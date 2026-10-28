import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import de from "./locales/de.json";
import en from "./locales/en.json";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("i18n", () => {
  it("stamps German on the document whatever language the browser prefers", async () => {
    document.documentElement.lang = "";
    vi.stubGlobal("navigator", { language: "en-GB" });
    vi.resetModules();
    await import("./i18n");
    expect(document.documentElement.lang).toBe("de");
  });

  it("stamps the language stored from an earlier visit", async () => {
    localStorage.setItem("lang", "en");
    document.documentElement.lang = "";
    vi.resetModules();
    await import("./i18n");
    expect(document.documentElement.lang).toBe("en");
  });

  it("titles the tab in the visit's language", async () => {
    document.title = "";
    vi.resetModules();
    await import("./i18n");
    expect(document.title).toBe(de["app.title"]);

    localStorage.setItem("lang", "en");
    document.title = "";
    vi.resetModules();
    await import("./i18n");
    expect(document.title).toBe(en["app.title"]);
  });

  it("has every German key in English too", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(de).sort());
  });
});
