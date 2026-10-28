import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useTheme } from "./useTheme";

function Harness() {
  const { look, mode, text } = useTheme();
  return (
    <div>
      <span data-testid="look">{look}</span>
      <span data-testid="mode">{mode}</span>
      <span data-testid="text">{text}</span>
    </div>
  );
}

function stubTheme(look: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        primary: "#38bdf8",
        secondary: "#16233a",
        accent: "#fbbf24",
        background: "#f8fafc",
        look,
      }),
    })),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("adopts the server look when the user has never chosen", async () => {
  stubTheme("pixel");
  render(<Harness />);
  expect(await screen.findByText("pixel", { selector: "[data-testid=look]" })).toBeInTheDocument();
  expect(document.documentElement.dataset.look).toBe("pixel");
  // the stub mirrors DEFAULT_COLORS so the assertion holds whether or not the
  // fetch has resolved by the time findByText settles (both give the same palette)
  expect(document.documentElement.style.getPropertyValue("--c-primary")).toBe("#39bffb");
});

it("keeps a stored look over the server default", async () => {
  window.localStorage.setItem("look", "clean");
  stubTheme("pixel");
  render(<Harness />);
  await screen.findByText("clean", { selector: "[data-testid=look]" });
});

it("falls back to the default palette when the theme endpoint is down", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })),
  );
  render(<Harness />);
  await screen.findByText("pixel", { selector: "[data-testid=look]" });
  // the Tiefsee seeds (DEFAULT_COLORS), quantized for the pixel look and dark mode (D55)
  const style = document.documentElement.style;
  expect(style.getPropertyValue("--c-primary")).toBe("#39bffb");
  expect(style.getPropertyValue("--c-accent")).toBe("#fbc031");
  expect(style.getPropertyValue("--c-bg")).toBe("#0a121f");
  expect(style.getPropertyValue("--c-text")).toBe("#d0d8e5");
});

it("starts on the pixel face and keeps a stored readable choice", async () => {
  stubTheme("pixel");
  const { unmount } = render(<Harness />);
  expect(await screen.findByText("pixel", { selector: "[data-testid=text]" })).toBeInTheDocument();
  expect(document.documentElement.dataset.text).toBe("pixel");
  unmount();

  window.localStorage.setItem("text", "plain");
  render(<Harness />);
  await screen.findByText("plain", { selector: "[data-testid=text]" });
  expect(document.documentElement.dataset.text).toBe("plain");
});

it("starts dark and keeps a stored light choice", async () => {
  stubTheme("pixel");
  const { unmount } = render(<Harness />);
  expect(await screen.findByText("dark", { selector: "[data-testid=mode]" })).toBeInTheDocument();
  expect(document.documentElement.dataset.mode).toBe("dark");
  unmount();

  window.localStorage.setItem("mode", "light");
  render(<Harness />);
  await screen.findByText("light", { selector: "[data-testid=mode]" });
  expect(document.documentElement.dataset.mode).toBe("light");
});
