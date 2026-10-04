import { loadData, loadCountyShapes, loadStateDetail, buildMetrics, yearRange, valueAt } from "./data.js";
import { ramp, rampGradient, cssRgb, cssVar } from "./colors.js";
import { MapScene, NATION_MAX_HEIGHT, project } from "./scene.js";
import { drawTrend, drawDetail } from "./charts.js";

const $ = (id) => document.getElementById(id);
const PLAY_SPEED = 1.6; // years per second
const STATE_HEIGHT = 0.45; // max prism/column height in a state view, as a share of the state's footprint
const CITY_RADIUS = 0.006; // city column radius, as a share of the state's footprint
const CITY_LABELS = 8; // most populous cities labelled in a state view

const { states: data, shapes, nation } = await loadData();
const metrics = buildMetrics(data);
const stateByFips = new Map(data.states.map((s) => [s.fips, s]));
const stateByAbbr = new Map(data.states.map((s) => [s.abbr, s]));
const partial = data.meta.partial_year;

const ui = {
  metric: metrics[0],
  scale: "fixed",
  t: data.years.length - 1, // fractional year index
  range: [0, data.years.length - 1],
  playing: false,
  state: null, // fips of the drilled-in state; null = whole nation
  level: "counties", // what a state view shows: counties | cities
  levels: null, // record sets for the drilled-in state
  extent: 1, // footprint size of the drilled-in state (scene units)
  hovered: null, // { layer, id }
  selected: null, // id in the current level (state view only)
};

// ---------------------------------------------------------------- levels

const nationLevel = levelOf("states", "States", data.states, (r) => r.fips);

function levelOf(name, label, records, key) {
  return { name, label, records, key, byId: new Map(records.map((r) => [key(r), r])) };
}

/** The record set the map, ranking and tooltips currently describe. */
function current() {
  return ui.state ? ui.levels[ui.level] : nationLevel;
}

/** The record a selection is compared with: the state in a state view, else the US. */
function parentRecord() {
  return ui.state ? stateByFips.get(ui.state) : data.us;
}

const levelFor = (layer) => (layer === "states" ? nationLevel : ui.levels?.[layer]);
const recordOf = (h) => h && levelFor(h.layer)?.byId.get(h.id);

// ---------------------------------------------------------------- scales

/** [lo, hi, clipped] over every value in range ("All years") or this year
 * ("Each year"). Counties and cities use the 1st-99th percentile so a handful
 * of extreme places don't flatten everything else; values beyond are capped. */
function computeDomain(t) {
  const m = ui.metric;
  const lvl = current();
  const vals = [];
  for (const r of lvl.records) {
    if (ui.scale === "fixed") {
      for (let i = ui.range[0]; i <= ui.range[1]; i++) {
        const v = m.get(r, i);
        if (v != null) vals.push(v);
      }
    } else {
      const v = valueAt(m, r, t);
      if (v != null) vals.push(v);
    }
  }
  if (!vals.length) return [0, 1, false];
  vals.sort((a, b) => a - b);
  if (lvl.name === "states") return [vals[0], vals.at(-1), false];
  const q = (p) => vals[Math.floor(p * (vals.length - 1))];
  const hi = q(0.99);
  return [q(0.01), hi, vals.at(-1) > hi];
}

let fixedDomainCache = null;
function domain(t = ui.t) {
  if (ui.scale === "year") return computeDomain(t);
  return (fixedDomainCache ??= computeDomain(t));
}

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const heightNorm = (v, [, hi]) => clamp01((v - ui.metric.heightFloor) / (hi - ui.metric.heightFloor));
const colorNorm = (v, [lo, hi]) => (hi > lo ? clamp01((v - lo) / (hi - lo)) : 0.5);
const maxHeight = () => (ui.state ? ui.extent * STATE_HEIGHT : NATION_MAX_HEIGHT);
const yearIndex = () => Math.round(ui.t);

function ranking(i, lvl = current()) {
  return lvl.records
    .map((r) => ({ r, v: ui.metric.get(r, i) }))
    .sort((a, b) => (b.v ?? -Infinity) - (a.v ?? -Infinity));
}

// ---------------------------------------------------------------- map

const map = new MapScene($("map"), {
  onHover: (h) => setHovered(isGround(h) ? null : h),
  onClick: (h) => onMapClick(h),
});
map.build(shapes, nation);
map.onPointer = positionTooltip;

