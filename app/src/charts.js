// Small SVG line charts: the US trend strip above the year slider, and the
// selected state's history in the side panel.

const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

function scales(svg, { i0, i1, lo, hi, pad }) {
  const { width, height } = svg.getBoundingClientRect();
  const x = (i) => pad.l + ((i - i0) / Math.max(1, i1 - i0)) * (width - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (height - pad.t - pad.b);
  const xi = (px) => Math.round(i0 + ((px - pad.l) / (width - pad.l - pad.r)) * (i1 - i0));
  return { width, height, x, y, xi };
}

function pathFor(values, i0, i1, x, y) {
  let d = "";
  let pen = false;
  for (let i = i0; i <= i1; i++) {
    const v = values[i];
    if (v == null) { pen = false; continue; }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  }
  return d;
}

/** Linear interpolation of a series at fractional index t (null-safe). */
function valueAtT(values, t) {
  const i = Math.floor(t);
  const a = values[i], b = values[i + 1];
  if (a == null || b == null || t === i) return a ?? b ?? null;
  return a + (b - a) * (t - i);
}

/**
 * The timeline: a trend line (US, or the drilled-in state) that doubles as the
 * year scrubber. The playhead + knob mark year `t`; click or drag anywhere to
 * scrub (snaps to whole years), arrow keys / Home / End step it, and hovering
 * reads out the year and value under the pointer. Re-rendered every frame
 * while playing, so drag/hover state lives on the svg element.
 *
 * `compare` ({ label, values }) adds a dashed comparison line, with a key in
 * the label row. The mobile state view uses it instead of the detail chart.
 */
export function drawTrend(svg, { years, label: name, values, compare, i0, i1, t, format, onPick }) {
  svg.replaceChildren();
  const all = compare ? [...values.slice(i0, i1 + 1), ...compare.values.slice(i0, i1 + 1)] : values.slice(i0, i1 + 1);
  const vals = all.filter((v) => v != null);
  if (!vals.length) return;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = { l: 10, r: 10, t: 16, b: 8 };
  const { width, height, x, y, xi } = scales(svg, { i0, i1, lo: lo - (hi - lo) * 0.15, hi, pad });
  const clampI = (i) => Math.min(i1, Math.max(i0, i));
  const indexAt = (clientX) => clampI(xi(clientX - svg.getBoundingClientRect().left));

  // Track: full line in muted ink, the part already played in the accent.
  svg.append(el("line", { x1: pad.l, x2: width - pad.r, y1: height - pad.b, y2: height - pad.b, stroke: "var(--axis)" }));
  if (compare) {
    svg.append(el("path", { d: pathFor(compare.values, i0, i1, x, y), fill: "none", stroke: "var(--text-muted)", "stroke-width": 1.5, "stroke-dasharray": "4 3" }));
  }
  svg.append(el("path", { d: pathFor(values, i0, i1, x, y), fill: "none", stroke: "var(--text-muted)", "stroke-width": 2, "stroke-linejoin": "round" }));
  const clipId = `played-${svg.id}`;
  const clip = el("clipPath", { id: clipId });
  clip.append(el("rect", { x: 0, y: 0, width: Math.max(0, x(t)), height }));
  svg.append(clip);
  svg.append(el("path", { d: pathFor(values, i0, i1, x, y), fill: "none", stroke: "var(--accent)", "stroke-width": 2, "stroke-linejoin": "round", "clip-path": `url(#${clipId})` }));

  // Static labels hide while hovering so the readout has the top row to itself.
  const labels = el("g", { "font-size": 10, fill: "var(--text-muted)" });
  const label = (text, attrs) => {
    const tx = el("text", { y: 10, ...attrs });
    tx.textContent = text;
    labels.append(tx);
    return tx;
  };
  svg.append(labels);
  if (compare) {
    // Key: solid line + name, dashed line + comparison name, then the first year.
    let kx = pad.l;
    const key = (text, dash) => {
      labels.append(el("line", { x1: kx, x2: kx + 12, y1: 7, y2: 7, stroke: dash ? "var(--text-muted)" : "var(--accent)", "stroke-width": 2, ...(dash ? { "stroke-dasharray": "3 2" } : {}) }));
      kx += 12 + 4 + label(text, { x: kx + 16 }).getComputedTextLength() + 10;
    };
    key(name, false);
    key(compare.label, true);
    label(`· ${years[i0]}`, { x: kx - 4 });
  } else {
    label(`${name} · ${years[i0]}`, { x: pad.l });
  }
  label(years[i1], { x: width - pad.r, "text-anchor": "end" });

  // Playhead + knob (the slider thumb).
  const vt = valueAtT(values, t);
  svg.append(el("line", { x1: x(t), x2: x(t), y1: pad.t - 2, y2: height - pad.b, stroke: "var(--accent)", "stroke-width": 2 }));
  svg.append(el("circle", { cx: x(t), cy: vt == null ? height - pad.b : y(vt), r: 7, fill: "var(--accent)", stroke: "var(--surface-1)", "stroke-width": 2.5, class: "knob" }));

  const hover = el("g", { visibility: "hidden", "pointer-events": "none" });
  const hLine = el("line", { y1: pad.t - 2, y2: height - pad.b, stroke: "var(--text-secondary)", "stroke-dasharray": "2 2" });
  const hText = el("text", { y: 10, "font-size": 10, fill: "var(--text-primary)", "font-weight": 600 });
  hover.append(hLine, hText);
  svg.append(hover);

  const showHover = (i) => {
    svg._hover = i;
    if (i == null) {
      hover.setAttribute("visibility", "hidden");
      labels.setAttribute("visibility", "visible");
      return;
    }
    hover.setAttribute("visibility", "visible");
    labels.setAttribute("visibility", "hidden");
    hLine.setAttribute("x1", x(i)); hLine.setAttribute("x2", x(i));
    hText.textContent = `${years[i]} · ${format(values[i])}` + (compare ? ` · ${compare.label} ${format(compare.values[i])}` : "");
    const anchor = x(i) > width - 120 ? "end" : x(i) < 120 ? "start" : "middle";
    hText.setAttribute("x", x(i)); hText.setAttribute("text-anchor", anchor);
  };
  if (svg._hover != null) showHover(clampI(svg._hover));

  svg.onpointerdown = (e) => {
    svg._dragging = true;
    onPick(indexAt(e.clientX));
    try {
      svg.setPointerCapture(e.pointerId); // keep scrubbing when the pointer leaves the chart
    } catch {
      // pointer already released (e.g. a synthetic event); a plain click still works
    }
  };
  svg.onpointermove = (e) => {
    const i = indexAt(e.clientX);
    showHover(i);
    if (svg._dragging && i !== Math.round(t)) onPick(i);
  };
  svg.onpointerup = (e) => {
    svg._dragging = false;
    if (svg.hasPointerCapture?.(e.pointerId)) svg.releasePointerCapture(e.pointerId);
  };
  svg.onpointerleave = () => { if (!svg._dragging) showHover(null); };

  const ti = Math.round(t);
  svg.setAttribute("aria-valuemin", years[i0]);
  svg.setAttribute("aria-valuemax", years[i1]);
  svg.setAttribute("aria-valuenow", years[ti]);
  svg.setAttribute("aria-valuetext", `${years[ti]}: ${format(values[ti])}`);
  svg.onkeydown = (e) => {
    const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, PageUp: 5, PageDown: -5 }[e.key];
    let i = null;
    if (step) i = clampI(ti + step);
    if (e.key === "Home") i = i0;
    if (e.key === "End") i = i1;
    if (i == null) return;
    e.preventDefault();
    onPick(i);
  };
}

