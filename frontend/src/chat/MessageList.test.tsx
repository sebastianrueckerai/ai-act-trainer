import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { tolgee } from "../i18n";
import { MessageList } from "./MessageList";
import { EMPTY } from "./state";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

describe("MessageList", () => {
  it("renders a file part as a file card, without its raw filename", async () => {
    render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Hier ist dein Spickzettel.",
                parts: [
                  {
                    kind: "file",
                    url: "/api/files/abc123",
                    title: "Spickzettel: Der ganze Kurs",
                    filename: "spickzettel-kurs.pdf",
                  },
                ],
              },
            ],
          }}
        />,
      ),
    );
    expect(await screen.findByText("Spickzettel: Der ganze Kurs")).toBeInTheDocument();
    expect(screen.queryByText("spickzettel-kurs.pdf")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Öffnen/ })).toHaveAttribute(
      "href",
      "/api/files/abc123",
    );
    expect(screen.queryByText("Fundstellen")).not.toBeInTheDocument();
  });

  it.each([
    { index: 1, line: "Kapitel 1 geschafft", lit: [true, false, false, false, false, false, false, false] },
    { index: 8, line: "Alle 8 Kapitel geschafft", lit: Array<boolean>(8).fill(true) },
  ])("closes a chapter end on its divider and the route: $line", async ({ index, line, lit }) => {
    render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Richtig.\n\nDas darfst du: üben (Art. 4 Abs. 1).",
                parts: [
                  { kind: "file", url: "/api/files/k", title: "Spickzettel", filename: "k.pdf" },
                  { kind: "chapter_done", chapter_id: "c", index, total: 8, title: "Titel" },
                ],
              },
            ],
          }}
        />,
      ),
    );
    const divider = (await screen.findByText(line)).closest(".chapter-divider");
    expect(divider).not.toBeNull();
    const nodes = Array.from(divider!.querySelectorAll(".chapter-route i"));
    expect(nodes.map((node) => node.hasAttribute("data-lit"))).toEqual(lit);
    expect(divider!.querySelectorAll(".chapter-route s")).toHaveLength(7);
    // The sheet comes first, the divider closes the turn below it.
    const order = Array.from(document.querySelectorAll(".ui-card, .chapter-divider"));
    expect(order.map((node) => node.className.split(" ")[0])).toEqual(["ui-card", "chapter-divider"]);
    // The may line is a paragraph like any other.
    expect(screen.getByText("Das darfst du: üben (Art. 4 Abs. 1).").closest(".ui-bubble")).not.toBeNull();
  });

  it("holds the sheet and the divider back until the turn's text is all there", async () => {
    render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Richtig.\n\nKapitel 1 im Kasten.",
                parts: [
                  { kind: "file", url: "/api/files/k", title: "Spickzettel", filename: "k.pdf" },
                  { kind: "chapter_done", chapter_id: "c", index: 1, total: 8, title: "Titel" },
                ],
              },
            ],
          }}
          revealed={1}
        />,
      ),
    );
    await screen.findByText("Richtig.");
    expect(screen.queryByText("Spickzettel")).not.toBeInTheDocument();
    expect(screen.queryByText("Kapitel 1 geschafft")).not.toBeInTheDocument();
  });

  it("opens the next chapter on its level card: the title, then the intro, then the step", async () => {
    render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Bevor du etwas hineinkopierst, prüfst du drei Dinge.",
                parts: [
                  { kind: "chapter_start", title: "Was du hineingeben darfst", intro: "Eine Frage jeden Tag." },
                ],
              },
            ],
          }}
        />,
      ),
    );
    const title = await screen.findByRole("heading", { name: "Was du hineingeben darfst" });
    expect(title).toHaveClass("level-card-title");
    const blocks = Array.from(document.querySelectorAll(".message > *")).map((node) => node.textContent);
    expect(blocks).toEqual([
      "Was du hineingeben darfst",
      "Eine Frage jeden Tag.",
      "Bevor du etwas hineinkopierst, prüfst du drei Dinge.",
    ]);
  });

  it("renders a message's verdict card above its own bubble text", async () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Weiter geht's mit der nächsten Frage.",
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
              },
            ],
          }}
        />,
      ),
    );
    const card = await screen.findByText("Wann greift Art. 5?");
    const bubble = screen.getByText("Weiter geht's mit der nächsten Frage.");
    // both share the container: the card node must precede the bubble node.
    expect(card.compareDocumentPosition(bubble) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector(".ui-card")?.compareDocumentPosition(
      container.querySelector(".ui-bubble")!,
    )).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("renders a card-only message without an empty bubble", async () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
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
              },
            ],
          }}
        />,
      ),
    );
    expect(await screen.findByText("Wann greift Art. 5?")).toBeInTheDocument();
    expect(container.querySelector(".ui-bubble")).toBeNull();
  });

  it("renders the citations line inside the bubble, as its last block", async () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Anbieter stellen KI-Kompetenz sicher.",
                parts: [
                  {
                    kind: "citations",
                    ref: "Art. 4",
                    title: "AI-Kompetenz",
                    quote: "Anbieter und Betreiber stellen ausreichende KI-Kompetenz sicher.",
                    url: "https://eur-lex.europa.eu/ai-act/art-4",
                  },
                ],
              },
            ],
          }}
        />,
      ),
    );
    const bubble = container.querySelector(".ui-bubble");
    const citations = bubble?.querySelector(".citations-line");
    expect(citations).not.toBeNull();
    expect(await screen.findByText("Art. 4")).toBeInTheDocument();
  });

  it("splits a reply on its blank lines into one bubble per paragraph", async () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Erster Absatz.\n\nZweiter Absatz.\n\nDritter Absatz.",
                parts: [
                  {
                    kind: "citations",
                    ref: "Art. 4",
                    title: "AI-Kompetenz",
                    quote: "Anbieter und Betreiber stellen ausreichende KI-Kompetenz sicher.",
                    url: "https://eur-lex.europa.eu/ai-act/art-4",
                  },
                ],
              },
            ],
          }}
        />,
      ),
    );
    const bubbles = container.querySelectorAll(".ui-bubble");
    expect(bubbles).toHaveLength(3);
    expect(bubbles[0]).toHaveTextContent("Erster Absatz.");
    expect(bubbles[1]).toHaveTextContent("Zweiter Absatz.");
    expect(bubbles[2]).toHaveTextContent("Dritter Absatz.");
    // the citations line trails the turn, so only its last bubble carries it
    expect(bubbles[0].querySelector(".citations-line")).toBeNull();
    expect(bubbles[1].querySelector(".citations-line")).toBeNull();
    expect(bubbles[2].querySelector(".citations-line")).not.toBeNull();
    expect(await screen.findByText("Art. 4")).toBeInTheDocument();
  });

  it("marks the last bubble of the latest assistant turn when the hint asks a question", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              { role: "assistant", text: "Erstens.\n\nZweitens?", parts: [] },
              { role: "user", text: "Antwort", parts: [] },
              { role: "assistant", text: "Drittens.\n\nViertens?", parts: [] },
            ],
          }}
          hint={{ kind: "text", choices: [], asks: true }}
        />,
      ),
    );
    const marked = container.querySelectorAll(".ui-bubble--question");
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Viertens?");
  });

  it("marks no bubble when the hint does not end on a question", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [{ role: "assistant", text: "Erstens.\n\nZweitens.", parts: [] }],
          }}
          hint={{ kind: "text", choices: [], asks: false }}
        />,
      ),
    );
    expect(container.querySelectorAll(".ui-bubble--question")).toHaveLength(0);
  });

  it("marks the newest assistant message as the scroll target, not an earlier one", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              { role: "assistant", text: "Erstens.", parts: [] },
              { role: "user", text: "Weiter", parts: [] },
              { role: "assistant", text: "Zweitens.", parts: [] },
            ],
          }}
        />,
      ),
    );
    const marked = container.querySelectorAll('[data-latest-assistant="true"]');
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Zweitens.");
  });

  it("marks the streaming placeholder as the scroll target while it grows", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [{ role: "assistant", text: "Erstens.", parts: [] }],
            streaming: "Zwei…",
          }}
        />,
      ),
    );
    const marked = container.querySelectorAll('[data-latest-assistant="true"]');
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Zwei…");
  });

  it("keeps one typing indicator under the streaming text until the turn settles", () => {
    const { container } = render(
      withProvider(<MessageList state={{ ...EMPTY, sending: true, streaming: "Zwei…" }} />),
    );
    const bubble = container.querySelector('[data-latest-assistant="true"]');
    expect(bubble).toHaveTextContent("Zwei…");
    expect(bubble?.querySelector(".chat-cursor")).toBeNull();
    expect(bubble?.querySelector(".chat-wait")).toBeNull();
    // One indicator for the whole turn, placed after the streaming text.
    const dots = container.querySelectorAll(".chat-wait");
    expect(dots).toHaveLength(1);
    expect(
      bubble!.compareDocumentPosition(dots[0]!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows the step's line beside the dots once a turn has run three seconds", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(
        withProvider(
          <MessageList state={{ ...EMPTY, sending: true, working: "Die Beute wird gewogen." }} />,
        ),
      );
      const bubble = container.querySelector(".chat-wait-bubble");
      expect(bubble?.querySelector(".chat-wait")).not.toBeNull();
      // A quick reply gets dots alone: the line is for a turn that takes its time.
      expect(bubble?.querySelector(".chat-working")).toBeNull();
      act(() => vi.advanceTimersByTime(2900));
      expect(bubble?.querySelector(".chat-working")).toBeNull();
      act(() => vi.advanceTimersByTime(100));
      expect(bubble).toHaveTextContent("Die Beute wird gewogen.");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the step's line alone while a typed answer's verdict is pending", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(
        withProvider(
          <MessageList
            state={{ ...EMPTY, sending: true, working: "prüft deine Antwort" }}
            awaitingVerdict
          />,
        ),
      );
      act(() => vi.advanceTimersByTime(3000));
      expect(container.querySelector(".chat-wait")).toBeNull();
      expect(container.querySelector(".chat-working-bare")).toHaveTextContent(
        "prüft deine Antwort",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("starts the three seconds afresh with every turn", () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        withProvider(<MessageList state={{ ...EMPTY, sending: true, working: "liest" }} />),
      );
      act(() => vi.advanceTimersByTime(3000));
      expect(container.querySelector(".chat-working")).not.toBeNull();
      rerender(withProvider(<MessageList state={{ ...EMPTY, sending: false }} />));
      rerender(withProvider(<MessageList state={{ ...EMPTY, sending: true, working: "liest" }} />));
      expect(container.querySelector(".chat-working")).toBeNull();
      act(() => vi.advanceTimersByTime(3000));
      expect(container.querySelector(".chat-working")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a waiting indicator once sending starts, before any token arrives", () => {
    const { container } = render(withProvider(<MessageList state={{ ...EMPTY, sending: true }} />));
    expect(container.querySelector(".chat-wait")).not.toBeNull();
    expect(screen.getByLabelText("Antwort wird vorbereitet …")).toBeInTheDocument();
  });

  it("keeps the one labelled bubble lit from the click through the stream", () => {
    const { container } = render(
      withProvider(<MessageList state={{ ...EMPTY, sending: true, streaming: "Gu" }} />),
    );
    expect(screen.getByLabelText("Antwort wird vorbereitet …")).toBeInTheDocument();
    expect(container.querySelectorAll(".chat-wait-bubble")).toHaveLength(1);
  });

  it("hides the waiting indicator when nothing is being sent", () => {
    const { container } = render(withProvider(<MessageList state={{ ...EMPTY, sending: false }} />));
    expect(container.querySelector(".chat-wait")).toBeNull();
  });

  it("renders a choices hint as the last block of the latest assistant message only", async () => {
    const onSend = vi.fn();
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              { role: "assistant", text: "Erstens.", parts: [] },
              { role: "user", text: "Weiter", parts: [] },
              { role: "assistant", text: "Zweitens?", parts: [] },
            ],
          }}
          hint={{
            kind: "choices",
            choices: [
              { key: "A", label: "Ja" },
              { key: "B", label: "Nein" },
            ],
            asks: false,
          }}
          onSend={onSend}
        />,
      ),
    );
    const grids = container.querySelectorAll(".message-choices");
    expect(grids).toHaveLength(1);
    const latest = container.querySelector('[data-latest-assistant="true"]');
    expect(latest?.querySelector(".message-choices")).not.toBeNull();

    await userEvent.click(await screen.findByRole("button", { name: "A. Ja" }));
    expect(onSend).toHaveBeenCalledWith("A", "A. Ja");
  });

  it("renders each answered grid inside the turn it answered, verdict and all", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              { role: "assistant", text: "Erste Frage?", parts: [] },
              { role: "user", text: "A. Ja", parts: [] },
              { role: "assistant", text: "Zweite Frage?", parts: [] },
              { role: "user", text: "B. Nein", parts: [] },
            ],
          }}
          hint={{ kind: "text", choices: [], asks: false }}
          answered={[
            {
              turn: 0,
              hint: { kind: "choices", choices: [{ key: "A", label: "Ja" }], asks: false },
              result: { key: "A", verdict: "ok", settled: true },
            },
            {
              turn: 2,
              hint: { kind: "choices", choices: [{ key: "B", label: "Nein" }], asks: false },
              result: { key: "B", verdict: "miss", settled: false },
            },
          ]}
        />,
      ),
    );
    // The picked chip is the answer: the student's replies to the two answered
    // questions draw no bubble of their own.
    const messages = [...container.querySelectorAll(".message")];
    expect(messages).toHaveLength(2);
    expect(container.querySelectorAll(".message--user")).toHaveLength(0);

    // The settled verdict keeps its green; the unsettled one still pulses red.
    const firstGrid = messages[0].querySelector(".message-choices");
    expect(firstGrid).not.toBeNull();
    expect(firstGrid).toHaveClass("message-choices--settled");
    expect(firstGrid?.querySelector(".chip-verdict--ok")).not.toBeNull();
    const secondGrid = messages[1].querySelector(".message-choices");
    expect(secondGrid).not.toBeNull();
    expect(secondGrid).not.toHaveClass("message-choices--settled");
    expect(secondGrid?.querySelector(".chip-flash--miss")).not.toBeNull();
    expect(container.querySelectorAll(".message-choices")).toHaveLength(2);
  });

  it("hides the choices grid while a modal confirmation is open", () => {
    const { container } = render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [{ role: "assistant", text: "Zweitens?", parts: [] }],
          }}
          hint={{ kind: "choices", choices: [{ key: "A", label: "Ja" }], asks: false }}
          hideChoices
        />,
      ),
    );
    expect(container.querySelector(".message-choices")).toBeNull();
  });

  it("keeps a translating message's paragraphs and cards in place under the indicator", () => {
    render(
      withProvider(
        <MessageList
          state={{
            ...EMPTY,
            messages: [
              {
                role: "assistant",
                text: "Erster Absatz.\n\nZweiter Absatz.",
                parts: [
                  {
                    kind: "card",
                    question: "Darf ich?",
                    model_answer: "Ja.",
                    explanation: "Weil.",
                    citations: [],
                    correct: true,
                    tries: 1,
                  },
                ],
                hint: null,
                translating: true,
              },
            ],
          }}
        />,
      ),
    );
    const message = screen.getByText("Erster Absatz.").closest(".message");
    expect(message?.className).toContain("message--translating");
    expect(message?.getAttribute("aria-busy")).toBe("true");
    expect(message?.querySelectorAll(".ui-bubble")).toHaveLength(2);
    expect(screen.getByText("Darf ich?")).toBeInTheDocument();
    expect(screen.getByText("Wird übersetzt …").className).toContain("sr-only");
  });
});
