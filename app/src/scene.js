// three.js scene. Geometry comes from us-atlas' Albers-projected TopoJSON
// (975 x 610 px, Alaska and Hawaii inset), so scene x/z are projected pixels
// and every layer (states, counties, city columns) lines up without a basemap.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { geoAlbersUsa } from "d3-geo";
import { cssVar } from "./colors.js";

const MAP_W = 975;
const MAP_H = 610;
const BASE_DEPTH = 3;
export const NATION_MAX_HEIGHT = 150; // scene units for normalized height 1, US view

// Same projection us-atlas used to build the *-albers-10m files.
const projection = geoAlbersUsa().scale(1300).translate([MAP_W / 2, MAP_H / 2]);

/** lon/lat -> scene [x, z], or null outside the projection. */
export function project(lon, lat) {
  const p = projection([lon, lat]);
  return p ? [p[0] - MAP_W / 2, p[1] - MAP_H / 2] : null;
}

// Projected pixel -> shape-plane coords. After rotateX(-90deg), shape y maps to
// world -z, so north (small py) ends up far from a camera placed to the south.
const toShape = ([px, py]) => new THREE.Vector2(px - MAP_W / 2, MAP_H / 2 - py);

function polygonsOf(geometry) {
  if (geometry.type === "Polygon") return [geometry.coordinates];
  if (geometry.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

/** Ring -> shape-plane points without repeated vertices; null if degenerate. */
function cleanRing(ring) {
  const pts = [];
  for (const p of ring.map(toShape)) if (!pts.length || !pts.at(-1).equals(p)) pts.push(p);
  if (pts.length > 1 && pts[0].equals(pts.at(-1))) pts.pop();
  return pts.length >= 3 && Math.abs(THREE.ShapeUtils.area(pts)) > 1e-9 ? pts : null;
}

const triangulates = (outer, holes) => {
  try {
    THREE.ShapeUtils.triangulateShape(outer, holes);
    return true;
  } catch {
    return false;
  }
};

/** Shapes for a (Multi)Polygon. A few simplified county rings trip up the
 * triangulator; those lose their holes, or are skipped as a last resort. */
function shapesFor(geometry) {
  const shapes = [];
  for (const [outerRing, ...holeRings] of polygonsOf(geometry)) {
    const outer = cleanRing(outerRing);
    if (!outer) continue;
    let holes = holeRings.map(cleanRing).filter(Boolean);
    if (!triangulates(outer, holes)) holes = [];
    if (!triangulates(outer, holes)) continue;
    const shape = new THREE.Shape(outer);
    shape.holes = holes.map((h) => new THREE.Path(h));
    shapes.push(shape);
  }
  return shapes;
}

function extrude(geometry, depth) {
  const shapes = shapesFor(geometry);
  const geo = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: false });
  geo.rotateX(-Math.PI / 2);
  return geo;
}

/** Outline rings at local height y (children of the mesh, so they ride its scale). */
function outlineFor(geometry, y, material) {
  const group = new THREE.Group();
  for (const polygon of polygonsOf(geometry)) {
    for (const ring of polygon) {
      const pts = ring.map(([px, py]) => new THREE.Vector3(px - MAP_W / 2, y, py - MAP_H / 2));
      group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), material));
    }
  }
  return group;
}

const ease = (k, from, to) => from + (to - from) * k;

/** Target color from { rgb: [r,g,b] } (sRGB 0..1) or { css }, else the fallback. */
function setTargetColor(color, t, fallback) {
  if (t?.rgb) color.setRGB(...t.rgb, THREE.SRGBColorSpace);
  else if (t?.css) color.set(t.css);
  else color.copy(fallback);
}

// ------------------------------------------------------------------ layers

/**
 * Polygons extruded to a unit height and scaled in y. Tops are unlit so their
 * color matches the legend exactly; sides are lit so the prisms read as 3D.
 */
class PrismLayer {
  constructor(scene, features, mats) {
    this.mats = mats;
    this.group = new THREE.Group();
    this.items = new Map(); // id -> item
    for (const f of features) {
      const top = new THREE.MeshBasicMaterial();
      const side = new THREE.MeshLambertMaterial();
      const mesh = new THREE.Mesh(extrude(f.geometry, 1), [top, side]);
      mesh.userData.id = f.id;
      const outline = outlineFor(f.geometry, 1.002, mats.outline);
      mesh.add(outline);
      this.group.add(mesh);
      this.items.set(f.id, {
        mesh, top, side, outline, height: mats.minHeight, target: mats.minHeight,
        color: new THREE.Color(0.5, 0.5, 0.5), targetColor: new THREE.Color(0.5, 0.5, 0.5),
      });
    }
    scene.add(this.group);
  }