/** Selected state vs US over the metric's range, with the current year marked. */
export function drawDetail(svg, { years, state, us, i0, i1, t, tick, format, stateName }) {
  svg.replaceChildren();
  const vals = [...state.slice(i0, i1 + 1), ...us.slice(i0, i1 + 1)].filter((v) => v != null);
  if (!vals.length) return;
  const lo = Math.min(0, ...vals), hi = Math.max(...vals) * 1.05;
  const pad = { l: 40, r: 6, t: 6, b: 18 };
  const { width, height, x, y, xi } = scales(svg, { i0, i1, lo, hi, pad });

  for (const v of [lo, (lo + hi) / 2, hi].map((v) => v)) {
    svg.append(el("line", { x1: pad.l, x2: width - pad.r, y1: y(v), y2: y(v), stroke: "var(--grid)" }));
    const tx = el("text", { x: pad.l - 6, y: y(v) + 3, "font-size": 10, fill: "var(--text-muted)", "text-anchor": "end" });
    tx.textContent = tick(v);
    svg.append(tx);
  }
  for (const i of [i0, i1]) {
    const tx = el("text", { x: x(i), y: height - 4, "font-size": 10, fill: "var(--text-muted)", "text-anchor": i === i0 ? "start" : "end" });
    tx.textContent = years[i];
    svg.append(tx);
  }
  svg.append(el("line", { x1: x(t), x2: x(t), y1: pad.t, y2: height - pad.b, stroke: "var(--axis)", "stroke-width": 1 }));
  svg.append(el("path", { d: pathFor(us, i0, i1, x, y), fill: "none", stroke: "var(--text-muted)", "stroke-width": 2, "stroke-dasharray": "4 3" }));
  svg.append(el("path", { d: pathFor(state, i0, i1, x, y), fill: "none", stroke: "var(--accent)", "stroke-width": 2, "stroke-linejoin": "round" }));

  const hover = el("g", { visibility: "hidden" });
  const hLine = el("line", { y1: pad.t, y2: height - pad.b, stroke: "var(--text-secondary)", "stroke-dasharray": "2 2" });
  const hDot = el("circle", { r: 4, fill: "var(--accent)", stroke: "var(--surface-1)", "stroke-width": 2 });
  const hText = el("text", { y: pad.t + 8, "font-size": 10, fill: "var(--text-primary)", "font-weight": 600 });
  hover.append(hLine, hDot, hText);
  svg.append(hover);
  svg.onpointermove = (e) => {
    const r = svg.getBoundingClientRect();
    const i = Math.min(i1, Math.max(i0, xi(e.clientX - r.left)));
    hover.setAttribute("visibility", "visible");
    hLine.setAttribute("x1", x(i)); hLine.setAttribute("x2", x(i));
    hDot.setAttribute("cx", x(i)); hDot.setAttribute("cy", state[i] == null ? -99 : y(state[i]));
    hText.textContent = `${years[i]}: ${format(state[i])}`;
    hText.setAttribute("x", x(i) > width / 2 ? x(i) - 6 : x(i) + 6);
    hText.setAttribute("text-anchor", x(i) > width / 2 ? "end" : "start");
  };
  svg.onpointerleave = () => hover.setAttribute("visibility", "hidden");
  svg.setAttribute("aria-label", `${stateName} compared with the US, ${years[i0]} to ${years[i1]}`);
}
