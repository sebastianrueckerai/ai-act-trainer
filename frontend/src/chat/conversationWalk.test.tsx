import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getActiveSession,
  postSession,
  setDisplayLocale,
  streamContinue,
  streamOpening,
  streamTurn,
  type ChatEvent,
} from "../api/chat";
import { burst } from "../effects/confetti";
import { getPersonas } from "../api/personas";
import { tolgee } from "../i18n";
import { stageFixture } from "../stage/fixture";
import { ChatPage } from "./ChatPage";

vi.mock("../api/chat", () => ({
  closeSession: vi.fn(),
  getActiveSession: vi.fn(),
  postSession: vi.fn(),
  setDisplayLocale: vi.fn(),
  streamContinue: vi.fn(),
  streamOpening: vi.fn(),
  streamTurn: vi.fn(),
}));
vi.mock("../api/personas", () => ({ getPersonas: vi.fn() }));
vi.mock("../effects/confetti", () => ({
  burst: vi.fn(),
  burstMs: vi.fn(() => 1200),
  reducedMotion: vi.fn(() => false),
}));

// The conversation contract, walked end to end: a scripted backend delivers its
// events one at a time, and after every single event the visible thread is
// snapshotted. The snapshots must obey what a student experiences:
//   - nothing ever vanishes or shuffles: every line stays, only grows (prefix rule);
//   - turns alternate: the tutor speaks, then the student, then the tutor;
//   - on a chosen answer the verdict (chip flash, confetti) lands before the
//     tutor's reply says a word, and the reply waits until the confetti has
//     played out, dots standing in for the tutor;
//   - a resumed thread replays one box at a time, each tutor box after its own
//     typing beat, a question landing together with its choices.
// A regression in the streaming handoff, the reveal pacing or the settled-message
// swap breaks the prefix rule instead of passing silently.

type Line = { role: "user" | "assistant"; text: string };
type Frame = { role: "user" | "assistant"; paragraphs: string[] }[];

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const SESSION = {
  id: 7,
  persona_id: "marvin",
  phase: "lesson",
  display_locale: "de",
  hint: { kind: "text" as const, choices: [], asks: false },
  messages: [],
  stage: stageFixture,
  budget: { state: "ok" as const },
};

const linesOf = (frame: Frame): Line[] =>
  frame.flatMap((message) =>
    message.paragraphs
      .filter((paragraph) => paragraph !== "")
      .map((paragraph) => ({ role: message.role, text: paragraph })),
  );

// A picked chip is the student's answer to its question: it reads as their line.
function snapshot(): Frame {
  return [...document.querySelectorAll(".chat-thread .message")].flatMap((block) => {
    const said = {
      role: block.classList.contains("message--user") ? ("user" as const) : ("assistant" as const),
      paragraphs: [...block.querySelectorAll(".ui-bubble")].map(
        (bubble) => bubble.childNodes[0]?.textContent ?? "",
      ),
    };
    const pick = block.querySelector('.message-choices .ui-chip[aria-pressed="true"]');
    return pick === null ? [said] : [said, { role: "user" as const, paragraphs: [pick.textContent ?? ""] }];
  });
}

// The paragraph text is the bubble's first child; a citations footer may follow
// as a sibling element and is not part of the line.

async function revealAll() {
  const scroller = document.querySelector(".chat-scroll");
  if (scroller !== null) await userEvent.click(scroller);
}