function valueTargets(lvl, dom) {
  const out = new Map();
  const H = maxHeight();
  for (const r of lvl.records) {
    const v = valueAt(ui.metric, r, ui.t);
    out.set(lvl.key(r), v == null ? { h: null } : { h: heightNorm(v, dom) * H, rgb: ramp(colorNorm(v, dom)) });
  }
  return out;
}

function updateMap(immediate = false) {
  const dom = domain();
  if (!ui.state) {
    map.setTargets("states", valueTargets(nationLevel, dom), immediate);
    return;
  }
  // State view: other states flatten into ground; the selected one is replaced by its counties.
  const dim = cssVar("--map-dim");
  map.setTargets("states", new Map(data.states.map((s) => [s.fips, s.fips === ui.state ? { hidden: true } : { h: 0, css: dim }])), immediate);
  if (ui.level === "counties") {
    map.setTargets("counties", valueTargets(ui.levels.counties, dom), immediate);
    map.setTargets("cities", new Map(), immediate); // columns shrink away
  } else {
    const ground = cssVar("--map-ground");
    map.setTargets("counties", new Map(ui.levels.counties.records.map((c) => [c.fips, { h: 0, css: ground }])), immediate);
    map.setTargets("cities", valueTargets(ui.levels.cities, dom), immediate);
  }
}

function updateFocus() {
  const focus = {};
  const add = (h) => h && (focus[h.layer] ??= []).push(h.id);
  add(ui.hovered);
  if (ui.selected != null) add({ layer: current().name, id: ui.selected });
  map.setFocus(focus);
}

/** State view only: the most populous cities, on their column (cities level)
 * or on the county under them (counties level). */
function updateLabels() {
  if (!ui.state) {
    map.setLabels([]);
    return;
  }
  const biggest = ui.levels.cities.records
    .filter((c) => c.population != null)
    .sort((a, b) => b.population - a.population)
    .slice(0, CITY_LABELS);
  map.setLabels(biggest.map((c) => ({
    text: c.name, cls: "city", xz: project(c.lon, c.lat),
    anchor: ui.level === "cities" ? { layer: "cities", id: c.id } : { layer: "counties" },
  })).filter((l) => l.xz));
}

// ---------------------------------------------------------------- navigation

let navToken = 0;

