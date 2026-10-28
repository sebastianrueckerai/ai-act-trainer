import { render, screen } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import type { PartOut } from "../api/chat";
import { tolgee } from "../i18n";
import { ModelAnswerCard } from "./ModelAnswerCard";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const card: Extract<PartOut, { kind: "card" }> = {
  kind: "card",
  question: "Welche Praxis ist verboten?",
  model_answer: "Social scoring ist verboten.",
  explanation: "Art. 5 Abs. 1 verbietet bestimmte Praktiken.",
  citations: [
    {
      kind: "citations",
      ref: "Art. 5",
      title: "Verbotene Praktiken im Bereich der KI",
      quote: "Folgende Praktiken im Bereich der KI sind verboten",
      url: "https://eur-lex.europa.eu/eli/reg/2024/1689/oj#art_5",
    },
  ],
  correct: true,
  tries: 1,
};

describe("ModelAnswerCard", () => {
  it("renders question, labels and the correct badge", async () => {
    render(withProvider(<ModelAnswerCard part={card} />));
    expect(await screen.findByText("Welche Praxis ist verboten?")).toBeInTheDocument();
    expect(screen.getByText("Musterantwort")).toBeInTheDocument();
    expect(screen.getByText("Social scoring ist verboten.")).toBeInTheDocument();
    expect(screen.getByText("Erklärung")).toBeInTheDocument();
    expect(screen.getByText("Richtig")).toBeInTheDocument();

    const citation = screen.getByRole("link", { name: "Art. 5" });
    expect(citation).toHaveAttribute("href", "https://eur-lex.europa.eu/eli/reg/2024/1689/oj#art_5");
    expect(citation).toHaveAttribute("target", "_blank");
    expect(citation).toHaveAttribute("rel", "noreferrer");
  });

  it("settles a second-try answer instead of calling it right", async () => {
    render(withProvider(<ModelAnswerCard part={{ ...card, tries: 2 }} />));
    expect(await screen.findByText("Geklärt")).toBeInTheDocument();
    expect(screen.queryByText("Richtig")).not.toBeInTheDocument();
  });

  it("shows the incorrect badge when the answer was wrong", async () => {
    render(withProvider(<ModelAnswerCard part={{ ...card, correct: false }} />));
    expect(await screen.findByText("Leider falsch")).toBeInTheDocument();
    expect(screen.queryByText("Richtig")).not.toBeInTheDocument();
  });
});
