import { render } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import { describe, expect, it } from "vitest";
import { tolgee } from "../i18n";
import { GALLERY_SECTIONS, GalleryPage } from "./GalleryPage";

describe("GalleryPage", () => {
  it("renders every section in both looks and both modes with stable selectors", () => {
    render(
      <TolgeeProvider tolgee={tolgee} fallback="…">
        <GalleryPage />
      </TolgeeProvider>,
    );

    expect(GALLERY_SECTIONS).toContain("buttons");
    for (const id of GALLERY_SECTIONS) {
      const nodes = document.querySelectorAll(`[data-gallery='${id}']`);
      expect(nodes.length, id).toBe(5);
      const columns = Array.from(nodes).map((node) => {
        const column = node.closest("[data-look]");
        return `${column?.getAttribute("data-look")} ${column?.getAttribute("data-mode")} ${column?.getAttribute("data-text")}`;
      });
      expect(columns).toEqual([
        "pixel dark pixel",
        "clean dark pixel",
        "pixel light pixel",
        "clean light pixel",
        "pixel dark plain",
      ]);
      // the fifth column shares look and mode with the first, so only the text
      // face tells them apart: every selector gallery.spec.ts uses must be unique.
      expect(new Set(columns).size).toBe(columns.length);
    }
  });
});
