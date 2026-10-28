import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

// jsdom ships no layout, so it ships no scrollIntoView.
Element.prototype.scrollIntoView = vi.fn();

// findByText's default one-second budget races the reveal pacing (useReveal
// keeps the first bubble off screen for about a second), so a loaded runner
// fails the wait after the reveal has already won. Four seconds is the headroom
// the paced waits in this suite already claim explicitly.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  cleanup();
});
