import { describe, expect, it } from "vitest";
import {
  DEFAULT_COLORS,
  VAR_NAMES,
  contrastRatio,
  derivePalette,
  hexToOklch,
  oklchToHex,
  quantize,
  type Oklch,
} from "./palette";

describe("oklch round trips", () => {
  it("passes grey through unchanged", () => {
    expect(oklchToHex(hexToOklch("#808080"))).toBe("#808080");
  });

  it("matches the published anchors for pure red", () => {
    const red = hexToOklch("#ff0000");
    expect(red.l).toBeCloseTo(0.628, 2);
    expect(red.c).toBeCloseTo(0.258, 2);
    expect(red.h).toBeCloseTo(29.23, 1);
  });
});

describe("quantize", () => {
  it("snaps lightness to 0.02 and chroma to 0.01", () => {
    expect(quantize({ l: 0.628, c: 0.258, h: 29 })).toEqual({ l: 0.62, c: 0.26, h: 29 });
  });

  it("holds a chroma under half a step at one step instead of washing it to grey", () => {
    // #f8fafc's own chroma, which the rounding alone would take to 0.00
    expect(quantize({ l: 0.9842, c: 0.0034, h: 247.86 })).toEqual({ l: 0.98, c: 0.01, h: 247.86 });
    expect(quantize({ l: 0.5, c: 0, h: 0 }).c).toBe(0);
  });
});