  /** targets: Map id -> { h: scene units | null, rgb | css, hidden?: bool }; no rgb/css = missing color */
  setTargets(targets, immediate) {
    for (const [id, it] of this.items) {
      const t = targets.get(id);
      it.target = Math.max(this.mats.minHeight, t?.h ?? 0);
      setTargetColor(it.targetColor, t, this.mats.missing);
      it.mesh.visible = t?.hidden !== true;
      if (immediate) { it.height = it.target; it.color.copy(it.targetColor); }
    }
  }

  setFocus(ids) {
    for (const [id, it] of this.items) {
      const focus = ids.includes(id);
      for (const line of it.outline.children) line.material = focus ? this.mats.focus : this.mats.outline;
    }
  }

  update(k) {
    for (const it of this.items.values()) {
      it.height = ease(k, it.height, it.target);
      it.color.lerp(it.targetColor, k);
      it.mesh.scale.y = it.height;
      it.top.color.copy(it.color);
      it.side.color.copy(it.color);
    }
  }

  pickables() {
    return [...this.items.values()].filter((it) => it.mesh.visible).map((it) => it.mesh);
  }

  idOf(hit) {
    return hit.object.userData.id;
  }

  /** Footprint box of one item. */
  box(id) {
    const geo = this.items.get(id).mesh.geometry;
    geo.computeBoundingBox();
    return geo.boundingBox.clone();
  }

  dispose() {
    this.group.removeFromParent();
    for (const it of this.items.values()) {
      it.mesh.geometry.dispose();
      it.top.dispose();
      it.side.dispose();
      it.outline.children.forEach((l) => l.geometry.dispose());
    }
  }
}

/** One cylinder per point in a single InstancedMesh; height and color animate per instance. */
class ColumnLayer {
  constructor(scene, points, radius) {
    this.ids = points.map((p) => p.id);
    this.index = new Map(this.ids.map((id, i) => [id, i]));
    this.pos = points.map((p) => p.xz);
    this.radius = radius;
    const n = points.length;
    this.height = new Float32Array(n);
    this.target = new Float32Array(n);
    this.color = Array.from({ length: n }, () => new THREE.Color(0.5, 0.5, 0.5));
    this.targetColor = Array.from({ length: n }, () => new THREE.Color(0.5, 0.5, 0.5));
    this.focus = new Set();

    const geo = new THREE.CylinderGeometry(1, 1, 1, 14);
    geo.translate(0, 0.5, 0); // base at y = 0
    // CylinderGeometry groups: 0 = side, 1 = top cap, 2 = bottom cap.
    const side = new THREE.MeshLambertMaterial();
    const cap = new THREE.MeshBasicMaterial();
    this.mesh = new THREE.InstancedMesh(geo, [side, cap, cap], n);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < n; i++) this.mesh.setColorAt(i, this.color[i]);
    this.matrix = new THREE.Matrix4();
    scene.add(this.mesh);
    this.update(1);
  }

  setTargets(targets, immediate) {
    this.ids.forEach((id, i) => {
      const t = targets.get(id);
      this.target[i] = t?.h ?? 0; // no data -> shrinks away
      if (t?.rgb || t?.css) setTargetColor(this.targetColor[i], t, this.targetColor[i]);
      if (immediate) { this.height[i] = this.target[i]; this.color[i].copy(this.targetColor[i]); }
    });
  }

  setFocus(ids) {
    this.focus = new Set(ids.filter((id) => this.index.has(id)));
  }

  update(k) {
    for (let i = 0; i < this.ids.length; i++) {
      this.height[i] = ease(k, this.height[i], this.target[i]);
      this.color[i].lerp(this.targetColor[i], k);
      const h = this.height[i];
      const r = h > 0.01 ? this.radius * (this.focus.has(this.ids[i]) ? 1.9 : 1) : 0;
      const [x, z] = this.pos[i];
      this.matrix.makeScale(r, Math.max(h, 0.001), r).setPosition(x, 0, z);
      this.mesh.setMatrixAt(i, this.matrix);
      this.mesh.setColorAt(i, this.color[i]);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    this.mesh.instanceColor.needsUpdate = true;
    this.mesh.computeBoundingSphere();
  }

  pickables() {
    return [this.mesh];
  }

  idOf(hit) {
    return this.ids[hit.instanceId];
  }

  dispose() {
    this.mesh.removeFromParent();
    this.mesh.geometry.dispose();
    this.mesh.dispose();
  }
}

// ------------------------------------------------------------------ scene

