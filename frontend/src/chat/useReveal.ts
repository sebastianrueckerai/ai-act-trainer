import { useCallback, useEffect, useRef, useState } from "react";

// A turn arrives one bubble at a time, at the speed the student reads it (D97). The
// numbers come from a slow, comfortable read of about 1.8 words a second: the floor
// keeps a one-word bubble from flashing past, the cap keeps a long one from stalling.
const BASE_MS = 900;
const PER_WORD_MS = 33;
const CAP_MS = 3600;

export function pauseFor(paragraph: string): number {
  return Math.min(CAP_MS, BASE_MS + PER_WORD_MS * paragraph.trim().split(/\s+/).length);
}

function instant(): boolean {
  // No way to ask is no licence to animate: a host without matchMedia shows the turn whole.
  if (typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * How much of the turn in progress is on screen.
 *
 * `paragraphs` is whatever exists so far — the streamed text while it grows, the settled
 * message once it lands — so the reveal paces the stream itself instead of flashing it
 * whole and starting over. `turn` identifies the turn (it changes when a new one begins);
 * across a change of paragraphs within the same turn the reveal keeps what it has. A
 * click anywhere in the thread calls `revealAll`: nobody is made to wait for text they
 * have already read. `hold` freezes the count while the confetti plays: nothing new
 * shows, and the pacing picks up where it stopped.
 */
export function useReveal(turn: unknown, paragraphs: string[], hold = false) {
  const [revealed, setRevealed] = useState(0);
  const [seen, setSeen] = useState<{ turn: unknown }>({ turn: undefined });
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const total = paragraphs.length;

  // A turn starts behind the dots: when the turn changes, the count drops to zero
  // and the first bubble paces in like every later one, so no box ever pops in
  // whole. Reduced motion shows everything at once. Starting in render, not in an
  // effect, keeps the previous turn's count from painting on the new one for a frame.
  if (seen.turn !== turn) {
    setSeen({ turn });
    setRevealed(total > 0 && instant() ? total : 0);
  } else if (revealed === 0 && total > 0 && instant()) {
    setRevealed(total);
  }

  // The pause waits for the paragraph about to appear — the first one included, so
  // even a reply that lands whole arrives typed, not popped. A growing stream must
  // not restart it — only reaching for a new paragraph (or one arriving while caught
  // up) re-arms — so the paragraph text is deliberately not a dependency.
  useEffect(() => {
    if (hold || instant() || revealed >= total) return;
    timer.current = setTimeout(() => setRevealed((n) => n + 1), pauseFor(paragraphs[revealed] ?? ""));
    return () => clearTimeout(timer.current);
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [revealed, total, hold]);

  const revealAll = useCallback(() => {
    clearTimeout(timer.current);
    setRevealed(total);
  }, [total]);

  return { revealed, revealing: revealed < total, revealAll };
}
