import { describe, expect, it } from "vitest";
import type { InputHint } from "../api/chat";
import { stageFixture } from "../stage/fixture";
import { EMPTY, reducer } from "./state";

const hint: InputHint = { kind: "text", choices: [], asks: false };

function boot(sessionHint: InputHint): ReturnType<typeof reducer> {
  return reducer(EMPTY, {
    type: "hydrate",
    session: {
      id: 1,
      persona_id: "clerk",
      phase: "lesson",
      display_locale: "de",
      hint: sessionHint,
      messages: [],
      stage: stageFixture,
      budget: { state: "ok" },
    },
  });
}

describe("chat state", () => {
  it("hydrates from a session response", () => {
    const state = reducer(EMPTY, {
      type: "hydrate",
      session: {
        id: 1,
        persona_id: "clerk",
        phase: "lesson",
        display_locale: "de",
        hint: { kind: "yes_no", choices: [], asks: false },
        messages: [{ role: "assistant", text: "Willkommen.", parts: [], translating: false }],
        stage: stageFixture,
        budget: { state: "ok" },
      },
    });
    expect(state.messages).toHaveLength(1);
    expect(state.hint.kind).toBe("yes_no");
    expect(state.streaming).toBe("");
    expect(state.stage).toEqual(stageFixture);
  });

  it("appends the user bubble and marks the turn as sending", () => {
    let state = boot(hint);
    state = reducer(state, { type: "user_message", text: "Was gilt für KI-Systeme?" });
    expect(state.messages).toEqual([{ role: "user", text: "Was gilt für KI-Systeme?", parts: [] }]);
    state = reducer(state, { type: "sending" });
    expect(state.sending).toBe(true);
  });

  it("accumulates tokens and finalizes on message", () => {
    let state = boot(hint);
    state = reducer(state, { type: "user_message", text: "Hallo" });
    state = reducer(state, { type: "sending" });
    state = reducer(state, { type: "event", event: { event: "token", text: "Gu" } });
    state = reducer(state, { type: "event", event: { event: "token", text: "ten Tag" } });
    expect(state.streaming).toBe("Guten Tag");
    state = reducer(state, {
      type: "event",
      event: {
        event: "message",
        translating: false,
        text: "Guten Tag!",
        parts: [],
        hint: { kind: "choices", choices: [{ key: "clerk", label: "Buchhaltung" }], asks: false },
      },
    });
    expect(state.messages.at(-1)).toMatchObject({
      role: "assistant",
      text: "Guten Tag!",
      parts: [],
    });
    expect(state.streaming).toBe("");
    expect(state.hint.kind).toBe("choices");
    expect(state.sending).toBe(false);
  });

  it("adopts an input_hint event", () => {
    const state = reducer(boot(hint), {
      type: "event",
      event: { event: "input_hint", hint: { kind: "confirm", asks: false } },
    });
    expect(state.hint.kind).toBe("confirm");
  });

  it("records an error event and drops the half-written answer", () => {
    let state = reducer(boot(hint), { type: "event", event: { event: "token", text: "Gu" } });
    expect(state.streaming).toBe("Gu");
    state = reducer(state, {
      type: "event",
      event: { event: "error", code: "turn_failed", message: "x" },
    });
    expect(state.error).not.toBe("");
    expect(state.sending).toBe(false);
    expect(state.streaming).toBe("");
  });

  it("takes a limit event's budget instead of an error line, and drops the half-written answer", () => {
    let state = reducer(boot(hint), { type: "sending" });
    state = reducer(state, { type: "event", event: { event: "token", text: "Gu" } });
    const budget = {
      state: "exhausted" as const,
      scope: "pool_day" as const,
      resets_at: "2026-10-12T00:00:00Z",
    };
    state = reducer(state, {
      type: "event",
      event: { event: "error", code: "limit", message: "chat.limit", budget },
    });
    expect(state.budget).toEqual(budget);
    expect(state.error).toBe("");
    expect(state.sending).toBe(false);
    expect(state.streaming).toBe("");
  });

  it("hydrates the session's budget and lifts it on a budget action", () => {
    const exhausted = {
      state: "exhausted" as const,
      scope: "day" as const,
      resets_at: "2026-10-12T00:00:00Z",
    };
    let state = reducer(EMPTY, {
      type: "hydrate",
      session: {
        id: 1,
        persona_id: "clerk",
        phase: "lesson",
        display_locale: "de",
        hint,
        messages: [],
        stage: stageFixture,
        budget: exhausted,
      },
    });
    expect(state.budget).toEqual(exhausted);
    state = reducer(state, { type: "budget", budget: { state: "ok" } });
    expect(state.budget).toEqual({ state: "ok" });
  });

  it("keeps a refusal through a flag flip, whose session knows nothing of seats", () => {
    const seats = { state: "exhausted" as const, scope: "seats" as const, resets_at: null };
    let state = reducer(boot(hint), {
      type: "event",
      event: { event: "error", code: "limit", message: "chat.limit", budget: seats },
    });
    state = reducer(state, {
      type: "retext",
      session: {
        id: 1,
        persona_id: "clerk",
        phase: "lesson",
        display_locale: "en",
        hint,
        messages: [],
        stage: stageFixture,
        budget: { state: "ok" },
      },
    });
    expect(state.budget).toEqual(seats);
  });

  it("ignores status, ui and part events", () => {
    const state = boot(hint);
    expect(
      reducer(state, { type: "event", event: { event: "status", node: "triage" } }),
    ).toBe(state);
    expect(
      reducer(state, { type: "event", event: { event: "ui", name: "progress" } }),
    ).toBe(state);
    expect(
      reducer(state, {
        type: "event",
        event: {
          event: "part",
          part: {
            kind: "citations",
            ref: "Art. 4",
            title: "AI-Kompetenz",
            quote: "…",
            url: "https://example.com",
          },
        },
      }),
    ).toBe(state);
  });

  it("resets to the empty state, dropping messages and stage", () => {
    let state = boot(hint);
    state = reducer(state, { type: "user_message", text: "Was gilt für KI-Systeme?" });
    expect(state.messages).not.toHaveLength(0);
    state = reducer(state, { type: "reset" });
    expect(state).toEqual(EMPTY);
  });

  it("adopts stage ui events and leaves other ui events alone", () => {
    let state = boot(hint);
    const stage = {
      ...stageFixture,
      persona: { id: "marvin", name: "Marvin", image_url: null },
      streak: 3,
    };
    state = reducer(state, {
      type: "event",
      event: { event: "ui", name: "stage", payload: stage },
    });
    expect(state.stage?.persona?.name).toBe("Marvin");
    expect(state.stage?.streak).toBe(3);
    state = reducer(state, {
      type: "event",
      event: { event: "ui", name: "progress", payload: {} },
    });
    expect(state.stage?.streak).toBe(3);
  });
});

