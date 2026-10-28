import { render, screen } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import type { PartOut } from "../api/chat";
import { tolgee } from "../i18n";
import { CitationsPanel } from "./CitationsPanel";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const partA: Extract<PartOut, { kind: "citations" }> = {
  kind: "citations",
  ref: "Art. 4",
  title: "AI-Kompetenz",
  quote: "Anbieter und Betreiber stellen ausreichende KI-Kompetenz sicher.",
  url: "https://eur-lex.europa.eu/ai-act/art-4",
};

const partB: Extract<PartOut, { kind: "citations" }> = {
  kind: "citations",
  ref: "Art. 4(2)",
  title: "AI-Kompetenz, Absatz 2",
  quote: "Betreiber berücksichtigen das technische Wissen des Personals.",
  url: "https://eur-lex.europa.eu/ai-act/art-4-2",
};

describe("CitationsPanel", () => {
  it("renders the ref as a link to the source, with the quote as its tooltip", async () => {
    render(withProvider(<CitationsPanel parts={[partA]} />));
    expect(await screen.findByText("Fundstellen")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Art. 4" });
    expect(link).toHaveAttribute("href", partA.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link).toHaveAttribute("title", partA.quote);
  });

  it("collapses several citations from one message into one line", async () => {
    render(withProvider(<CitationsPanel parts={[partA, partB]} />));
    expect(await screen.findAllByText("Fundstellen")).toHaveLength(1);
    expect(screen.getByText("Art. 4")).toBeInTheDocument();
    expect(screen.getByText("Art. 4(2)")).toBeInTheDocument();
  });

  it("renders nothing without citations", () => {
    const { container } = render(withProvider(<CitationsPanel parts={[]} />));
    expect(container).toBeEmptyDOMElement();
  });
});
