import type { Stage } from "../api/chat";

export const stageFixture: Stage = {
  persona: null,
  mood: "neutral",
  streak: 0,
  chapters: [
    { id: "01-a", title: "Erstes Kapitel", stub: false, state: "done", steps: 4, step: null },
    { id: "02-b", title: "Zweites Kapitel", stub: false, state: "current", steps: 6, step: 2 },
    { id: "03-c", title: "Drittes Kapitel", stub: true, state: "locked", steps: 4, step: null },
  ],
  attempt: null,
};