describe("a flag flip retexts the thread", () => {
  const session = {
    id: 1,
    persona_id: "clerk",
    phase: "lesson",
    display_locale: "en",
    hint,
    stage: stageFixture,
    budget: { state: "ok" as const },
  };

  it("swaps each message's text in place and leaves the turn in flight alone", () => {
    let state = boot(hint);
    state = reducer(state, {
      type: "event",
      event: { event: "message", id: "m1", translating: false, text: "Guten Tag.", parts: [], hint },
    });
    state = reducer(state, { type: "user_message", text: "weiter" });
    state = reducer(state, { type: "sending" });
    state = reducer(state, { type: "event", event: { event: "token", text: "Ein" } });

    const flipped = reducer(state, {
      type: "retext",
      session: {
        ...session,
        messages: [
          { id: "m1", role: "assistant", text: "Good day.", parts: [], translating: false },
          { role: "user", text: "weiter", parts: [], translating: false },
        ],
      },
    });

    expect(flipped.messages.map((message) => message.text)).toEqual(["Good day.", "weiter"]);
    expect(flipped.streaming).toBe("Ein");
    expect(flipped.sending).toBe(true);
    expect(flipped.hint).toEqual(hint);
  });

  it("keeps a message the client already has that the server response lacks", () => {
    let state = boot(hint);
    state = reducer(state, {
      type: "event",
      event: { event: "message", id: "m1", translating: false, text: "Guten Tag.", parts: [], hint },
    });
    state = reducer(state, { type: "user_message", text: "weiter" });

    const flipped = reducer(state, {
      type: "retext",
      session: {
        ...session,
        messages: [{ id: "m1", role: "assistant", text: "Guten Tag.", parts: [], translating: true }],
      },
    });

    expect(flipped.messages.map((message) => message.text)).toEqual(["Guten Tag.", "weiter"]);
    expect(flipped.messages[0].translating).toBe(true);
    expect(flipped.messages[1].translating).toBeFalsy();
  });

  it("matches messages by id, so a compacted server list retexts the right bubbles", () => {
    let state = boot(hint);
    state = reducer(state, {
      type: "event",
      event: { event: "message", id: "m1", text: "Erstens.", parts: [], hint, translating: false },
    });
    state = reducer(state, { type: "user_message", text: "weiter" });
    state = reducer(state, {
      type: "event",
      event: { event: "message", id: "m2", text: "Zweitens.", parts: [], hint, translating: false },
    });

    // The server compacted the first turn away and renders only what it still holds.
    const flipped = reducer(state, {
      type: "retext",
      session: {
        ...session,
        messages: [{ id: "m2", role: "assistant", text: "Second.", parts: [], hint: null, translating: false }],
      },
    });

    expect(flipped.messages.map((message) => message.text)).toEqual(["Erstens.", "weiter", "Second."]);
    expect(flipped.messages[0].id).toBe("m1");
  });

  it("carries a settled message's id, hint and translating mark from the event", () => {
    const state = reducer(boot(hint), {
      type: "event",
      event: { event: "message", id: "m9", text: "Noch deutsch.", parts: [], hint, translating: true },
    });
    expect(state.messages[0]).toMatchObject({ id: "m9", hint, translating: true });
  });

  it("takes the session's hint when no turn is in flight, and keeps it during one", () => {
    const enHint: InputHint = {
      kind: "choices",
      choices: [{ key: "a", label: "Yes, I may." }],
      asks: true,
    };
    let idle = boot(hint);
    idle = reducer(idle, {
      type: "event",
      event: { event: "message", id: "m1", translating: false, text: "Darf ich?", parts: [], hint },
    });
    const flippedIdle = reducer(idle, {
      type: "retext",
      session: {
        ...session,
        hint: enHint,
        messages: [
          { id: "m1", role: "assistant", text: "May I?", parts: [], hint: enHint, translating: false },
        ],
      },
    });
    expect(flippedIdle.hint).toEqual(enHint);
    expect(flippedIdle.messages[0].hint).toEqual(enHint);

    const busy = reducer(idle, { type: "sending" });
    const flippedBusy = reducer(busy, {
      type: "retext",
      session: { ...session, hint: enHint, messages: [] },
    });
    expect(flippedBusy.hint).toEqual(hint);
  });
});

describe("the working line", () => {
  it("keeps the step's line from the event until the message lands", () => {
    let state = reducer(boot(hint), { type: "sending" });
    state = reducer(state, {
      type: "event",
      event: { event: "working", step: "grading", text: "prüft deine Antwort" },
    });
    expect(state.working).toBe("prüft deine Antwort");
    state = reducer(state, {
      type: "event",
      event: { event: "working", step: "writing", text: "schreibt die Antwort" },
    });
    expect(state.working).toBe("schreibt die Antwort");
    state = reducer(state, {
      type: "event",
      event: { event: "message", id: "7", text: "Richtig.", parts: [], hint, translating: false },
    });
    expect(state.working).toBe("");
  });

  it("starts every turn without a line and drops it on an error", () => {
    let state = reducer(boot(hint), {
      type: "event",
      event: { event: "working", step: "reading", text: "liest" },
    });
    state = reducer(state, { type: "sending" });
    expect(state.working).toBe("");
    state = reducer(state, {
      type: "event",
      event: { event: "working", step: "reading", text: "liest" },
    });
    state = reducer(state, { type: "event", event: { event: "error", code: "x", message: "x" } });
    expect(state.working).toBe("");
  });
});
