// Heat ramp: green (low) -> yellow -> orange -> red (high). Same ramp in light
// and dark mode. Height always encodes the same value as color, so readers who
// can't separate red from green still get the magnitude.

const STOPS = ["#1a9850", "#66bd63", "#a6d96a", "#fee08b", "#fdae61", "#f46d43", "#d73027"];

const hexToRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const RGB = STOPS.map(hexToRgb);

/** t in [0,1] -> [r,g,b] in 0..1 (sRGB). */
export function ramp(t) {
  t = Math.min(1, Math.max(0, t));
  const x = t * (RGB.length - 1);
  const i = Math.min(RGB.length - 2, Math.floor(x));
  const f = x - i;
  return RGB[i].map((c, k) => c + (RGB[i + 1][k] - c) * f);
}

export const cssRgb = (rgb) => `rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})`;

/** CSS linear-gradient for the legend bar. */
export function rampGradient() {
  const stops = [];
  for (let k = 0; k <= 12; k++) stops.push(`${cssRgb(ramp(k / 12))} ${((k / 12) * 100).toFixed(1)}%`);
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

export const cssVar = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();
