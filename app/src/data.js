// Loads states.json + state geometry and defines the metrics the map can show.

import { feature } from "topojson-client";

export async function loadData() {
  const [states, topo] = await Promise.all([
    fetch("/states.json").then((r) => r.json()),
    fetch("/geo/states-albers-10m.json").then((r) => r.json()),
  ]);
  const shapes = feature(topo, topo.objects.states).features;
  const nationFc = feature(topo, topo.objects.nation);
  const nation = nationFc.features ? nationFc.features[0] : nationFc;
  return { states, shapes, nation };
}

// Drill-down data is fetched on first use and cached.
let countyTopo = null;
const stateDetail = new Map();

/** County polygons (Albers-projected) for one state. */
export async function loadCountyShapes(stateFips) {
  countyTopo ??= fetch("/geo/counties-albers-10m.json").then((r) => r.json());
  const topo = await countyTopo;
  return feature(topo, topo.objects.counties).features.filter((f) => f.id.startsWith(stateFips));
}

/** { counties, cities } for one state, annual arrays aligned to states.json `years`. */
export function loadStateDetail(stateFips) {
  if (!stateDetail.has(stateFips)) {
    stateDetail.set(stateFips, fetch(`/by_state/${stateFips}.json`).then((r) => r.json()));
  }
  return stateDetail.get(stateFips);
}

const usd = (v) =>
  v == null ? "No data" : "$" + Math.round(v).toLocaleString("en-US");
const usdShort = (v) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3)}k`;

/**
 * A metric maps (record, year index) -> number|null. `levels` lists where the
 * data exists: county and city records only carry home values.
 * heightFloor: value at which bars have zero height (0 for $ and ratios; index
 * metrics hover around 100, so they are measured from a floor stated in the legend).
 */
export function buildMetrics(data) {
  const { years, cpi } = data;
  const lastYear = years[years.length - 1];
  const cpiLast = cpi[years.length - 1] ?? cpi.filter((v) => v != null).at(-1);

  return [
    {
      id: "real",
      label: "Home value",
      sublabel: `typical home, in ${lastYear} dollars`,
      get: (s, i) =>
        s.home_value?.[i] == null || cpi[i] == null ? null : (s.home_value[i] * cpiLast) / cpi[i],
      format: usd,
      tick: usdShort,
      heightFloor: 0,
      levels: ["states", "counties", "cities"],
    },
    {
      id: "nominal",
      label: "Home value (nominal)",
      sublabel: "typical home, dollars of each year",
      get: (s, i) => s.home_value?.[i] ?? null,
      format: usd,
      tick: usdShort,
      heightFloor: 0,
      levels: ["states", "counties", "cities"],
    },
    {
      id: "ratio",
      label: "Price-to-income",
      sublabel: "home value ÷ median household income",
      get: (s, i) => s.value_to_income?.[i] ?? null,
      format: (v) => (v == null ? "No data" : `${v.toFixed(1)}× income`),
      tick: (v) => `${v.toFixed(0)}×`,
      heightFloor: 0,
      levels: ["states"],
    },
    {
      id: "rpp",
      label: "Cost of living",
      sublabel: "BEA price index, US = 100 (comparable within a year)",
      get: (s, i) => s.rpp_all?.[i] ?? null,
      format: (v) => (v == null ? "No data" : `${v.toFixed(1)} (US = 100)`),
      tick: (v) => v.toFixed(0),
      heightFloor: 80,
      levels: ["states"],
    },
  ];
}

/** First/last year index where any record has a value for this metric. */
export function yearRange(metric, records, years) {
  const has = years.map((_, i) => records.some((s) => metric.get(s, i) != null));
  return [has.indexOf(true), has.lastIndexOf(true)];
}

/** Value at a fractional year index, linearly interpolated between years. */
export function valueAt(metric, s, t) {
  const i0 = Math.floor(t);
  const a = metric.get(s, i0);
  const f = t - i0;
  if (f < 1e-6) return a;
  const b = metric.get(s, i0 + 1);
  if (a == null) return f > 0.5 ? b : null;
  if (b == null) return f < 0.5 ? a : null;
  return a + (b - a) * f;
}
