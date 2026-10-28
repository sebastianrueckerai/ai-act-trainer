import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  closeSession,
  getActiveSession,
  postSession,
  setDisplayLocale,
  streamContinue,
  streamOpening,
  streamTurn,
  type ChatEvent,
} from "../api/chat";
import { getPersonas } from "../api/personas";
import { tolgee } from "../i18n";
import { stageFixture } from "../stage/fixture";
import { ChatPage } from "./ChatPage";
import { onUi } from "./uiBus";
import { burst } from "../effects/confetti";

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
// The hold waits for the burst; a mocked burst is worth nothing and waits no time.
vi.mock("../effects/confetti", () => ({
  burst: vi.fn(),
  burstMs: vi.fn(() => 20),
  reducedMotion: vi.fn(() => false),
}));

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

async function pickMarvin() {
  const toolsSlot = document.body.appendChild(document.createElement("div"));
  render(withProvider(<ChatPage toolsSlot={toolsSlot} />));
  await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));
}

describe("ChatPage", () => {
  beforeEach(() => {
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
    vi.mocked(closeSession).mockResolvedValue(undefined);
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        id: "m-open",
        text: "Willkommen beim Kurs.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "ui",
        name: "stage",
        payload: {
          ...stageFixture,
          persona: { id: "marvin", name: "Marvin", image_url: null },
        },
      });
      onEvent({ event: "token", text: "Gu" });
      onEvent({ event: "token", text: "ten Tag" });
      onEvent({ event: "input_hint", hint: { kind: "yes_no", choices: [], asks: false } });
      onEvent({
        event: "message",
        translating: false,
        id: "m-turn",
        text: "Guten Tag! Was beschäftigt dich?",
        parts: [],
        hint: { kind: "yes_no", choices: [], asks: false },
      });
    });
  });

  it("shows the persona's English name and tagline when the UI is English", async () => {
    await tolgee.changeLanguage("en");
    try {
      render(withProvider(<ChatPage />));
      expect(await screen.findByText("Depressobot")).toBeInTheDocument();
      expect(screen.getByText("Brain the size of a planet.")).toBeInTheDocument();
      expect(screen.queryByText("Marvin")).not.toBeInTheDocument();
    } finally {
      await tolgee.changeLanguage("de");
    }
  });

  it("opens on the persona choice and starts the course on a click", async () => {
    render(withProvider(<ChatPage />));

    expect(await screen.findByText("Wer soll dich durch den Kurs bringen?")).toBeInTheDocument();
    const card = await screen.findByRole("button", { name: /Marvin/ });
    expect(screen.getByText("Gehirn von Planetariumsgröße.")).toBeInTheDocument();

    await userEvent.click(card);

    expect(postSession).toHaveBeenCalledWith("marvin", "de");
    expect(streamOpening).toHaveBeenCalledWith(7, expect.any(Function));
    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();
  });

  it("paces a fast-streamed opening one bubble at a time, each prefaced by the wait indicator", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    const paragraphs = ["Willkommen beim Kurs.", "Ich bin dein Tutor.", "Wir fangen gleich an."];
    const text = paragraphs.join("\n\n");
    let opening!: (event: ChatEvent) => void;
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      opening = onEvent;
    });
    const bubbles = () => [...document.querySelectorAll(".ui-bubble--assistant")];
    try {
      await pickMarvin();
      await waitFor(() => expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument());

      // The model emits the whole opening in one fast burst.
      await act(async () => {
        opening({ event: "token", text });
      });
      // The first bubble owes its own typing beat: dots hold the floor first.
      expect(bubbles().map((bubble) => bubble.textContent)).toEqual([]);
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();
      await waitFor(() => expect(bubbles().map((bubble) => bubble.textContent)).toEqual([paragraphs[0]]), {
        timeout: 4000,
      });
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();

      // The settled message lands: nothing shown disappears, nothing new flashes.
      await act(async () => {
        opening({
          event: "message",
          translating: false,
          text,
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });
      expect(bubbles().map((bubble) => bubble.textContent)).toEqual([paragraphs[0]]);
      expect(document.querySelector(".chat-wait-bubble")).toBeInTheDocument();

      // The rest arrives at reading pace.
      await waitFor(() => expect(bubbles().map((bubble) => bubble.textContent)).toEqual(paragraphs), {
        timeout: 4000,
      });
    } finally {
      vi.unstubAllGlobals();
    }
  }, 10000);

  it("keeps the tutor's last turn on screen while the model thinks", async () => {
    let answer!: () => void;
    const thinking = new Promise<void>((resolve) => {
      answer = resolve;
    });
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      await thinking;
      onEvent({ event: "token", text: "Antwort." });
      onEvent({
        event: "message",
        translating: false,
        text: "Antwort.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    await pickMarvin();
    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox"), "Frage");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await act(async () => {});

    // The model has not said a word yet; what it said before is still there.
    expect(screen.getByText("Frage")).toBeInTheDocument();
    expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();

    await act(async () => {
      answer();
    });
    expect(await screen.findByText("Antwort.")).toBeInTheDocument();
  });

  it("answers a refused turn with the notice above a disabled composer, not a red line", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const resetsAt = new Date(Date.now() + 2 * 3_600_000).toISOString();
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "error",
        code: "limit",
        message: "chat.limit",
        budget: { state: "exhausted", scope: "pool_day", resets_at: resetsAt },
      });
    });
    await pickMarvin();
    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox"), "Frage");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    const notice = await screen.findByRole("status");
    expect(screen.getByRole("heading", { name: "Großer Andrang" })).toBeInTheDocument();
    expect(notice).toHaveTextContent(/Das Demo-Guthaben für heute ist aufgebraucht\. Um .+ geht es weiter\./);
    expect(notice).toHaveTextContent(/Weiter in \d+ Std\. \d+ Min\. \d+ Sek\./);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Senden" })).toBeDisabled();
    expect(screen.queryByText(/Etwas ist schiefgelaufen/)).not.toBeInTheDocument();
    // the notice stands in the foot, directly above the composer
    expect(notice.nextElementSibling).toHaveClass("composer");
    warn.mockRestore();
  });

  it("keeps the thread's end in view when the notice takes room from the pane", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    let refuse: (() => void) | undefined;
    vi.mocked(streamTurn).mockImplementation(
      (_sessionId, _text, onEvent) =>
        new Promise<void>((resolve) => {
          refuse = () => {
            onEvent({
              event: "error",
              code: "limit",
              message: "chat.limit",
              budget: { state: "exhausted", scope: "seats", resets_at: null },
            });
            resolve();
          };
        }),
    );
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");
    await userEvent.type(screen.getByRole("textbox"), "Frage");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    scrollIntoView.mockClear();

    await act(async () => refuse?.());
    await screen.findByRole("status");
    const last = scrollIntoView.mock.contexts.at(-1) as Element | undefined;
    expect(last?.classList.contains("chat-thread-end")).toBe(true);
    warn.mockRestore();
  });

  it("opens an exhausted session on the notice and holds the opening back", async () => {
    vi.mocked(streamOpening).mockClear();
    vi.mocked(postSession).mockResolvedValue({
      ...SESSION,
      budget: {
        state: "exhausted",
        scope: "day",
        resets_at: new Date(Date.now() + 3_600_000).toISOString(),
      },
    });
    await pickMarvin();

    expect(await screen.findByRole("heading", { name: "Viel geschafft" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/Dein Guthaben für heute ist aufgebraucht\./);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(streamOpening).not.toHaveBeenCalled();
  });

  it("lifts the notice when the session's budget is back, and the course opens", async () => {
    vi.mocked(streamOpening).mockClear();
    vi.mocked(postSession).mockResolvedValue({
      ...SESSION,
      budget: {
        state: "exhausted",
        scope: "pool_day",
        resets_at: new Date(Date.now() - 1_000).toISOString(),
      },
    });
    // the first ask finds no session and opens the picker; the clock already stands at
    // zero, so the page asks again at once and finds the budget back
    vi.mocked(getActiveSession).mockResolvedValueOnce(null).mockResolvedValue(SESSION);
    await pickMarvin();

    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
    expect(streamOpening).toHaveBeenCalledTimes(1);
  });

  it("goes back to the persona choice when the session was cleaned while waiting", async () => {
    vi.mocked(postSession).mockResolvedValue({
      ...SESSION,
      budget: {
        state: "exhausted",
        scope: "pool_day",
        resets_at: new Date(Date.now() - 1_000).toISOString(),
      },
    });
    await pickMarvin();

    expect(await screen.findByText("Wer soll dich durch den Kurs bringen?")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("translates the error line at render, so the flag flips it too (D94)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({ event: "error", code: "turn_failed", message: "boom" });
    });
    try {
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      await userEvent.type(screen.getByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      expect(
        await screen.findByText("Etwas ist schiefgelaufen. Bitte versuche es erneut."),
      ).toBeInTheDocument();

      await act(async () => {
        await tolgee.changeLanguage("en");
      });
      expect(await screen.findByText("Something went wrong. Please try again.")).toBeInTheDocument();
    } finally {
      await tolgee.changeLanguage("de");
      warn.mockRestore();
    }
  });

  it("warms every emotion image of the picked persona, so a mood swap never waits", async () => {
    vi.mocked(getPersonas).mockResolvedValue([
      {
        id: "marvin",
        name: { de: "Marvin", en: "Depressobot" },
        tagline: { de: "Gehirn von Planetariumsgröße.", en: "Brain the size of a planet." },
        images: {
          neutral: "/api/personas/marvin/images/neutral",
          happy: "/api/personas/marvin/images/happy",
          disappointed: "/api/personas/marvin/images/disappointed",
        },
      },
    ]);
    const warmed: string[] = [];
    vi.stubGlobal(
      "Image",
      class {
        set src(url: string) {
          warmed.push(url);
        }
      },
    );

    try {
      await pickMarvin();
      expect(warmed).toEqual([
        "/api/personas/marvin/images/neutral",
        "/api/personas/marvin/images/happy",
        "/api/personas/marvin/images/disappointed",
      ]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows the disclaimer on the picker, not once the chat is open", async () => {
    render(withProvider(<ChatPage />));
    expect(
      await screen.findByText(/Ich bin ein Trainingsprogramm und kein Rechtsberater/),
    ).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: /Marvin/ }));

    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();
    expect(
      screen.queryByText(/Ich bin ein Trainingsprogramm und kein Rechtsberater/),
    ).not.toBeInTheDocument();
  });

  it("streams a turn and swaps the input hint", async () => {
    await pickMarvin();
    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox"), "Was gilt für KI-Systeme?");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    expect(streamTurn).toHaveBeenCalledWith(
      7,
      "Was gilt für KI-Systeme?",
      expect.any(Function),
      undefined,
      undefined,
    );

    expect(await screen.findByText("Guten Tag! Was beschäftigt dich?")).toBeInTheDocument();
    expect(screen.getByText("Was gilt für KI-Systeme?")).toBeInTheDocument();
    expect(screen.queryByText("Guten Tag")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Ja" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nein" })).toBeInTheDocument();
  });

  it("marks a picked chip as the answer, sends its key and draws no bubble of its own", async () => {
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: { kind: "choices", choices: [{ key: "B", label: "Eine Notiz zusammenfassen" }], asks: false },
      });
    });
    await pickMarvin();

    await userEvent.click(await screen.findByRole("button", { name: "B. Eine Notiz zusammenfassen" }));

    // The key drives the graph, the label is what the thread replays (D91).
    expect(streamTurn).toHaveBeenCalledWith(
      7,
      "B",
      expect.any(Function),
      undefined,
      "B. Eine Notiz zusammenfassen",
    );
    // No verdict yet: the picked chip is pressed, and the chip is the answer on screen.
    // It keeps the plain chip look; only the verdict rings its frame (D104).
    const pickedChip = screen.getByRole("button", { name: "B. Eine Notiz zusammenfassen" });
    expect(pickedChip).toHaveAttribute("aria-pressed", "true");
    expect(pickedChip).toHaveAttribute("data-selected", "false");
    expect(document.querySelectorAll(".message--user")).toHaveLength(0);
  });

  it("advances on confirm without a message of its own", async () => {
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Reicht das?",
        parts: [],
        hint: { kind: "confirm", choices: [], label: "Weiter", asks: false },
      });
    });
    vi.mocked(streamContinue).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Nächster Schritt.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    await userEvent.click(await screen.findByRole("button", { name: "Weiter" }));

    expect(streamContinue).toHaveBeenCalledWith(7, expect.any(Function));
    expect(await screen.findByText("Nächster Schritt.")).toBeInTheDocument();
    const userBubbles = document.querySelectorAll(".message--user");
    expect(userBubbles).toHaveLength(1);
    expect(userBubbles[0].textContent).toBe("Hallo");
  });

  it("resumes an existing session and never shows the picker", async () => {
    vi.mocked(getActiveSession).mockResolvedValue({
      ...SESSION,
      messages: [{ role: "assistant", text: "Weiter geht es.", parts: [], translating: false }],
    });
    render(withProvider(<ChatPage />));

    // The resumed thread replays, so the box waits out its typing beat first.
    expect(await screen.findByText("Weiter geht es.", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("Wer soll dich durch den Kurs bringen?")).not.toBeInTheDocument();
    expect(streamOpening).not.toHaveBeenCalled();
  });

  it("restores the typed why's composer on a mid-chained reload", async () => {
    vi.mocked(getActiveSession).mockResolvedValue({
      ...SESSION,
      messages: [
        {
          role: "assistant",
          text: "Muss die Kennzeichnung dran?",
          parts: [],
          translating: false,
          hint: {
            kind: "choices",
            asks: true,
            choices: [
              { key: "a", label: "Das Video muss als erzeugt gekennzeichnet sein." },
              { key: "b", label: "Eine Kennzeichnung braucht es nicht." },
            ],
          },
        },
        { role: "user", text: "Das Video muss als erzeugt gekennzeichnet sein.", parts: [], translating: false },
        {
          role: "assistant",
          text: "Richtig, sie muss dran. Das Marketing fragt aber noch. Wer schreibt sie dazu?",
          parts: [],
          translating: false,
          hint: { kind: "text", asks: true },
        },
      ],
      hint: { kind: "text" as const, choices: [], asks: true },
    });
    render(withProvider(<ChatPage />));

    expect(
      await screen.findByText(/Wer schreibt sie dazu?/, {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    // The reload replays the thread without the grid's live state (D104): no chips
    // come back, and the last message's text hint restores the composer (D127).
    expect(screen.queryByRole("button", { name: /Der Chef hat recht/ })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("runs the opening when a seeded session has no messages yet", async () => {
    vi.mocked(getActiveSession).mockResolvedValue(SESSION);
    render(withProvider(<ChatPage />));

    expect(await screen.findByText("Willkommen beim Kurs.")).toBeInTheDocument();
    expect(streamOpening).toHaveBeenCalledWith(7, expect.any(Function));
    expect(postSession).not.toHaveBeenCalled();
  });

  it("echoes every ui event onto the bus", async () => {
    const seen: string[] = [];
    const off = onUi((detail) => seen.push(detail.name));
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    expect(await screen.findByText("Guten Tag! Was beschäftigt dich?")).toBeInTheDocument();
    off();
    expect(seen).toEqual(["stage"]);
  });

  it("shows the error line when the course fails to start", async () => {
    vi.mocked(postSession).mockRejectedValue(new Error("backend down"));
    await pickMarvin();
    expect(
      await screen.findByText("Etwas ist schiefgelaufen. Bitte versuche es erneut."),
    ).toBeInTheDocument();
  });

  it("restarts: closes the session and returns to the persona picker", async () => {
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");

    await userEvent.click(await screen.findByRole("button", { name: "Neu starten" }));
    await userEvent.click(await screen.findByRole("button", { name: "Ja, von vorn" }));

    expect(closeSession).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Wer soll dich durch den Kurs bringen?")).toBeInTheDocument();
    expect(screen.queryByText("Willkommen beim Kurs.")).not.toBeInTheDocument();
  });

  it("hides the choices and disables the composer while restart is being confirmed", async () => {
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");
    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await screen.findByRole("button", { name: "Ja" });

    await userEvent.click(screen.getByRole("button", { name: "Neu starten" }));

    expect(screen.queryByRole("button", { name: "Ja" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nein" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ja, von vorn" })).toBeInTheDocument();
  });

  it("stays on the course when the restart confirmation is cancelled", async () => {
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");

    await userEvent.click(await screen.findByRole("button", { name: "Neu starten" }));
    await userEvent.click(await screen.findByRole("button", { name: "Abbrechen" }));

    expect(closeSession).not.toHaveBeenCalled();
    expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
  });

  it("scrolls the thread to the bottom when the student sends a message", async () => {
    // Held open so the reply never lands in the same batch as the student's own
    // message: that isolates the "user just sent" scroll from the "reply arrived" one.
    vi.mocked(streamTurn).mockImplementation(() => new Promise(() => {}));
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");
    scrollIntoView.mockClear();

    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" });
  });

  it("scrolls a reply taller than the scroll box to its own top", async () => {
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    await pickMarvin();
    scrollIntoView.mockClear();

    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    await screen.findByText("Guten Tag! Was beschäftigt dich?");

    // jsdom lays nothing out: the reply measures 0 against a scroll box of 0,
    // which is the "taller than the box" branch (0 > -24)
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start" });
  });

  it("brings a tall reply's own choices into view too, once its top is aligned", async () => {
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: { kind: "choices", choices: [{ key: "A", label: "Text zusammenfassen" }], asks: false },
      });
    });
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({ height: 520, bottom: 520, top: 0 } as DOMRect);
    const clientHeight = vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(500);
    try {
      await pickMarvin();
      scrollIntoView.mockClear();

      await userEvent.type(await screen.findByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await screen.findByText("Welche Nutzung ist erlaubt?");

      expect(scrollIntoView).toHaveBeenCalledWith({ block: "start" });
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" });
    } finally {
      rect.mockRestore();
      clientHeight.mockRestore();
    }
  });

  it("scrolls a reply shorter than the scroll box to the newest line", async () => {
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({ height: 120, bottom: 120, top: 0 } as DOMRect);
    const clientHeight = vi
      .spyOn(Element.prototype, "clientHeight", "get")
      .mockReturnValue(600);
    try {
      await pickMarvin();
      scrollIntoView.mockClear();

      await userEvent.type(await screen.findByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await screen.findByText("Guten Tag! Was beschäftigt dich?");

      expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "end" });
    } finally {
      rect.mockRestore();
      clientHeight.mockRestore();
    }
  });

  it("returns the reaction portrait to the neutral face after six seconds", async () => {
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    vi.useFakeTimers();
    try {
      await act(async () => {
        deliver?.({
          event: "ui",
          name: "stage",
          payload: {
            ...stageFixture,
            mood: "happy",
            persona: {
              id: "marvin",
              name: "Marvin",
              image_url: "/api/personas/marvin/images/happy",
              neutral_image_url: "/api/personas/marvin/images/neutral",
            },
          },
        });
      });
      const portrait = () => screen.getByRole("img", { name: "Marvin" });
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/happy");

      await act(async () => {
        vi.advanceTimersByTime(5_999);
      });
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/happy");
      await act(async () => {
        vi.advanceTimersByTime(1);
      });
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/neutral");
    } finally {
      vi.useRealTimers();
    }
  });

  it("returns the reaction portrait to the neutral face once the next question is on screen", async () => {
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    const portrait = () => screen.getByRole("img", { name: "Marvin" });

    await act(async () =>
      deliver?.({
        event: "ui",
        name: "stage",
        payload: {
          ...stageFixture,
          mood: "happy",
          persona: {
            id: "marvin",
            name: "Marvin",
            image_url: "/api/personas/marvin/images/happy",
            neutral_image_url: "/api/personas/marvin/images/neutral",
          },
        },
      }),
    );
    expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/happy");

    await act(async () =>
      deliver?.({
        event: "message",
        id: "m-next",
        text: "Richtig.\n\nWer ist Betreiber?",
        parts: [],
        hint: { kind: "text", choices: [], asks: true },
        translating: false,
      }),
    );
    expect(screen.getByText("Wer ist Betreiber?").closest(".ui-bubble")).toHaveClass("ui-bubble--question");
    expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/neutral");
    expect(portrait().parentElement).toHaveAttribute("data-mood", "neutral");
  });

  it("keeps the reaction portrait over a turn that asks nothing", async () => {
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    await act(async () =>
      deliver?.({
        event: "ui",
        name: "stage",
        payload: {
          ...stageFixture,
          mood: "happy",
          persona: {
            id: "marvin",
            name: "Marvin",
            image_url: "/api/personas/marvin/images/happy",
            neutral_image_url: "/api/personas/marvin/images/neutral",
          },
        },
      }),
    );
    await act(async () =>
      deliver?.({
        event: "message",
        id: "m-next",
        text: "Richtig. Klar soweit?",
        parts: [],
        hint: { kind: "confirm", choices: [], label: "Ja, weiter", asks: false },
        translating: false,
      }),
    );
    expect(screen.getByRole("img", { name: "Marvin" })).toHaveAttribute(
      "src",
      "/api/personas/marvin/images/happy",
    );
  });

  it("shows the reaction again when the next verdict brings the same mood", async () => {
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    const disappointed = () => ({
      event: "ui" as const,
      name: "stage",
      payload: {
        ...stageFixture,
        mood: "disappointed",
        persona: {
          id: "marvin",
          name: "Marvin",
          image_url: "/api/personas/marvin/images/disappointed",
          neutral_image_url: "/api/personas/marvin/images/neutral",
        },
      },
    });

    vi.useFakeTimers();
    try {
      await act(async () => deliver?.(disappointed()));
      await act(async () => {
        vi.advanceTimersByTime(6_000);
      });
      const portrait = () => screen.getByRole("img", { name: "Marvin" });
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/neutral");

      await act(async () => deliver?.(disappointed()));
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/disappointed");
      expect(portrait().parentElement).toHaveAttribute("data-mood", "disappointed");

      await act(async () => {
        vi.advanceTimersByTime(6_000);
      });
      expect(portrait()).toHaveAttribute("src", "/api/personas/marvin/images/neutral");
      expect(portrait().parentElement).toHaveAttribute("data-mood", "neutral");
    } finally {
      vi.useRealTimers();
    }
  });

  it("holds the choices until the question has arrived", async () => {
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "weiter");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    // The hint with the choices lands while the question turn is still generating:
    // no option may show yet.
    await act(async () => {
      deliver?.({
        event: "input_hint",
        hint: {
          kind: "choices",
          asks: true,
          choices: [{ key: "a", label: "Text zusammenfassen" }],
        },
      });
    });
    expect(screen.queryByRole("button", { name: /Text zusammenfassen/ })).toBeNull();

    // The question message lands and reveals; then the options stand under it.
    await act(async () => {
      deliver?.({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          choices: [{ key: "a", label: "Text zusammenfassen" }],
        },
      });
    });
    expect(await screen.findByRole("button", { name: /Text zusammenfassen/ })).toBeVisible();
  });

  it("flashes the clicked choice and throws confetti on a correct answer", async () => {
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          choices: [{ key: "a", label: "Text zusammenfassen" }, { key: "b", label: "Noten hochladen" }],
        },
      });
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    // The choice's own turn comes back with the verdict event.
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({ event: "ui", name: "answer_result", payload: { verdict: "correct", settled: true } });
      onEvent({
        event: "message",
        translating: false,
        text: "Sauber.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    const chip = await screen.findByRole("button", { name: /Text zusammenfassen/ });
    await userEvent.click(chip);
    await screen.findByText("Sauber.");

    // The answered grid stays inside the turn that asked; the flashed chip is its chip.
    const flashed = screen.getAllByRole("button", { name: /Text zusammenfassen/ })[0];
    expect(flashed).toHaveClass("chip-flash--ok");
    await waitFor(() => expect(burst).toHaveBeenCalledWith(60), { timeout: 2000 });
  });

  it.each([
    { verdict: "correct", tone: "ok" },
    { verdict: "partial", tone: "partial" },
    { verdict: "wrong", tone: "miss" },
  ])("flashes a picked chip by verdict ($verdict), then keeps the tint", async ({ verdict, tone }) => {
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          choices: [{ key: "a", label: "Text zusammenfassen" }, { key: "b", label: "Noten hochladen" }],
        },
      });
    });
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({ event: "ui", name: "answer_result", payload: { verdict, settled: true } });
      onEvent({
        event: "message",
        translating: false,
        text: "Weiter so.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    await pickMarvin();
    await userEvent.click(await screen.findByRole("button", { name: /Text zusammenfassen/ }));
    await screen.findByText("Weiter so.");

    const picked = screen.getByRole("button", { name: /Text zusammenfassen/ });
    expect(picked).toHaveClass(`chip-flash--${tone}`);
    await waitFor(() => expect(picked).toHaveClass(`chip-verdict--${tone}`), { timeout: 4000 });
  });

  it.each([
    { verdict: "correct", settled: true, flash: "own-flash--ok", bursts: true },
    { verdict: "correct", settled: false, flash: "own-flash--ok", bursts: false },
    { verdict: "partial", settled: false, flash: "own-flash--partial", bursts: false },
    { verdict: "wrong", settled: false, flash: "own-flash--miss", bursts: false },
  ])(
    "flashes a typed answer's own bubble by verdict ($verdict, settled $settled) and keeps the tint, celebrating only a settled correct one",
    async ({ verdict, settled, flash, bursts }) => {
      vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
        onEvent({
          event: "message",
          translating: false,
          text: "Welche Nutzung ist erlaubt?",
          parts: [],
          hint: { kind: "text", choices: [], asks: true },
        });
      });
      vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
        onEvent({ event: "ui", name: "answer_result", payload: { verdict, settled } });
        onEvent({
          event: "message",
          translating: false,
          text: "Schön erklärt.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });
      await pickMarvin();
      await userEvent.type(await screen.findByRole("textbox"), "Wir dürfen das");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await screen.findByText("Schön erklärt.");

      const ownBubble = [...document.querySelectorAll(".message--user .ui-bubble")].at(-1);
      expect(ownBubble).toHaveClass(flash);
      // After the pulse the bubble keeps its tint, as a picked chip does (D104).
      await waitFor(() => expect(ownBubble).toHaveClass(flash.replace("flash", "verdict")), {
        timeout: 4000,
      });
      if (bursts) {
        await waitFor(() => expect(burst).toHaveBeenCalledWith(60), { timeout: 2000 });
      } else {
        expect(burst).not.toHaveBeenCalled();
      }
    },
  );

  it("hops the portrait on a chapter end and drops the answer's confetti", async () => {
    vi.mocked(burst).mockClear();
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Weil wir es prüfen");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    vi.useFakeTimers();
    try {
      await act(async () => {
        deliver?.({
          event: "ui",
          name: "stage",
          payload: { ...stageFixture, mood: "happy", persona: { id: "marvin", name: "Marvin", image_url: null } },
        });
        deliver?.({ event: "ui", name: "answer_result", payload: { verdict: "correct", settled: true } });
        deliver?.({ event: "ui", name: "chapter_complete", payload: { chapter: "02-b" } });
        deliver?.({ event: "ui", name: "badge", payload: {} });
      });
      const portrait = () => document.querySelector(".chat-portrait");
      expect(portrait()).toHaveAttribute("data-hop");
      await act(async () => {
        vi.advanceTimersByTime(1199);
      });
      expect(portrait()).toHaveAttribute("data-hop");
      await act(async () => {
        vi.advanceTimersByTime(1);
      });
      expect(portrait()).not.toHaveAttribute("data-hop");
      await act(async () => {
        vi.advanceTimersByTime(5_000);
      });
      expect(burst).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("puts the chapter end's divider in the thread and its label on the button", async () => {
    const hint = { kind: "confirm" as const, choices: [], label: "Weiter zu Kapitel 3", asks: false };
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({ event: "ui", name: "chapter_complete", payload: { chapter: "02-b" } });
      onEvent({ event: "input_hint", hint });
      onEvent({
        event: "message",
        translating: false,
        id: "m-end",
        text: "Richtig.\n\nKapitel 2 geschafft. Ich empfinde etwas.\n\nDas darfst du: üben (Art. 4 Abs. 1).",
        parts: [{ kind: "chapter_done", chapter_id: "02-b", index: 2, total: 3, title: "Zweites" }],
        hint,
      });
    });
    await pickMarvin();
    await userEvent.type(await screen.findByRole("textbox"), "Weil wir es prüfen");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    expect(await screen.findByText("Kapitel 2 geschafft", { selector: ".chapter-divider-what" })).toBeInTheDocument();
    const lit = document.querySelectorAll(".chapter-route i[data-lit]");
    expect(lit).toHaveLength(2);
    expect(await screen.findByRole("button", { name: "Weiter zu Kapitel 3" })).toBeEnabled();
  });

  it("does not promise the tutor while the grade is pending", async () => {
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
      await runDoesNotPromise();
    } finally {
      vi.unstubAllGlobals();
    }

    async function runDoesNotPromise() {
      vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Welche Nutzung ist erlaubt?",
        parts: [],
        hint: {
          kind: "choices",
          asks: true,
          choices: [{ key: "a", label: "Text zusammenfassen" }],
        },
      });
    });
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    await pickMarvin();
    const chip = await screen.findByRole(
      "button",
      { name: /Text zusammenfassen/ },
      { timeout: 4000 },
    );
    await userEvent.click(chip);
    await act(async () => {});

    // The grade is pending: no indicator may promise the tutor, only to be
    // revoked by the verdict's celebration a moment later.
    expect(document.querySelector(".chat-wait-bubble")).toBeNull();

    // The verdict lands and the celebration holds: still no indicator.
    await act(async () => {
      deliver?.({
        event: "ui",
        name: "answer_result",
        payload: { verdict: "correct", settled: true },
      });
    });
    expect(document.querySelector(".chat-wait-bubble")).toBeNull();

    // The hold lifts and the reply paces in behind the dots, as always.
    await act(async () => {
      deliver?.({
        event: "message",
        translating: false,
        text: "Sauber.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    await new Promise((resolve) => setTimeout(resolve, 600));
    await waitFor(() => expect(document.querySelector(".chat-wait-bubble")).not.toBeNull());
    await screen.findByText("Sauber.", {}, { timeout: 4000 });
    }
  }, 15000);

  it("parks the view where the student scrolled it and follows again at the end", async () => {
    let deliver: ((event: Parameters<NonNullable<Parameters<typeof streamTurn>[2]>>[0]) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    await pickMarvin();
    await screen.findByRole("textbox");

    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" });

    // The send's own scroll is programmatic; its settle window must pass before a
    // hand-driven scroll counts as the student's.
    await new Promise((resolve) => setTimeout(resolve, 170));
    const scroller = document.querySelector(".chat-scroll") as HTMLDivElement;
    const setMetrics = (scrollTop: number) => {
      for (const [key, value] of [["scrollHeight", 2000], ["clientHeight", 500], ["scrollTop", scrollTop]]) {
        Object.defineProperty(scroller, key, { value, configurable: true });
      }
      scroller.dispatchEvent(new Event("scroll"));
    };

    // Scrolled up, far from the end: a landing reply must not move the view.
    setMetrics(100);
    scrollIntoView.mockClear();
    await act(async () => {
      deliver?.({ event: "message", translating: false, text: "Erste Antwort.", parts: [], hint: { kind: "text", asks: false } });
    });
    expect(scrollIntoView).not.toHaveBeenCalled();

    // Back at the end: the next text follows again.
    setMetrics(1450);
    scrollIntoView.mockClear();
    await act(async () => {
      deliver?.({ event: "message", translating: false, text: "Zweite Antwort.", parts: [], hint: { kind: "text", asks: false } });
    });
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("scrolls a tall card-and-bubble reply to its own top, card included", async () => {
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Richtig.",
        parts: [
          {
            kind: "card",
            question: "Wann greift Art. 5?",
            model_answer: "Bei verbotenen Praktiken.",
            explanation: "Art. 5 zählt sie abschließend auf.",
            citations: [],
            correct: true,
            tries: 1,
          },
        ],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    // The whole reply (card then bubble) spans 40 to 560, 520 px tall against a
    // scroll box with room for 476 (500 - 24): too tall to fit, so it aligns its
    // own top, the card included, rather than landing on the bubble's last line
    // with the card scrolled past.
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({ top: 40, bottom: 560, height: 520 } as DOMRect);
    const clientHeight = vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(500);
    try {
      await pickMarvin();
      scrollIntoView.mockClear();

      await userEvent.type(await screen.findByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await screen.findByText("Richtig.");

      expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "start" });
    } finally {
      rect.mockRestore();
      clientHeight.mockRestore();
    }
  });

  it("scrolls a card-only reply (no bubble) to its own top when it doesn't fit", async () => {
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "",
        parts: [
          {
            kind: "card",
            question: "Wann greift Art. 5?",
            model_answer: "Bei verbotenen Praktiken.",
            explanation: "Art. 5 zählt sie abschließend auf.",
            citations: [],
            correct: true,
            tries: 1,
          },
        ],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({ top: 40, bottom: 560, height: 520 } as DOMRect);
    const clientHeight = vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(500);
    try {
      await pickMarvin();
      scrollIntoView.mockClear();

      await userEvent.type(await screen.findByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await screen.findByText("Wann greift Art. 5?");

      expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "start" });
    } finally {
      rect.mockRestore();
      clientHeight.mockRestore();
    }
  });

  it("paints the persona's own scene and drops it again on restart", async () => {
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "ui",
        name: "stage",
        payload: {
          ...stageFixture,
          persona: {
            id: "marvin",
            name: "Marvin",
            image_url: null,
            scene_url: "/api/personas/marvin/images/scene",
          },
        },
      });
      onEvent({
        event: "message",
        translating: false,
        id: "m-open",
        text: "Willkommen beim Kurs.",
        parts: [],
        hint: { kind: "text", choices: [], asks: false },
      });
    });
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");

    expect(document.documentElement.style.getPropertyValue("--scene-image")).toBe(
      'url("/api/personas/marvin/images/scene")',
    );

    await userEvent.click(await screen.findByRole("button", { name: "Neu starten" }));
    await userEvent.click(await screen.findByRole("button", { name: "Ja, von vorn" }));
    await screen.findByText("Wer soll dich durch den Kurs bringen?");

    expect(document.documentElement.style.getPropertyValue("--scene-image")).toBe("");
  });

  it("shows the locale's error line, never the provider's own text", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.mocked(streamTurn).mockImplementation(async (_sessionId, _text, onEvent) => {
      onEvent({ event: "error", code: "upstream", message: "KeyError: 'id'" });
    });
    await pickMarvin();
    await screen.findByText("Willkommen beim Kurs.");

    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));

    expect(
      await screen.findByText("Etwas ist schiefgelaufen. Bitte versuche es erneut."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/KeyError/)).not.toBeInTheDocument();
    expect(warn).toHaveBeenCalledWith("chat error", "upstream", "KeyError: 'id'");
    warn.mockRestore();
  });

  it("follows the waiting dots when a continue turn takes over", async () => {
    vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
      onEvent({
        event: "message",
        translating: false,
        text: "Reicht das?",
        parts: [],
        hint: { kind: "confirm", choices: [], label: "Weiter", asks: false },
      });
    });
    vi.mocked(streamContinue).mockImplementation(() => new Promise(() => {}));
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    await pickMarvin();
    await screen.findByRole("button", { name: "Weiter" });
    scrollIntoView.mockClear();

    // "Weiter" adds no student bubble, so nothing else scrolls here: the dots
    // appearing at the thread's end must bring themselves into view.
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" });
  });

  it("scrolls the clearance sentinel, so the newest line clears the mask fully", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        const bottom = this.classList.contains("chat-scroll") ? 500 : 600;
        return { top: 0, bottom, height: 600 } as DOMRect;
      });
    try {
      vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
        onEvent({
          event: "message",
          translating: false,
          text: "Erste Zeile.\n\nZweite Zeile.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });
      await pickMarvin();
      await screen.findByText("Zweite Zeile.", {}, { timeout: 4000 });

      // The follow that lands last must scroll the thread-end sentinel: it
      // carries the 24px mask clearance, so the newest line is fully shown.
      const contexts = vi.mocked(Element.prototype.scrollIntoView).mock.contexts ?? [];
      const last = contexts.at(-1);
      expect(last).toBeDefined();
      expect((last as Element).classList.contains("chat-thread-end")).toBe(true);
    } finally {
      rect.mockRestore();
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("keeps following the settled reply as it paces in, paragraph by paragraph", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    const rect = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        const bottom = this.classList.contains("chat-scroll") ? 500 : 600;
        return { top: 0, bottom, height: 600 } as DOMRect;
      });
    try {
      vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
        onEvent({
          event: "message",
          translating: false,
          text: "Erste Zeile.\n\nZweite Zeile.",
          parts: [],
          hint: { kind: "text", choices: [], asks: false },
        });
      });
      await pickMarvin();

      // The reply outgrows the box while it paces in; every new paragraph must
      // carry the view with it, not reveal below the fold.
      await screen.findByText("Zweite Zeile.", {}, { timeout: 4000 });
      expect(Element.prototype.scrollIntoView).toHaveBeenLastCalledWith({ block: "end" });
    } finally {
      rect.mockRestore();
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("brings the options into view when the question has revealed", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    let deliver: ((event: ChatEvent) => void) | null = null;
    vi.mocked(streamTurn).mockImplementation((_sessionId, _text, onEvent) => {
      deliver = onEvent;
      return new Promise(() => {});
    });
    try {
      const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      await userEvent.type(screen.getByRole("textbox"), "Hallo");
      await userEvent.click(screen.getByRole("button", { name: "Senden" }));
      await act(async () => {
        deliver?.({
          event: "message",
          translating: false,
          text: "Welche Nutzung ist erlaubt?",
          parts: [],
          hint: {
            kind: "choices",
            asks: true,
            choices: [{ key: "a", label: "Text zusammenfassen" }],
          },
        });
      });
      scrollIntoView.mockClear();

      // The grid waits for the question's reveal (D91); when it un-hides it is
      // what the student acts on next, so it brings itself into view.
      await screen.findByRole("button", { name: /Text zusammenfassen/ }, { timeout: 4000 });
      // The scroll is an effect of the commit that shows the grid, and runs a task later.
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" }));
    } finally {
      vi.unstubAllGlobals();
    }
  }, 15000);

  it("offers a jump to the newest line when parked far up, and takes the thread back", async () => {
    vi.mocked(streamTurn).mockImplementation(() => new Promise(() => {}));
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    await pickMarvin();
    await screen.findByRole("textbox");
    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Senden" }));
    // The send's own scroll settle window must pass before a scroll counts as
    // the student's (the park rule).
    await new Promise((resolve) => setTimeout(resolve, 170));
    const scroller = document.querySelector(".chat-scroll") as HTMLDivElement;
    const setMetrics = (scrollTop: number) => {
      for (const [key, value] of [
        ["scrollHeight", 2000],
        ["clientHeight", 500],
        ["scrollTop", scrollTop],
      ]) {
        Object.defineProperty(scroller, key, { value, configurable: true });
      }
    };

    // 1400px from the end: the arrow stands; a click returns to the newest line.
    await act(async () => {
      setMetrics(100);
      scroller.dispatchEvent(new Event("scroll"));
    });
    const jump = document.querySelector(".chat-jump");
    expect(jump).not.toBeNull();
    scrollIntoView.mockClear();
    await userEvent.click(jump!);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "end" });

    // Back near the end the arrow is gone, and the following has resumed.
    await act(async () => {
      setMetrics(1450);
      scroller.dispatchEvent(new Event("scroll"));
    });
    expect(document.querySelector(".chat-jump")).toBeNull();
  });

  describe("the display locale", () => {
    afterEach(async () => {
      await tolgee.changeLanguage("de");
    });

    it("starts a new session in whatever language the flag already shows", async () => {
      await tolgee.changeLanguage("en");
      const toolsSlot = document.body.appendChild(document.createElement("div"));
      render(withProvider(<ChatPage toolsSlot={toolsSlot} />));
      await userEvent.click(await screen.findByRole("button", { name: /Depressobot/ }));
      expect(postSession).toHaveBeenCalledWith("marvin", "en");
    });

    it("writes no display locale just for opening a session", async () => {
      vi.mocked(setDisplayLocale).mockClear();
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      expect(setDisplayLocale).not.toHaveBeenCalled();
    });

    it("pushes a later flip of the flag to the open session", async () => {
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      vi.mocked(setDisplayLocale).mockClear();

      await tolgee.changeLanguage("en");

      await waitFor(() => expect(setDisplayLocale).toHaveBeenCalledWith(7, "en"));
    });

    it("swaps the thread into English on a flip and polls until the translation lands", async () => {
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      vi.mocked(setDisplayLocale).mockResolvedValue({
        ...SESSION,
        display_locale: "en",
        messages: [
          { id: "m-open", role: "assistant", text: "Willkommen beim Kurs.", parts: [], translating: true },
        ],
      });
      vi.mocked(getActiveSession).mockResolvedValue({
        ...SESSION,
        display_locale: "en",
        messages: [
          { id: "m-open", role: "assistant", text: "Welcome to the course.", parts: [], translating: false },
        ],
      });

      await tolgee.changeLanguage("en");

      expect(await screen.findByText("Translating …")).toBeInTheDocument();
      expect(screen.getByText("Willkommen beim Kurs.")).toBeInTheDocument();
      expect(
        await screen.findByText("Welcome to the course.", {}, { timeout: 4000 }),
      ).toBeInTheDocument();
      expect(screen.queryByText("Translating …")).not.toBeInTheDocument();
    });

    it("retexts the answered grid's labels on a flip", async () => {
      vi.mocked(streamOpening).mockImplementation(async (_sessionId, onEvent) => {
        onEvent({
          event: "message",
          translating: false,
          id: "m-open",
          text: "Darf ich?",
          parts: [],
          hint: { kind: "choices", choices: [{ key: "a", label: "Ja, darf ich." }], asks: true },
        });
      });
      await pickMarvin();
      await userEvent.click(await screen.findByRole("button", { name: /Ja, darf ich\./ }));
      await screen.findByText("Guten Tag! Was beschäftigt dich?");
      const enHint = {
        kind: "choices" as const,
        choices: [{ key: "a", label: "Yes, I may." }],
        asks: true,
      };
      vi.mocked(setDisplayLocale).mockResolvedValue({
        ...SESSION,
        display_locale: "en",
        hint: { kind: "yes_no", choices: [], asks: false },
        messages: [
          { id: "m-open", role: "assistant", text: "May I?", parts: [], hint: enHint, translating: false },
          { role: "user", text: "A. Ja, darf ich.", parts: [], hint: null, translating: false },
          {
            role: "assistant",
            id: "m-turn",
            text: "Good day! What is on your mind?",
            parts: [],
            hint: null,
            translating: false,
          },
        ],
      });

      await tolgee.changeLanguage("en");

      expect(await screen.findByRole("button", { name: /Yes, I may\./ })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Ja, darf ich\./ })).not.toBeInTheDocument();
    });

    it("three quick flips leave the thread in the language of the last one", async () => {
      await pickMarvin();
      await screen.findByText("Willkommen beim Kurs.");
      const english = {
        ...SESSION,
        display_locale: "en",
        messages: [
          {
            role: "assistant" as const,
            id: "m-open",
            text: "Welcome to the course.",
            parts: [],
            hint: null,
            translating: false,
          },
        ],
      };
      const german = {
        ...SESSION,
        messages: [
          {
            role: "assistant" as const,
            id: "m-open",
        text: "Willkommen beim Kurs.",
            parts: [],
            hint: null,
            translating: false,
          },
        ],
      };
      vi.mocked(setDisplayLocale).mockImplementation(async (_id, locale) =>
        locale === "en" ? english : german,
      );

      await tolgee.changeLanguage("en");
      await tolgee.changeLanguage("de");
      await tolgee.changeLanguage("en");

      expect(await screen.findByText("Welcome to the course.")).toBeInTheDocument();
      await waitFor(() => expect(setDisplayLocale).toHaveBeenLastCalledWith(7, "en"));
      expect(screen.queryByText("Willkommen beim Kurs.")).not.toBeInTheDocument();
    });

    it("lets a resumed session's own locale win over the flag", async () => {
      vi.mocked(getActiveSession).mockResolvedValue({ ...SESSION, display_locale: "en" });
      render(withProvider(<ChatPage />));

      await screen.findByText("Willkommen beim Kurs.");
      expect(tolgee.getLanguage()).toBe("en");
    });
  });
});