/** Route from the URL hash: "" = nation, "#CA" = counties of CA, "#CA/cities". */
async function route() {
  const [abbr, lvl] = location.hash.replace(/^#/, "").split("/");
  const st = stateByAbbr.get((abbr || "").toUpperCase());
  const token = ++navToken;
  if (!st) return showNation();
  const [detail, countyShapes] = await Promise.all([loadStateDetail(st.fips), loadCountyShapes(st.fips)]);
  if (token !== navToken) return; // a newer navigation won
  showState(st.fips, lvl === "cities" ? "cities" : "counties", detail, countyShapes);
}

function go(abbr, level) {
  location.hash = abbr ? (level === "cities" ? `${abbr}/cities` : abbr) : "";
}

function showNation() {
  if (ui.state) {
    map.setCounties(null);
    map.setCities(null);
    map.setHome(null);
  }
  ui.state = null;
  ui.levels = null;
  ui.selected = null;
  refresh();
}

function showState(fips, level, detail, countyShapes) {
  if (fips !== ui.state) {
    ui.state = fips;
    ui.selected = null;
    // Counties on the map without any data still get a record (drawn as missing).
    const byFips = new Map(detail.counties.map((c) => [c.fips, c]));
    const counties = countyShapes.map((f) => byFips.get(f.id) ?? { fips: f.id, name: f.properties.name, home_value: null });
    ui.levels = {
      counties: levelOf("counties", "Counties", counties, (r) => r.fips),
      cities: levelOf("cities", "Cities", detail.cities, (r) => r.id),
    };
    const box = map.stateBox(fips);
    ui.extent = MapScene.extent(box);
    map.setCounties(countyShapes);
    const points = detail.cities.map((c) => ({ id: c.id, xz: project(c.lon, c.lat) })).filter((p) => p.xz);
    map.setCities(points, ui.extent * CITY_RADIUS);
    map.setHome(box, ui.extent * STATE_HEIGHT);
  }
  if (level !== ui.level) ui.selected = null;
  ui.level = level;
  if (!ui.metric.levels.includes(level)) ui.metric = metrics[0];
  refresh();
}

/** In city view the counties are flat ground: hits on them count as "inside
 * the state" but aren't hoverable or selectable. */
const isGround = (h) => ui.state && ui.level === "cities" && h?.layer === "counties";

function onMapClick(h) {
  if (!h) {
    if (ui.state) go(null); // clicked away from the state: back to the US
    return;
  }
  if (isGround(h)) return;
  if (h.layer === "states") {
    if (h.id !== ui.state) go(stateByFips.get(h.id).abbr, ui.state ? ui.level : "counties");
    return;
  }
  setSelected(h.id);
}

// ---------------------------------------------------------------- full refresh

function refresh() {
  pause();
  ui.range = yearRange(ui.metric, current().records, data.years);
  if (ui.range[0] < 0) ui.range = [0, data.years.length - 1];
  fixedDomainCache = null;
  ui.hovered = null;
  $("tooltip").hidden = true;
  renderControls();
  renderTitle();
  map.setPickOrder(!ui.state ? ["states"] : ui.level === "cities" ? ["cities", "counties", "states"] : ["counties", "states"]);
  updateLabels();
  setYear(Math.round(ui.t), false, true);
  updateFocus();
}

// ---------------------------------------------------------------- title, controls, legend, badge

function renderTitle() {
  const h1 = $("title");
  if (!ui.state) { h1.textContent = "US Housing Costs"; return; }
  h1.innerHTML = `<button class="crumb" id="crumb-home">US Housing Costs</button><span class="sep">/</span>${stateByFips.get(ui.state).name}`;
  $("crumb-home").onclick = () => go(null);
}

function renderControls() {
  for (const b of $("metric-buttons").children) {
    const m = metrics.find((x) => x.id === b.dataset.id);
    b.disabled = !m.levels.includes(current().name);
    b.setAttribute("aria-checked", String(m === ui.metric));
  }
  $("level-buttons").hidden = !ui.state;
  mark($("level-buttons"), ui.level);
  mark($("scale-buttons"), ui.scale);
}

function updateLegend() {
  const m = ui.metric;
  const [lo, hi, clipped] = domain();
  $("legend-title").textContent = m.label;
  $("legend-bar").style.background = rampGradient();
  $("legend-ticks").replaceChildren(
    ...[lo, (lo + hi) / 2, hi].map((v, k) => {
      const span = document.createElement("span");
      span.style.left = `${k * 50}%`;
      span.textContent = m.tick(v) + (k === 2 && clipped ? "+" : "");
      return span;
    }),
  );
}

const monthName = (m) =>
  ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1];

function updateBadge() {
  const year = data.years[yearIndex()];
  const note = partial && year === partial.year ? `<small>Jan–${monthName(partial.months)} average</small>` : "";
  $("year-badge").innerHTML = `${year}${note}`;
}

// ---------------------------------------------------------------- ranking list (also the table view)

let lastRankKey = null;
function updateRanking(force = false) {
  const i = yearIndex();
  const lvl = current();
  const key = `${lvl.name}:${ui.state}:${i}`;
  if (!force && key === lastRankKey) return false;
  lastRankKey = key;
  const dom = domain(i);
  const rows = ranking(i, lvl);
  const max = Math.max(...rows.map((r) => r.v ?? 0));
  const floor = ui.metric.heightFloor;
  $("ranking-title").textContent = `${lvl.label}, ${data.years[i]}`;
  $("ranking").replaceChildren(
    ...rows.map(({ r, v }, k) => {
      const id = lvl.key(r);
      const li = document.createElement("li");
      li.dataset.id = id;
      li.tabIndex = 0;
      const pct = v == null ? 0 : clamp01((v - floor) / (max - floor)) * 100;
      li.innerHTML = `
        <span class="rank">${v == null ? "–" : k + 1}</span>
        <span class="name">${r.name}</span>
        <span class="val ${v == null ? "missing" : ""}">${v == null ? "No data" : ui.metric.tick(v)}</span>
        <span class="bar"><i style="width:${pct}%;background:${v == null ? "transparent" : cssRgb(ramp(colorNorm(v, dom)))}"></i></span>`;
      const h = { layer: lvl.name, id };
      li.onmouseenter = () => setHovered(h, false);
      li.onmouseleave = () => setHovered(null, false);
      const activate = () => (ui.state ? setSelected(id) : go(r.abbr));
      li.onclick = activate;
      li.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), activate());
      return li;
    }),
  );
  markRows();
  return true;
}