describe("derivePalette", () => {
  it("returns all 15 keys as hex colors", () => {
    const palette = derivePalette(DEFAULT_COLORS, "light", "clean");
    expect(Object.keys(palette).sort()).toEqual([...VAR_NAMES].sort());
    for (const value of Object.values(palette)) {
      expect(value).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it("keeps surfaces lighter than the background in dark mode and darker in light mode", () => {
    const dark = derivePalette(DEFAULT_COLORS, "dark", "clean");
    const light = derivePalette(DEFAULT_COLORS, "light", "clean");
    expect(hexToOklch(dark["--c-surface"]).l).toBeGreaterThan(hexToOklch(dark["--c-bg"]).l);
    expect(hexToOklch(light["--c-surface"]).l).toBeLessThan(hexToOklch(light["--c-bg"]).l);
  });

  it("quantizes chroma and lightness in the pixel look and leaves the clean look alone", () => {
    // reading a colour back out of its 8-bit hex shifts l and c by a few ten-thousandths,
    // well under half the lattice step, so the check is to three decimals
    const pixel = hexToOklch(derivePalette(DEFAULT_COLORS, "light", "pixel")["--c-primary"]);
    expect(pixel.l).toBeCloseTo(Math.round(pixel.l * 50) / 50, 3);
    expect(pixel.c).toBeCloseTo(Math.round(pixel.c * 100) / 100, 3);

    const clean = hexToOklch(derivePalette(DEFAULT_COLORS, "light", "clean")["--c-primary"]);
    expect(clean.l).not.toBeCloseTo(Math.round(clean.l * 50) / 50, 3);
    expect(clean.c).not.toBeCloseTo(Math.round(clean.c * 100) / 100, 3);
  });

  it("picks light text on dark colors and dark text on light colors", () => {
    // both Tiefsee seeds sit above the flip, so a dark stand-in exercises the other branch
    const palette = derivePalette({ ...DEFAULT_COLORS, primary: "#16233a" }, "light", "clean");
    expect(hexToOklch(palette["--c-on-primary"]).l).toBeGreaterThan(0.8);
    expect(hexToOklch(palette["--c-on-accent"]).l).toBeLessThan(0.4);
  });

  it("reads the text lightness off a dark background even on a light system", () => {
    // #0f172a is l=0.2077, so the text sits at 0.2077 + 0.7, inside the 0.85..0.97 clamp
    const palette = derivePalette({ ...DEFAULT_COLORS, background: "#0f172a" }, "light", "clean");
    expect(hexToOklch(palette["--c-bg"]).l).toBeCloseTo(0.2077, 2);
    expect(hexToOklch(palette["--c-text"]).l).toBeCloseTo(0.9077, 2);
  });

  it("darkens both looks in dark mode, because no sprite carries a fill", () => {
    // the sprites are outlines and bands on transparency, so the pixel look follows
    // the mode like the clean one (D42)
    const pixelDark = derivePalette(DEFAULT_COLORS, "dark", "pixel");
    expect(pixelDark["--c-bg"]).toBe("#0a121f");
    expect(pixelDark["--c-text"]).toBe("#d0d8e5");
    expect(derivePalette(DEFAULT_COLORS, "light", "pixel")["--c-bg"]).toBe("#f3f9ff");
    expect(derivePalette(DEFAULT_COLORS, "dark", "clean")).not.toEqual(
      derivePalette(DEFAULT_COLORS, "light", "clean"),
    );
  });

  it("shifts the focus ring away from the accent it rings", () => {
    // #fbbf24 is l=0.8369, above the 0.62 flip, so the ring drops 0.3 to 0.5369
    const palette = derivePalette(DEFAULT_COLORS, "light", "clean");
    expect(palette["--c-focus"]).not.toBe(palette["--c-accent"]);
    expect(hexToOklch(palette["--c-accent"]).l).toBeCloseTo(0.8369, 2);
    expect(hexToOklch(palette["--c-focus"]).l).toBeCloseTo(0.5369, 2);
  });

  it("derives the dark pixel ramp from the secondary seed, within 0.03 of the hand-picked hex (D55)", () => {
    // only bg/surface/surface2/border change formula under D55; #0b1220 is the one
    // anchor recorded in the round notes, the rest are hand-derived by the same formula
    const distance = (a: Oklch, b: Oklch): number => {
      const toLab = (c: Oklch): [number, number, number] => {
        const rad = (c.h * Math.PI) / 180;
        return [c.l, c.c * Math.cos(rad), c.c * Math.sin(rad)];
      };
      const [al, aa, ab] = toLab(a);
      const [bl, ba, bb] = toLab(b);
      return Math.sqrt((al - bl) ** 2 + (aa - ba) ** 2 + (ab - bb) ** 2);
    };
    const palette = derivePalette(DEFAULT_COLORS, "dark", "pixel");
    const targets: Partial<Record<keyof typeof palette, string>> = {
      "--c-bg": "#0b1220",
      "--c-surface": "#101a2d",
      "--c-surface-2": "#16243c",
      "--c-border": "#283d62",
    };
    for (const [key, hex] of Object.entries(targets) as [keyof typeof palette, string][]) {
      expect(distance(hexToOklch(palette[key]), hexToOklch(hex))).toBeLessThan(0.03);
    }
  });

  it("tints the light pixel surfaces and border with the secondary seed's hue, not the near-grey background", () => {
    // the raw background (#f8fafc) sits at h=247.86, c=0.0034, far too little chroma
    // to carry a surface ramp, so light surfaces borrow the secondary's hue (261.22)
    // instead, within a tolerance well short of the 13.4° gap to bg's own
    const palette = derivePalette(DEFAULT_COLORS, "light", "pixel");
    const secondaryHue = hexToOklch(DEFAULT_COLORS.secondary).h;
    for (const key of ["--c-surface", "--c-border"] as const) {
      expect(Math.abs(hexToOklch(palette[key]).h - secondaryHue)).toBeLessThan(5);
    }
  });

  it("keeps the light pixel background tinted, not grey beside its own surfaces", () => {
    // the chroma floor in quantize holds bg at one step with the background seed's
    // own hue; without it the page is #f8f8f8, grey under blue surfaces
    const bg = hexToOklch(derivePalette(DEFAULT_COLORS, "light", "pixel")["--c-bg"]);
    expect(bg.c).toBeGreaterThan(0.008);
    expect(Math.abs(bg.h - hexToOklch(DEFAULT_COLORS.background).h)).toBeLessThan(1);
  });

  it("keeps the name-plate accent readable in both modes (WCAG AA, >= 4.5:1)", () => {
    const light = derivePalette(DEFAULT_COLORS, "light", "pixel");
    const dark = derivePalette(DEFAULT_COLORS, "dark", "pixel");
    expect(contrastRatio(light["--c-accent"], light["--c-on-accent"])).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(dark["--c-accent"], dark["--c-on-accent"])).toBeGreaterThanOrEqual(4.5);
  });
});