export class MapScene {
  constructor(container, { onHover, onClick }) {
    this.container = container;
    this.onHover = onHover;
    this.onClick = onClick;
    this.hovered = null; // { layer, id }
    this.layers = {}; // name -> PrismLayer | ColumnLayer | null
    this.pickOrder = ["states"];
    this.home = null; // footprint box "Reset view" returns to (null = nation)

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);
    // HTML labels drawn over the canvas, positioned from 3D anchors every frame.
    this.labelRenderer = new CSS2DRenderer();
    Object.assign(this.labelRenderer.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
    container.appendChild(this.labelRenderer.domElement);
    this.labels = [];
    this.downRay = new THREE.Raycaster();

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 1, 6000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minPolarAngle = 0.05;
    this.controls.maxPolarAngle = 1.32; // never below the horizon
    this.controls.minDistance = 10;
    this.controls.screenSpacePanning = false;

    // Dim enough that a lit wall never outshines its own (unlit) top, so
    // on-screen brightness always follows the color scale.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a8a, 0.8));
    const sun = new THREE.DirectionalLight(0xffffff, 0.4);
    sun.position.set(-400, 700, 600);
    this.scene.add(sun);

    this.mats = {
      outline: new THREE.LineBasicMaterial({ transparent: true, opacity: 0.9 }),
      focus: new THREE.LineBasicMaterial(),
      missing: new THREE.Color(),
      minHeight: 0.6,
    };
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.pointerInside = false;

    this.bindPointer();
    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.clock = new THREE.Clock();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  build(states, nation) {
    this.baseMat = new THREE.MeshLambertMaterial();
    const base = new THREE.Mesh(extrude(nation.geometry, BASE_DEPTH), this.baseMat);
    base.position.y = -BASE_DEPTH;
    this.scene.add(base);
    this.layers.states = new PrismLayer(this.scene, states, this.mats);
    this.applyTheme();
    this.resetView(false);
  }

  /** Replace the county layer (null removes it). */
  setCounties(features) {
    this.layers.counties?.dispose();
    this.layers.counties = features
      ? new PrismLayer(this.scene, features, { ...this.mats, minHeight: 0.15 })
      : null;
  }

  /** Replace the city column layer (null removes it). points: [{ id, xz: [x, z] }] */
  setCities(points, radius) {
    this.layers.cities?.dispose();
    this.layers.cities = points ? new ColumnLayer(this.scene, points, radius) : null;
  }

  setTargets(layer, targets, immediate = false) {
    this.layers[layer]?.setTargets(targets, immediate);
  }

  setPickOrder(names) {
    this.pickOrder = names;
  }

  /** focus: { layerName: [ids] } drawn with the focus outline / wider column. */
  setFocus(focus) {
    for (const [name, layer] of Object.entries(this.layers)) layer?.setFocus(focus[name] ?? []);
  }

  /**
   * labels: [{ text, cls, xz: [x, z], anchor }], most important first: when two
   * overlap on screen, the later one is hidden. anchor says what the label sits
   * on: { layer: "states" | "cities", id } follows that prism/column's height;
   * { layer: "counties" } sits on whatever county is under the point.
   */
  setLabels(labels) {
    for (const l of this.labels) l.obj.removeFromParent();
    this.labels = labels.map((l) => {
      const el = document.createElement("div");
      el.className = `map-label ${l.cls ?? ""}`;
      const span = document.createElement("span");
      span.textContent = l.text;
      el.append(span);
      const obj = new CSS2DObject(el);
      obj.position.set(l.xz[0], 0, l.xz[1]);
      this.scene.add(obj);
      return { ...l, obj, span };
    });
    this.labelFrame = 0;
  }

  /** Greedy overlap culling in priority order (labels are pre-sorted). */
  cullLabels() {
    const placed = [];
    for (const l of this.labels) {
      const r = l.span.getBoundingClientRect();
      const hit = placed.some((p) => r.left < p.right + 1 && r.right > p.left - 1 && r.top < p.bottom && r.bottom > p.top);
      l.span.style.visibility = hit ? "hidden" : "visible";
      if (!hit) placed.push(r);
    }
  }

  labelHeight(l) {
    const { layer, id } = l.anchor;
    if (layer === "states") return this.layers.states?.items.get(id)?.height ?? 0;
    if (layer === "cities") {
      const c = this.layers.cities;
      const i = c?.index.get(id);
      return i == null ? 0 : c.height[i];
    }
    const counties = this.layers.counties;
    if (!counties) return 0;
    this.downRay.set(new THREE.Vector3(l.xz[0], 1e4, l.xz[1]), new THREE.Vector3(0, -1, 0));
    return this.downRay.intersectObjects(counties.pickables(), false)[0]?.point.y ?? 0;
  }

  applyTheme() {
    this.scene.background = new THREE.Color(cssVar("--surface-1"));
    this.baseMat?.color.set(cssVar("--map-base"));
    this.mats.outline.color.set(cssVar("--map-outline"));
    this.mats.focus.color.set(cssVar("--text-primary"));
    this.mats.missing.set(cssVar("--map-missing"));
  }

  // ---------------------------------------------------------------- camera

  nationBox() {
    return new THREE.Box3(new THREE.Vector3(-MAP_W / 2, 0, -MAP_H / 2), new THREE.Vector3(MAP_W / 2, 0, MAP_H / 2));
  }

  stateBox(id) {
    return this.layers.states.box(id);
  }

  /** Larger horizontal side of a footprint box. */
  static extent(box) {
    return Math.max(box.max.x - box.min.x, box.max.z - box.min.z);
  }

  /**
   * Tween the camera to frame a footprint box from the south, tilted 48 degrees.
   * `height` is the tallest prism/column expected, so tall blocks stay in frame:
   * from this tilt the ground's depth shows at cos(48) and heights at sin(48).
   */
  fitBox(box, height, animate = true) {
    const w = box.max.x - box.min.x;
    const d = box.max.z - box.min.z;
    const polar = THREE.MathUtils.degToRad(48);
    const vfov = THREE.MathUtils.degToRad(this.camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
    const span = d * Math.cos(polar) + height * Math.sin(polar);
    const dist = Math.max((w * 1.22) / 2 / Math.tan(hfov / 2), (span * 1.35) / 2 / Math.tan(vfov / 2));
    const c = box.getCenter(new THREE.Vector3());
    // Aim partway up the blocks, nudged left/north so the legend (top-left)
    // overlaps less of the map.
    const target = new THREE.Vector3(c.x - w * 0.03, height * 0.3, c.z - d * 0.04);
    const pos = new THREE.Vector3(0, Math.cos(polar) * dist, Math.sin(polar) * dist).add(target);
    this.controls.maxDistance = Math.max(dist * 3, 600);
    if (!animate) {
      this.camera.position.copy(pos);
      this.controls.target.copy(target);
      this.controls.update();
      return;
    }
    this.cameraTween = { from: this.camera.position.clone(), fromT: this.controls.target.clone(), pos, target, k: 0 };
  }

  /** The view "Reset view" returns to: a footprint box and its max block height (null = nation). */
  setHome(box, height) {
    this.home = box ? { box, height } : null;
    this.resetView();
  }

  resetView(animate = true) {
    const { box, height } = this.home ?? { box: this.nationBox(), height: NATION_MAX_HEIGHT };
    this.fitBox(box, height, animate);
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.labelRenderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // ---------------------------------------------------------------- picking

  bindPointer() {
    const el = this.renderer.domElement;
    let down = null;
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      this.pointerInside = true;
      this.pointerClient = { x: e.clientX, y: e.clientY };
    });
    el.addEventListener("pointerleave", () => {
      this.pointerInside = false;
      if (this.hovered) { this.hovered = null; this.onHover(null); }
    });
    el.addEventListener("pointerdown", (e) => (down = { x: e.clientX, y: e.clientY }));
    el.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return; // a drag, not a click
      this.onClick(this.pick());
    });
  }

  /** Nearest hit across the pickable layers -> { layer, id } | null. */
  pick() {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    let best = null;
    for (const name of this.pickOrder) {
      const layer = this.layers[name];
      if (!layer) continue;
      const hit = this.raycaster.intersectObjects(layer.pickables(), false)[0];
      if (hit && (!best || hit.distance < best.distance)) best = { distance: hit.distance, layer: name, id: layer.idOf(hit) };
    }
    return best && { layer: best.layer, id: best.id };
  }

  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    const k = 1 - Math.exp(-dt * 9); // frame-rate independent easing
    for (const layer of Object.values(this.layers)) layer?.update(k);

    if (this.cameraTween) {
      const tw = this.cameraTween;
      tw.k = Math.min(1, tw.k + dt * 1.4);
      const e = 1 - Math.pow(1 - tw.k, 3);
      this.camera.position.lerpVectors(tw.from, tw.pos, e);
      this.controls.target.lerpVectors(tw.fromT, tw.target, e);
      if (tw.k >= 1) this.cameraTween = null;
    }
    this.controls.update();

    if (this.pointerInside) {
      const h = this.pick();
      if (h?.layer !== this.hovered?.layer || h?.id !== this.hovered?.id) {
        this.hovered = h;
        this.onHover(h);
      }
      this.onPointer?.(this.pointerClient);
    }
    for (const l of this.labels) l.obj.position.y = this.labelHeight(l);
    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
    if (this.labels.length && this.labelFrame++ % 6 === 0) this.cullLabels();
  }
}