function markRows() {
  const lvl = current().name;
  for (const li of $("ranking").children) {
    const id = li.dataset.id;
    li.classList.toggle("hovered", ui.hovered?.layer === lvl && String(ui.hovered.id) === id);
    li.classList.toggle("selected", ui.selected != null && String(ui.selected) === id);
  }
}

// ---------------------------------------------------------------- hover + tooltip

function setHovered(h, fromMap = true) {
  ui.hovered = h;
  updateFocus();
  markRows();
  if (!h) $("tooltip").hidden = true;
  else if (fromMap) renderTooltip();
}

function renderTooltip() {
  const h = ui.hovered;
  const r = recordOf(h);
  if (!r) { $("tooltip").hidden = true; return; }
  const i = yearIndex();
  const m = ui.metric;
  const v = m.get(r, i);
  const rows = ranking(i, levelFor(h.layer));
  const rank = rows.findIndex((x) => x.r === r) + 1;
  const ranked = rows.filter((x) => x.v != null).length;
  const first = firstValue(r);
  const where = h.layer === "cities" ? r.county : h.layer === "counties" ? stateByFips.get(ui.state).name : null;
  const change = v != null && first && first.i < i ? `<div>${changeText(first.v, v)} since ${data.years[first.i]}</div>` : "";
  $("tooltip").innerHTML = `
    <strong>${r.name}</strong>
    ${where ? `<div class="where">${where}</div>` : ""}
    <div class="value">${m.format(v)}</div>
    <div>${data.years[i]}${v != null ? ` · rank ${rank} of ${ranked}` : ""}</div>
    ${change}`;
  $("tooltip").hidden = false;
}

function firstValue(r) {
  for (let i = ui.range[0]; i <= ui.range[1]; i++) {
    const v = ui.metric.get(r, i);
    if (v != null) return { i, v };
  }
  return null;
}

function changeText(a, b) {
  if (ui.metric.id === "rpp") return `${b - a >= 0 ? "+" : ""}${(b - a).toFixed(1)} pts`;
  const r = b / a;
  return r >= 2 ? `${r.toFixed(1)}×` : `${r >= 1 ? "+" : ""}${((r - 1) * 100).toFixed(0)}%`;
}

function positionTooltip(p) {
  const tip = $("tooltip");
  if (tip.hidden || !p) return;
  const { offsetWidth: w, offsetHeight: h } = tip;
  const x = p.x + 16 + w > window.innerWidth ? p.x - w - 16 : p.x + 16;
  const y = Math.min(window.innerHeight - h - 8, p.y + 16);
  tip.style.transform = `translate(${x}px, ${y}px)`;
}

// ---------------------------------------------------------------- selection + detail panel

function setSelected(id) {
  ui.selected = id === ui.selected ? null : id;
  updateFocus();
  markRows();
  renderDetail();
  renderTrend();
}

/** State view: the selected county/city vs its state, or else the state vs the US. */
function renderDetail() {
  const box = $("detail");
  if (!ui.state) { box.hidden = true; return; }
  const st = stateByFips.get(ui.state);
  const sel = ui.selected != null ? current().byId.get(ui.selected) : null;
  const rec = sel ?? st;
  const parent = sel ? st : data.us;
  const m = ui.metric;
  const i = yearIndex();
  const v = m.get(rec, i);
  const rows = ranking(i, sel ? current() : nationLevel);
  const rank = rows.findIndex((x) => x.r === rec) + 1;
  const ranked = rows.filter((x) => x.v != null).length;
  const pv = m.get(parent, i);
  box.hidden = false;
  box.innerHTML = `
    <div class="detail-head">
      <h3>${rec.name}</h3>
      ${sel ? `<button class="close" id="detail-close" aria-label="Clear selection">×</button>` : ""}
    </div>
    <div class="big">${m.format(v)}</div>
    <div class="meta">${data.years[i]}${v != null ? ` · rank ${rank} of ${ranked}` : ""}${pv != null && m.id !== "rpp" ? ` · ${sel ? st.abbr : "US"} ${m.format(pv)}` : ""}</div>
    <svg id="detail-chart"></svg>
    <div class="key"><span><i style="background:var(--accent)"></i>${sel ? rec.name : st.abbr}</span><span><i style="background:var(--text-muted)"></i>${sel ? st.name : "United States"}</span></div>`;
  if (sel) $("detail-close").onclick = () => setSelected(null);
  if (mobile.matches) return; // the timeline shows this comparison on phones
  const series = (r) => data.years.map((_, k) => m.get(r, k));
  drawDetail($("detail-chart"), {
    years: data.years, state: series(rec), us: series(parent),
    i0: ui.range[0], i1: ui.range[1], t: ui.t, tick: m.tick, format: m.format, stateName: rec.name,
  });
}

