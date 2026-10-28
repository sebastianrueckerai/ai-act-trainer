export type ThemeColors = {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
};

export type Oklch = { l: number; c: number; h: number };
export type Look = "pixel" | "clean";
export type Mode = "light" | "dark";

export const DEFAULT_COLORS: ThemeColors = {
  primary: "#38bdf8",
  secondary: "#16233a",
  accent: "#fbbf24",
  background: "#f8fafc",
};

export const VAR_NAMES = [
  "--c-primary",
  "--c-on-primary",
  "--c-primary-soft",
  "--c-secondary",
  "--c-accent",
  "--c-on-accent",
  "--c-bg",
  "--c-surface",
  "--c-surface-2",
  "--c-border",
  "--c-text",
  "--c-text-dim",
  "--c-success",
  "--c-warning",
  "--c-danger",
  "--c-focus",
] as const;

export type Palette = Record<(typeof VAR_NAMES)[number], string>;

function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [
    parseInt(value.slice(0, 2), 16),
    parseInt(value.slice(2, 4), 16),
    parseInt(value.slice(4, 6), 16),
  ];
}

function rgbToHex(rgb: [number, number, number]): string {
  return (
    "#" +
    rgb
      .map((channel) =>
        Math.round(Math.min(255, Math.max(0, channel)))
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

function srgbToLinear(channel: number): number {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map(srgbToLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(hexA: string, hexB: string): number {
  const la = relativeLuminance(hexA);
  const lb = relativeLuminance(hexB);
  const [lighter, darker] = la > lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

function linearToSrgb(channel: number): number {
  const c = channel <= 0.0031308 ? 12.92 * channel : 1.055 * Math.pow(channel, 1 / 2.4) - 0.055;
  return Math.min(255, Math.max(0, c * 255));
}

// Björn Ottosson's published linear sRGB <-> OKLab matrices
function linearToOklab(rgb: [number, number, number]): [number, number, number] {
  const [r, g, b] = rgb;
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;
  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);
  return [
    0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_,
    1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_,
    0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_,
  ];
}

function oklabToLinear(lab: [number, number, number]): [number, number, number] {
  const [L, a, b] = lab;
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

export function hexToOklch(hex: string): Oklch {
  const linear = hexToRgb(hex).map(srgbToLinear) as [number, number, number];
  const [L, a, b] = linearToOklab(linear);
  const c = Math.sqrt(a * a + b * b);
  let h = (Math.atan2(b, a) * 180) / Math.PI;
  if (h < 0) h += 360;
  return { l: L, c, h };
}

export function oklchToHex(color: Oklch): string {
  const rad = (color.h * Math.PI) / 180;
  const lab: [number, number, number] = [color.l, color.c * Math.cos(rad), color.c * Math.sin(rad)];
  const linear = oklabToLinear(lab);
  return rgbToHex(linear.map(linearToSrgb) as [number, number, number]);
}

export function quantize(color: Oklch): Oklch {
  const c = Math.round(color.c * 100) / 100;
  return {
    l: Math.round(color.l * 50) / 50,
    // A near-white background seed carries less than half a chroma step; rounding
    // it away leaves a grey page beside its own tinted surfaces (D55).
    c: c === 0 && color.c > 0 ? 0.01 : c,
    h: color.h,
  };
}

function mix(a: Oklch, b: Oklch, t: number): Oklch {
  let dh = b.h - a.h;
  if (dh > 180) dh -= 360;
  if (dh < -180) dh += 360;
  return { l: a.l + (b.l - a.l) * t, c: a.c + (b.c - a.c) * t, h: a.h + dh * t };
}

const clamp = (value: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, value));

function onColor(base: Oklch): Oklch {
  return base.l < 0.62 ? { l: 0.97, c: 0.01, h: base.h } : { l: 0.18, c: 0.02, h: base.h };
}

// Scales a color toward or away from black in OKLCH, which keeps its hue and its
// chroma-to-lightness ratio exactly (D55): a step up the ramp, not a wash to grey.
function scaledFrom(base: Oklch, factor: number): Oklch {
  return { l: clamp(base.l * factor, 0.02, 0.98), c: base.c * factor, h: base.h };
}

export function derivePalette(colors: ThemeColors, mode: Mode, look: Look): Palette {
  const pixel = look === "pixel";
  // the sprite art carries no baked fill, so both looks follow the mode (D42)
  const dark = mode === "dark";

  const bgSource = hexToOklch(colors.background);
  const primary = hexToOklch(colors.primary);
  const secondary = hexToOklch(colors.secondary);
  const accent = hexToOklch(colors.accent);

  // Dark mode steps up from the secondary seed itself (D55), not the light background,
  // so a customer's seed shows in the dark surfaces instead of washing to grey. Light
  // mode keeps `bg` on the background seed, but the near-zero chroma of a white-ish
  // background would wash light surfaces to grey too, so they borrow the secondary's
  // hue at a small chroma instead, the same idea as D55 for the other end of the ramp.
  const bg: Oklch = dark ? scaledFrom(secondary, 0.71) : bgSource;
  const lightTint = (l: number, c: number): Oklch => ({ l: clamp(l, 0.02, 0.98), c, h: secondary.h });
  const surface = dark ? scaledFrom(secondary, 0.86) : lightTint(bg.l - 0.04, 0.02);
  const surface2 = dark ? scaledFrom(secondary, 1.02) : lightTint(bg.l - 0.08, 0.025);
  const border = dark ? scaledFrom(secondary, 1.39) : lightTint(bg.l - 0.18, 0.03);
  const text =
    bg.l < 0.62
      ? { l: clamp(bg.l + 0.7, 0.85, 0.97), c: bg.c * 0.5, h: bg.h }
      : { l: clamp(bg.l - 0.45, 0.1, 0.3), c: bg.c * 0.5 + 0.01, h: bg.h };
  // dim enough to recede, bright enough for a footnote in the pixel font
  const textDim = mix(text, bg, 0.3);
  const focus = { ...accent, l: clamp(accent.l + (accent.l < 0.62 ? 0.3 : -0.3), 0.05, 0.95) };

  const finish = (color: Oklch): string => oklchToHex(pixel ? quantize(color) : color);

  return {
    "--c-primary": finish(primary),
    "--c-on-primary": finish(onColor(primary)),
    "--c-primary-soft": finish(mix(primary, bg, 0.85)),
    "--c-secondary": finish(secondary),
    "--c-accent": finish(accent),
    "--c-on-accent": finish(onColor(accent)),
    "--c-bg": finish(bg),
    "--c-surface": finish(surface),
    "--c-surface-2": finish(surface2),
    "--c-border": finish(border),
    "--c-text": finish(text),
    "--c-text-dim": finish(textDim),
    "--c-success": finish({ l: 0.68, c: 0.13, h: 150 }),
    "--c-warning": finish({ l: 0.84, c: 0.16, h: 88 }),
    "--c-danger": finish({ l: 0.6, c: 0.2, h: 27 }),
    "--c-focus": finish(focus),
  };
}
