import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { tolgee } from "../i18n";
import { stageFixture } from "../stage/fixture";
import { CourseStatus } from "./CourseStatus";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const cellStates = () =>
  Array.from(document.querySelectorAll(".ui-cell")).map((cell) => cell.getAttribute("data-state"));

function withCurrentStep(step: number) {
  const chapters = stageFixture.chapters.map((chapter) =>
    chapter.state === "current" ? { ...chapter, step } : chapter,
  );
  return { ...stageFixture, chapters };
}

describe("CourseStatus", () => {
  it("always shows the chapter count", async () => {
    render(withProvider(<CourseStatus stage={stageFixture} />));
    expect(await screen.findByText("Kapitel 2 von 3")).toBeInTheDocument();
  });

  it("counts the chapter marked current, not the chapters already done", async () => {
    const chapters = [
      { id: "01-a", title: "Erstes", stub: false, state: "done" as const, steps: 4, step: null },
      { id: "02-b", title: "Zweites", stub: false, state: "done" as const, steps: 4, step: null },
      { id: "03-c", title: "Drittes", stub: false, state: "current" as const, steps: 4, step: 0 },
      { id: "04-d", title: "Viertes", stub: true, state: "locked" as const, steps: 4, step: null },
    ];
    render(withProvider(<CourseStatus stage={{ ...stageFixture, chapters }} />));
    expect(await screen.findByText("Kapitel 3 von 4")).toBeInTheDocument();
  });

  it("stays on the last chapter, full and flag up, once none is marked current", async () => {
    // after the last chapter the backend marks every chapter done and none current
    const chapters = [
      { id: "01-a", title: "Erstes", stub: false, state: "done" as const, steps: 4, step: null },
      { id: "02-b", title: "Zweites", stub: false, state: "done" as const, steps: 5, step: null },
    ];
    render(withProvider(<CourseStatus stage={{ ...stageFixture, chapters }} />));
    expect(await screen.findByText("Kapitel 2 von 2")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 5 von 5");
    expect(cellStates()).toEqual(["done", "done", "done", "done", "done"]);
    expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "up");
  });

  it("draws the current chapter's steps as cells with the flag at the end", async () => {
    render(withProvider(<CourseStatus stage={stageFixture} />));
    await screen.findByText("Kapitel 2 von 3");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 3 von 6");
    expect(cellStates()).toEqual(["done", "done", "now", "ahead", "ahead", "ahead"]);
    expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "down");
    expect(document.querySelector(".ui-cell[data-flash]")).toBeNull();
  });

  it("flashes the step just done for 1800 ms", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(withProvider(<CourseStatus stage={stageFixture} />));
      rerender(withProvider(<CourseStatus stage={withCurrentStep(3)} />));
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 4 von 6");
      expect(cellStates()).toEqual(["done", "done", "done", "now", "ahead", "ahead"]);
      const flashing = () => Array.from(document.querySelectorAll(".ui-cell[data-flash]"));
      expect(flashing()).toEqual([document.querySelectorAll(".ui-cell")[2]]);
      act(() => vi.advanceTimersByTime(1799));
      expect(flashing()).toHaveLength(1);
      act(() => vi.advanceTimersByTime(1));
      expect(flashing()).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps a finished chapter full, flag hoisted, until the click opens the next one", () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(withProvider(<CourseStatus stage={withCurrentStep(5)} />));
      // The chapter end: the chapter is done and none is current while the button waits.
      const waiting = {
        ...stageFixture,
        chapters: [
          stageFixture.chapters[0],
          { ...stageFixture.chapters[1], state: "done" as const, step: null },
          stageFixture.chapters[2],
        ],
      };
      rerender(withProvider(<CourseStatus stage={waiting} />));
      expect(screen.getByText("Kapitel 2 von 3")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 6 von 6");
      expect(cellStates()).toEqual(["done", "done", "done", "done", "done", "done"]);
      expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "up");
      expect(document.querySelector(".ui-flag")).toHaveClass("ui-flag--hoist");
      expect(document.querySelectorAll(".ui-cell")[5]).toHaveAttribute("data-flash");
      act(() => vi.advanceTimersByTime(60_000));
      expect(screen.getByText("Kapitel 2 von 3")).toBeInTheDocument();
      expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "up");

      const next = {
        ...waiting,
        chapters: [
          waiting.chapters[0],
          waiting.chapters[1],
          { ...stageFixture.chapters[2], state: "current" as const, step: 0 },
        ],
      };
      rerender(withProvider(<CourseStatus stage={next} />));
      expect(screen.getByText("Kapitel 3 von 3")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 1 von 4");
      expect(cellStates()).toEqual(["now", "ahead", "ahead", "ahead"]);
      expect(document.querySelector(".ui-flag")).toHaveAttribute("data-state", "down");
      expect(document.querySelector(".ui-cell[data-flash]")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the test's answers on the same cells during the test", async () => {
    const stage = {
      ...stageFixture,
      attempt: { kind: "test" as const, index: 0, results: [true, false], total: 3 },
    };
    render(withProvider(<CourseStatus stage={stage} />));
    expect(await screen.findByText("Test")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "1 von 3 richtig");
    expect(cellStates()).toEqual(["ok", "wrong", "ahead"]);
    expect(document.querySelector(".ui-flag")).toBeNull();
  });

  it("names no chapter during the graded test, which covers all of them", async () => {
    const stage = {
      ...stageFixture,
      attempt: { kind: "test" as const, index: 0, results: [true, false], total: 3 },
    };
    render(withProvider(<CourseStatus stage={stage} />));
    await screen.findByText("Test");
    expect(screen.queryByText("Kapitel 2 von 3")).not.toBeInTheDocument();
  });

  it("shows a step's own question as part of the chapter, on the chapter's bar", async () => {
    const stage = {
      ...stageFixture,
      attempt: { kind: "practice" as const, index: 0, results: [], total: 1 },
    };
    render(withProvider(<CourseStatus stage={stage} />));
    expect(await screen.findByText("Kapitel 2 von 3")).toBeInTheDocument();
    expect(screen.queryByText("Übung")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Schritt 3 von 6");
  });

  it("hides the streak badge at or below a streak of one", async () => {
    render(withProvider(<CourseStatus stage={{ ...stageFixture, streak: 1 }} />));
    await screen.findByText("Kapitel 2 von 3");
    expect(screen.queryByText("1 richtig in Folge")).not.toBeInTheDocument();
  });

  it("shows the streak badge above a streak of one", async () => {
    render(withProvider(<CourseStatus stage={{ ...stageFixture, streak: 4 }} />));
    expect(await screen.findByText("4 richtig in Folge")).toBeInTheDocument();
  });

  it("shows no restart confirmation unless told to", async () => {
    render(withProvider(<CourseStatus stage={stageFixture} />));
    await screen.findByText("Kapitel 2 von 3");
    expect(screen.queryByText("Kurs wirklich von vorn beginnen?")).not.toBeInTheDocument();
  });

  it("renders the restart confirmation when confirming", async () => {
    render(withProvider(<CourseStatus stage={stageFixture} confirming />));
    expect(await screen.findByText("Kurs wirklich von vorn beginnen?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ja, von vorn" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abbrechen" })).toBeInTheDocument();
  });

  it("calls onConfirm when the restart is accepted", async () => {
    const onConfirm = vi.fn();
    render(withProvider(<CourseStatus stage={stageFixture} confirming onConfirm={onConfirm} />));
    await userEvent.click(await screen.findByRole("button", { name: "Ja, von vorn" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when the restart is dismissed", async () => {
    const onCancel = vi.fn();
    render(withProvider(<CourseStatus stage={stageFixture} confirming onCancel={onCancel} />));
    await userEvent.click(await screen.findByRole("button", { name: "Abbrechen" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