// ---------------------------------------------------------------- timeline

// Phone layout (same breakpoint as styles.css): in a state view the timeline
// also carries the comparison line, and the detail card drops its own chart.
const mobile = window.matchMedia("(max-width: 860px)");

function renderTrend() {
  const m = ui.metric;
  const series = (r) => data.years.map((_, k) => m.get(r, k));
  let rec = parentRecord();
  let compare = null;
  if (mobile.matches && ui.state) {
    const st = stateByFips.get(ui.state);
    const sel = ui.selected != null ? current().byId.get(ui.selected) : null;
    rec = sel ?? st;
    compare = sel ? { label: st.abbr, values: series(st) } : { label: "US", values: series(data.us) };
  }
  drawTrend($("trend"), {
    years: data.years,
    label: rec.name,
    values: series(rec),
    compare,
    i0: ui.range[0], i1: ui.range[1], t: ui.t, format: m.format,
    onPick: (i) => { pause(); setYear(i); },
  });
}

function setYear(t, immediate = false, force = false) {
  ui.t = Math.min(ui.range[1], Math.max(ui.range[0], t));
  updateMap(immediate);
  updateBadge();
  if (ui.scale === "year" || force) updateLegend();
  if (updateRanking(force)) {
    renderDetail();
    if (ui.hovered) renderTooltip();
  }
  renderTrend();
}

let lastFrame = null;
function tick(now) {
  if (!ui.playing) return;
  if (lastFrame != null) {
    const t = ui.t + ((now - lastFrame) / 1000) * PLAY_SPEED;
    if (t >= ui.range[1]) { setYear(ui.range[1]); pause(); return; }
    setYear(t);
  }
  lastFrame = now;
  requestAnimationFrame(tick);
}

/** Animated playback through the years (Space toggles it). */
function play() {
  if (ui.t >= ui.range[1]) setYear(ui.range[0], true);
  ui.playing = true;
  lastFrame = null;
  requestAnimationFrame(tick);
}

function pause() {
  if (!ui.playing) return;
  ui.playing = false;
  setYear(Math.round(ui.t));
}

window.addEventListener("keydown", (e) => {
  if (e.target.closest("input, button, li, [role=slider]")) return;
  if (e.key === " ") { e.preventDefault(); ui.playing ? pause() : play(); }
  if (e.key === "ArrowRight") { pause(); setYear(Math.round(ui.t) + 1); }
  if (e.key === "ArrowLeft") { pause(); setYear(Math.round(ui.t) - 1); }
  if (e.key === "Escape") {
    if (ui.selected != null) setSelected(null);
    else if (ui.state) go(null);
  }
});

// ---------------------------------------------------------------- controls

const mark = (container, id) => {
  for (const b of container.children) b.setAttribute("aria-checked", String(b.dataset.id === id));
};

function segmented(container, items, onPick) {
  container.replaceChildren(
    ...items.map(({ id, label, title }) => {
      const b = document.createElement("button");
      b.setAttribute("role", "radio");
      b.dataset.id = id;
      b.textContent = label;
      if (title) b.title = title;
      b.onclick = () => onPick(id);
      return b;
    }),
  );
}

segmented($("metric-buttons"), metrics.map((m) => ({ id: m.id, label: m.label, title: m.sublabel })), (id) => {
  ui.metric = metrics.find((m) => m.id === id);
  refresh();
});
segmented($("scale-buttons"), [
  { id: "fixed", label: "All years", title: "Colors and heights span every year's values: see change over time" },
  { id: "year", label: "This year", title: "Colors and heights span only this year's values: compare places within the year" },
], (id) => {
  ui.scale = id;
  refresh();
});
segmented($("level-buttons"), [
  { id: "counties", label: "Counties" },
  { id: "cities", label: "Cities" },
], (id) => go(stateByFips.get(ui.state).abbr, id));

// Theme changes repaint everything (outline, ground and missing colors come from CSS).
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  map.applyTheme();
  refresh();
});
new ResizeObserver(() => { renderTrend(); renderDetail(); }).observe($("trend"));
mobile.addEventListener("change", () => { renderTrend(); renderDetail(); });
window.addEventListener("hashchange", route);

refresh();
updateMap(true);
route();

if (import.meta.env.DEV) window.__app = { map, ui, data }; // for debugging in the console
