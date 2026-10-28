import { render, screen } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { tolgee } from "../i18n";
import { FileCard } from "./FileCard";

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const FILE = {
  kind: "file" as const,
  url: "/api/files/abc123",
  title: "Spickzettel: Der ganze Kurs",
  filename: "spickzettel-kurs.pdf",
};

describe("FileCard", () => {
  it("links to the PDF in a new tab", async () => {
    render(withProvider(<FileCard part={FILE} />));
    expect(await screen.findByText("Spickzettel: Der ganze Kurs")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Öffnen/ });
    expect(link).toHaveAttribute("href", "/api/files/abc123");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(screen.queryByText("spickzettel-kurs.pdf")).not.toBeInTheDocument();
  });

  describe("in English", () => {
    afterEach(async () => {
      await tolgee.changeLanguage("de");
    });

    it("notes that the file itself stays German", async () => {
      await tolgee.changeLanguage("en");
      render(withProvider(<FileCard part={FILE} />));
      expect(
        await screen.findByText("The cheat sheet and the certificate are in German."),
      ).toBeInTheDocument();
    });
  });
});
