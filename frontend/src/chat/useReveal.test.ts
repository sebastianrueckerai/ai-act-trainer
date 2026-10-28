import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pauseFor, useReveal } from "./useReveal";

const THREE = ["Ein Satz.", "Noch einer, etwas laenger als der erste.", "Und der dritte."];

function paced(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches, media: "", addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

describe("useReveal", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows one paragraph, then the next, at the pace of the one about to appear", () => {
    paced(false);
    const { result } = renderHook(() => useReveal(0, THREE));

    // The turn starts behind the dots: the first bubble owes its own beat.
    expect(result.current.revealed).toBe(0);
    expect(result.current.revealing).toBe(true);

    act(() => void vi.advanceTimersByTime(pauseFor(THREE[0])));
    expect(result.current.revealed).toBe(1);

    act(() => void vi.advanceTimersByTime(pauseFor(THREE[1])));
    expect(result.current.revealed).toBe(2);

    act(() => void vi.advanceTimersByTime(pauseFor(THREE[2])));
    expect(result.current.revealed).toBe(3);
    expect(result.current.revealing).toBe(false);
  });

  it("paces a stream as it grows, and carries what it showed into the settled message", () => {
    paced(false);
    const { result, rerender } = renderHook(({ turn, paragraphs }) => useReveal(turn, paragraphs), {
      initialProps: { turn: 0, paragraphs: THREE.slice(0, 1) },
    });

    expect(result.current.revealed).toBe(0);
    expect(result.current.revealing).toBe(true);

    act(() => void vi.advanceTimersByTime(pauseFor(THREE[0])));
    expect(result.current.revealed).toBe(1);
    expect(result.current.revealing).toBe(false);

    // More of the stream arrives: the pace holds, nothing jumps ahead.
    rerender({ turn: 0, paragraphs: THREE });
    expect(result.current.revealed).toBe(1);

    act(() => void vi.advanceTimersByTime(pauseFor(THREE[1])));
    expect(result.current.revealed).toBe(2);

    // The stream settles into the message: the same turn keeps its count.
    rerender({ turn: 0, paragraphs: [...THREE, "Ein vierter."] });
    expect(result.current.revealed).toBe(2);
    expect(result.current.revealing).toBe(true);
  });

  it("starts the next turn behind the dots", () => {
    paced(false);
    const { result, rerender } = renderHook(({ turn, paragraphs }) => useReveal(turn, paragraphs), {
      initialProps: { turn: 0, paragraphs: THREE },
    });

    act(() => result.current.revealAll());
    expect(result.current.revealed).toBe(3);

    rerender({ turn: 1, paragraphs: ["Neue Runde.", "Ganz anders."] });
    expect(result.current.revealed).toBe(0);
    expect(result.current.revealing).toBe(true);

    act(() => void vi.advanceTimersByTime(pauseFor("Neue Runde.")));
    expect(result.current.revealed).toBe(1);
  });

  it("shows the whole turn at once when motion is not wanted", () => {
    paced(true);
    const { result } = renderHook(() => useReveal(0, THREE));

    expect(result.current.revealed).toBe(3);
    expect(result.current.revealing).toBe(false);
  });

  it("shows the rest at once when the student asks for it", () => {
    paced(false);
    const { result } = renderHook(() => useReveal(0, THREE));

    act(() => result.current.revealAll());

    expect(result.current.revealed).toBe(3);
    expect(result.current.revealing).toBe(false);
  });

  it("paces a short paragraph by its floor and a long one by its cap", () => {
    expect(pauseFor("Ja.")).toBe(933);
    expect(pauseFor("Wort ".repeat(200))).toBe(3600);
  });
});
