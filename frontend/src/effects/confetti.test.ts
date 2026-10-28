import { afterEach, describe, expect, it, vi } from "vitest";
import { burst } from "./confetti";

type Frame = () => void;
let frames: Frame[] = [];

function stubMotion(reduced: boolean) {
  vi.stubGlobal("matchMedia", () => ({ matches: reduced }));
}

function stubRaf() {
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (cb: Frame) => {
    frames.push(cb);
    return frames.length;
  });
}

/** jsdom has no native 2d context without the optional `canvas` package. */
function stubCanvas() {
  const ctx = {
    clearRect: () => {},
    beginPath: () => {},
    arc: () => {},
    fill: () => {},
    fillRect: () => {},
    fillStyle: "",
    imageSmoothingEnabled: true,
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D,
  );
}

/** Run every scheduled frame, once, and return the next batch. */
function pump(rounds: number) {
  for (let i = 0; i < rounds; i += 1) {
    const batch = frames;
    frames = [];
    batch.forEach((cb) => cb());
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.querySelectorAll("canvas").forEach((node) => node.remove());
});

describe("burst", () => {
  it("does nothing under reduced motion", () => {
    stubMotion(true);
    burst(50);
    expect(document.querySelectorAll("canvas").length).toBe(0);
  });

  it("draws on a canvas and removes it when the particles are gone", () => {
    stubMotion(false);
    stubRaf();
    stubCanvas();
    burst(10);
    pump(1);
    const canvas = document.querySelector("canvas.ui-confetti");
    expect(canvas).not.toBeNull();
    pump(200);
    expect(document.querySelector("canvas.ui-confetti")).toBeNull();
  });
});