describe("the conversation walk", () => {
  let deliver: ((event: ChatEvent) => void) | null;
  let settle: () => void;

  function streamByEvent(): void {
    vi.mocked(streamTurn).mockImplementation(
      (_sessionId, _text, onEvent) =>
        new Promise<void>((resolve) => {
          deliver = onEvent;
          settle = resolve;
        }),
    );
  }

  async function play(events: ChatEvent[]): Promise<void> {
    for (const event of events) {
      await act(async () => {
        deliver?.(event);
      });
      await revealAll();
    }
    await act(async () => {
      settle();
    });
    await revealAll();
  }

  beforeEach(() => {
    deliver = null;
    vi.mocked(burst).mockClear();
    vi.mocked(getActiveSession).mockResolvedValue(null);
    vi.mocked(getPersonas).mockResolvedValue([
      {
        id: "marvin",
        name: { de: "Marvin", en: "Depressobot" },
        tagline: { de: "Gehirn von Planetariumsgröße.", en: "Brain the size of a planet." },
        images: { neutral: "/api/personas/marvin/images/neutral" },
      },
    ]);
    vi.mocked(postSession).mockResolvedValue(SESSION);
    vi.mocked(setDisplayLocale).mockResolvedValue(SESSION);
    streamByEvent();
  });

  it("walks opening, taught turn and graded answer with no line ever vanishing", async () => {
    const timeline: Frame[] = [];
    const take = () => timeline.push(snapshot());

    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );

    render(withProvider(<ChatPage />));
    await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));

    const opening = [
      { event: "token", text: "Willkommen" },
      { event: "token", text: " beim Kurs." },
      {
        event: "message",
        translating: false,
        text: "Willkommen beim Kurs.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      },
    ] as ChatEvent[];
    for (const event of opening) {
      await act(async () => {
        deliverOpening(event);
      });
      await revealAll();
      take();
    }
    await act(async () => {
      settleOpening();
    });
    await revealAll();
    take();

    // Turn 1: taught, ends on the case's choices.
    await userEvent.type(screen.getByRole("textbox"), "Weiter bitte");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    take();
    await play([
      { event: "ui", name: "stage", payload: stageFixture },
      { event: "token", text: "Fangen wir an: " },
      { event: "token", text: "Was darf du mit einem KI-System tun?" },
      {
        event: "input_hint",
        hint: {
          kind: "choices",
          asks: true,
          correct_key: "a",
          choices: [
            { key: "a", label: "Notizen zusammenfassen" },
            { key: "b", label: "Noten automatisch vergeben" },
          ],
        },
      },
      {
        event: "message",
        translating: false,
        text: "Fangen wir an: Was darf du mit einem KI-System tun?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          correct_key: "a",
          choices: [
            { key: "a", label: "Notizen zusammenfassen" },
            { key: "b", label: "Noten automatisch vergeben" },
          ],
        },
      },
    ]);
    take();

    // Turn 2: the student picks an answer; the verdict lands before the tutor speaks.
    await userEvent.click(await screen.findByRole("button", { name: /Notizen zusammenfassen/ }));
    take();
    // The pick is the answer on screen: no bubble repeats it, only the typed
    // "Weiter bitte" is a student bubble.
    expect(document.querySelectorAll(".chat-thread .message--user")).toHaveLength(1);
    // A practice hint names its answer: the picked chip flashes on the click
    // itself, a beat before any verdict event arrives.
    expect(document.querySelectorAll(".chip-flash--ok").length).toBeGreaterThanOrEqual(1);
    await play([
      { event: "ui", name: "answer_result", payload: { verdict: "correct", settled: true } },
      { event: "ui", name: "confetti", payload: {} },
      { event: "token", text: "Sauber. " },
      { event: "token", text: "Weiter zum nächsten Schritt." },
      {
        event: "message",
        translating: false,
        text: "Sauber. Weiter zum nächsten Schritt.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      },
    ]);
    take();

    // The answered grid holds the turn it belongs to, not the thread's end: it
    // sits inside the message that asked the question, ahead of the student's
    // own line, and stays put there as the reply lands.
    const threadList = document.querySelector(".chat-thread > div");
    const blocks = threadList ? [...threadList.children] : [];
    const gridHost = blocks.find((block) => block.querySelector(".message-choices"));
    expect(gridHost).toBeDefined();
    expect(blocks.at(-1)).not.toBe(gridHost);
    const gridIndex = blocks.indexOf(gridHost as Element);

    // The confetti holds the reply: while it plays, no new line lands and no
    // typing dots start. The celebration owns the moment; the dots come after it.
    const duringHold = linesOf(timeline[timeline.length - 1]);
    expect(duringHold.at(-1)?.role).toBe("user");
    expect(document.querySelector(".chat-wait-bubble")).toBeNull();

    // The verdict order, on screen: when the answer_result event had landed, the
    // chip flashed and the confetti flew, and the tutor had not yet said a word.
    const atVerdict = linesOf(timeline[timeline.length - 2]);
    expect(atVerdict[atVerdict.length - 1].role).toBe("user");
    const flashed = [...document.querySelectorAll(".chip-flash--ok")];
    expect(flashed.length).toBeGreaterThanOrEqual(1);
    await waitFor(() => expect(burst).toHaveBeenCalledWith(60), { timeout: 2000 });

    // The hold lifts and the reply arrives, paced as always.
    await waitFor(
      () => expect(screen.getByText(/Weiter zum nächsten Schritt/)).toBeInTheDocument(),
      { timeout: 9000 },
    );
    take();

    // The answered chips stay once their moment is over (D104): the flash has
    // played, the picked chip keeps its verdict steady, and the grid stays with
    // its question, exactly where the answer found it.
    await waitFor(
      () => expect(document.querySelector(".message-choices--settled")).not.toBeNull(),
      { timeout: 4000 },
    );
    expect(document.querySelectorAll(".chip-flash--ok")).toHaveLength(0);
    const picked = document.querySelector(".chip-verdict--ok");
    expect(picked).not.toBeNull();
    const settledBlocks = [...(threadList as HTMLElement).children];
    expect(settledBlocks[gridIndex]).toBe(gridHost);
    expect(gridHost?.contains(picked)).toBe(true);

    // The conversation contract across every snapshot taken.
    const lines = timeline.map(linesOf);
    for (let i = 1; i < lines.length; i++) {
      const before = lines[i - 1];
      const after = lines[i];
      expect(after.length).toBeGreaterThanOrEqual(before.length);
      for (let j = 0; j < before.length; j++) {
        expect(after[j].role).toBe(before[j].role);
        expect(after[j].text.startsWith(before[j].text)).toBe(true);
      }
    }
    // Turns alternate: the tutor opens, then user and tutor take turns.
    const final = lines[lines.length - 1];
    expect(final[0].role).toBe("assistant");
    for (let j = 1; j < final.length; j++) {
      expect(final[j].role).not.toBe(final[j - 1].role);
    }
    expect(final.at(-1)?.text).toContain("Weiter zum nächsten Schritt");
  }, 20000);

  it("walks a picked position into its typed why", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    render(withProvider(<ChatPage />));
    await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
    await act(async () => {
      deliverOpening({
        event: "message",
        translating: false,
        text: "Willkommen beim Kurs.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
      settleOpening();
    });
    await revealAll();
    await userEvent.type(screen.getByRole("textbox"), "Los geht es");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await play([
      {
        event: "message",
        translating: false,
        text: "Muss die Kennzeichnung dran?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          correct_key: "a",
          choices: [
            { key: "a", label: "Das Video muss als erzeugt gekennzeichnet sein." },
            { key: "b", label: "Eine Kennzeichnung braucht es nicht." },
          ],
        },
      },
    ] as ChatEvent[]);
    // The pick is green but the question stays open: the verdict is not settled.
    await userEvent.click(screen.getByRole("button", { name: /Das Video muss als erzeugt/ }));
    await play([
      { event: "ui", name: "answer_result", payload: { verdict: "correct", settled: false } },
      { event: "token", text: "Richtig, der Chef. Der Kollege bleibt aber dabei." },
      {
        event: "message",
        translating: false,
        text: "Richtig, sie muss dran. Das Marketing fragt aber noch. Wer schreibt sie dazu?",
        parts: [],
        hint: { kind: "text", choices: [], asks: true },
      },
    ] as ChatEvent[]);
    // After the pick the input is the composer again: the why is typed (D125).
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    const grid = document.querySelector(".message-choices");
    expect(grid).not.toBeNull();
    const picked = document.querySelector('.message-choices .ui-chip[aria-pressed="true"]');
    expect(picked).not.toBeNull();

    await userEvent.type(screen.getByRole("textbox"), "Die Verordnung ist nur die Untergrenze.");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await play([
      { event: "ui", name: "answer_result", payload: { verdict: "correct", settled: true } },
      { event: "ui", name: "confetti", payload: {} },
      { event: "token", text: "Genau. Weiter im Kapitel." },
      {
        event: "message",
        translating: false,
        text: "Genau. Weiter im Kapitel.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      },
    ] as ChatEvent[]);
    
  });

  it("keeps the whole thread when a turn fails, and the retry appends cleanly", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    render(withProvider(<ChatPage />));
    await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
    await act(async () => {
      deliverOpening({
        event: "message",
        translating: false,
        text: "Willkommen beim Kurs.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
      settleOpening();
    });
    await revealAll();

    await userEvent.type(screen.getByRole("textbox"), "Weiter");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await play([{ event: "token", text: "Halb eine" }]);
    await act(async () => {
      deliver?.({ event: "error", code: "network", message: "chat.error" });
    });
    await revealAll();
    // A half-streamed line goes with its failed turn; what is settled stays, and
    // the error says why nothing followed.
    expect(screen.getByText(/Etwas ist schiefgelaufen/)).toBeInTheDocument();
    expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
    expect(screen.getByText("Weiter")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeEnabled();

    await userEvent.type(screen.getByRole("textbox"), "Nochmal");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await play([
      { event: "token", text: "Und jetzt komplett." },
      {
        event: "message",
        translating: false,
        text: "Und jetzt komplett.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      },
    ]);

    const final = linesOf(snapshot());
    expect(final.map((line) => line.text)).toEqual([
      "Willkommen beim Kurs.",
      "Weiter",
      "Nochmal",
      "Und jetzt komplett.",
    ]);
  }, 20000);

  it("gives a continue turn its typing beat too, though the student sent no message", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    let deliverContinue!: (event: ChatEvent) => void;
    vi.mocked(streamContinue).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>(() => {
          deliverContinue = onEvent;
        }),
    );
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    try {
      render(withProvider(<ChatPage />));
      await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
      await act(async () => {
        deliverOpening({
          event: "message",
          translating: false,
          text: "Willkommen beim Kurs.",
          parts: [],
          hint: { kind: "confirm", choices: [], label: "Weiter", asks: false },
        });
        settleOpening();
      });
      await revealAll();

      // "Weiter" carries no student bubble, yet the tutor's next turn owes the
      // same beat: dots hold the floor, the text may not pop in.
      await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
      await act(async () => {
        deliverContinue({
          event: "message",
          translating: false,
          text: "Nächster Schritt.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });
      expect(screen.queryByText("Nächster Schritt.")).toBeNull();
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();
      await screen.findByText("Nächster Schritt.", {}, { timeout: 3000 });
    } finally {
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("keeps the in-progress indicator lit while the stream catches its breath", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    try {
      render(withProvider(<ChatPage />));
      await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
      await act(async () => {
        deliverOpening({
          event: "message",
          translating: false,
          text: "Willkommen beim Kurs.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
        settleOpening();
      });
      await revealAll();

      await userEvent.type(screen.getByRole("textbox"), "Weiter");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await act(async () => {
        deliver?.({ event: "token", text: "Erste Zeile." });
      });
      // The first paragraph is on screen and the stream has caught up: the
      // indicator may not go dark, because more of the turn may still come.
      await screen.findByText("Erste Zeile.");
      expect(document.querySelector(".chat-wait-bubble")).not.toBeNull();

      // The next chunk arrives: the indicator stays, the line count grows.
      await act(async () => {
        deliver?.({ event: "token", text: "\n\nZweite Zeile." });
      });
      await screen.findByText("Zweite Zeile.", {}, { timeout: 4000 });
      expect(document.querySelector(".chat-wait-bubble")).not.toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("never blanks a read line, not even when a turn fails", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      render(withProvider(<ChatPage />));
      await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
      await act(async () => {
        deliverOpening({
          event: "message",
          translating: false,
          text: "Willkommen beim Kurs.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
        settleOpening();
      });
      await revealAll();

      await userEvent.type(screen.getByRole("textbox"), "Weiter");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await act(async () => {
        deliver?.({ event: "token", text: "Halb eine" });
        deliver?.({ event: "error", code: "network", message: "chat.error" });
      });
      // The failed turn withdraws its own half line; the line the student had
      // already read stays exactly where it was, whole, with no re-typing.
      expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
      expect(screen.queryByText(/Halb/)).toBeNull();
    } finally {
      warn.mockRestore();
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("gives a whole-landing reply its typing beat, like any other", async () => {
    let settleOpening!: () => void;
    let deliverOpening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(
      (_sessionId, onEvent) =>
        new Promise<void>((resolve) => {
          deliverOpening = onEvent;
          settleOpening = resolve;
        }),
    );
    // jsdom ships no matchMedia, and without it every turn shows whole; the beat
    // under test needs the motion answer.
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    try {
      render(withProvider(<ChatPage />));
      await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
      await act(async () => {
        deliverOpening({
          event: "message",
          translating: false,
          text: "Willkommen beim Kurs.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
        settleOpening();
      });
      await revealAll();

      await userEvent.type(screen.getByRole("textbox"), "Weiter");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await act(async () => {
        deliver?.({
          event: "message",
          translating: false,
          text: "Erfolg.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });

      // The dots hold the floor first: a reply that lands whole may not pop in.
      expect(screen.queryByText("Erfolg.")).toBeNull();
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();
      await screen.findByText("Erfolg.", {}, { timeout: 3000 });
    } finally {
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("replays a resumed thread one box at a time, each tutor box after its typing beat", async () => {
    vi.mocked(getActiveSession).mockResolvedValue({
      ...SESSION,
      hint: {
        kind: "choices" as const,
        asks: true,
        choices: [{ key: "a", label: "Notizen zusammenfassen" }],
      },
      messages: [
        { role: "assistant" as const, text: "Willkommen beim Kurs.", parts: [], translating: false },
        { role: "user" as const, text: "Hallo Tutor", parts: [], translating: false },
        {
          role: "assistant" as const,
          text: "Guten Tag! Was beschäftigt dich?",
          parts: [],
          translating: false,
        },
      ],
    });
    vi.useFakeTimers();
    try {
      render(withProvider(<ChatPage />));
      for (let i = 0; i < 50 && document.querySelector(".chat-wait-bubble") === null; i++) {
        await act(async () => {});
      }

      // The dots come first; no box of the old thread has popped in.
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();
      expect(document.querySelector(".chat-thread .message")).toBeNull();

      // The first box waits the long first beat: the regular beat plus its half.
      await act(async () => {
        vi.advanceTimersByTime(900);
      });
      expect(screen.queryByText("Willkommen beim Kurs.")).not.toBeInTheDocument();
      await act(async () => {
        vi.advanceTimersByTime(1125);
      });
      expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
      await act(async () => {
        vi.advanceTimersByTime(1);
      });
      expect(screen.getByText("Hallo Tutor")).toBeInTheDocument();

      // The regular beat brings the question, and its choices land with it.
      await act(async () => {
        vi.advanceTimersByTime(1349);
      });
      expect(screen.queryByText("Guten Tag! Was beschäftigt dich?")).not.toBeInTheDocument();
      await act(async () => {
        vi.advanceTimersByTime(2);
      });
      expect(screen.getByText("Guten Tag! Was beschäftigt dich?")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Notizen zusammenfassen/ })).toBeInTheDocument();
      expect(document.querySelector(".chat-wait-bubble")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("skips the replay when the student clicks the thread", async () => {
    vi.mocked(getActiveSession).mockResolvedValue({
      ...SESSION,
      hint: {
        kind: "choices" as const,
        asks: true,
        choices: [{ key: "a", label: "Notizen zusammenfassen" }],
      },
      messages: [
        { role: "assistant" as const, text: "Willkommen beim Kurs.", parts: [], translating: false },
        {
          role: "assistant" as const,
          text: "Guten Tag! Was beschäftigt dich?",
          parts: [],
          translating: false,
        },
      ],
    });
    render(withProvider(<ChatPage />));
    await waitFor(() => expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument());

    await userEvent.click(document.querySelector(".chat-scroll")!);

    expect(await screen.findByRole("button", { name: /Notizen zusammenfassen/ })).toBeInTheDocument();
    expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
    expect(screen.getByText("Guten Tag! Was beschäftigt dich?")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector(".chat-wait-bubble")).toBeNull());
  }, 15000);
});
