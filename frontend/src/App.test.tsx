import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { tolgee } from "./i18n";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// What the backend in each test offers, and who is signed in.
let options = { backend: "dev", guest: false };
let signedIn = false;
let inviteStatus = 200;
let posted: { url: string; body: string | undefined }[] = [];

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    options = { backend: "dev", guest: false };
    signedIn = false;
    inviteStatus = 200;
    posted = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          posted.push({ url, body: init.body as string | undefined });
          if (url.endsWith("/api/auth/guest")) {
            signedIn = true;
            return jsonResponse(200, { status: "ok" });
          }
          if (url.endsWith("/api/auth/invite/login")) {
            signedIn = inviteStatus === 200;
            return jsonResponse(inviteStatus, signedIn ? { status: "ok" } : { detail: "invite not valid" });
          }
        }
        if (url.endsWith("/api/auth/options")) return jsonResponse(200, options);
        if (url.endsWith("/api/me") && signedIn) {
          return jsonResponse(200, {
            principal: { subject: "guest-x", name: "Gast", groups: ["guest"], roles: ["student"] },
            data_level: 1,
            stored: [],
          });
        }
        if (url.endsWith("/api/version")) {
          return jsonResponse(200, {
            app: "0.1.0",
            course: "0.1.0",
            law: { celex: "02024R1689-20260727", consolidated: "2026-07-27", amended_by: [] },
            locales: ["de"],
            reference_locale: "de",
          });
        }
        if (url.endsWith("/api/me")) return jsonResponse(401, { detail: "not signed in" });
        if (url.endsWith("/api/auth/dev/users") && options.backend === "dev") {
          return jsonResponse(200, [{ subject: "anna", name: "Anna Beispiel" }]);
        }
        if (url.endsWith("/api/theme")) {
          return jsonResponse(200, {
            primary: "#2563eb",
            secondary: "#0f172a",
            accent: "#f59e0b",
            background: "#f8fafc",
            look: "clean",
          });
        }
        return jsonResponse(404, {});
      }),
    );
  });

  it("names the product and never the regulation number", async () => {
    render(<App />);
    expect(await screen.findByText("KI-Führerschein")).toBeInTheDocument();
    expect(screen.queryByText(/KI-Verordnung Training/)).not.toBeInTheDocument();
  });

  it("offers dev sign-in when signed out and the dev backend is active", async () => {
    render(<App />);
    expect(await screen.findByRole("button", { name: "Anmelden" })).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Anna Beispiel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Demo starten" })).not.toBeInTheDocument();
  });

  it("starts a guest on the demo button when the backend opens the guest door", async () => {
    options = { backend: "invite", guest: true };
    const user = userEvent.setup();
    render(<App />);
    const demo = await screen.findByRole("button", { name: "Demo starten" });
    expect(screen.getByText("Demo: Der Verlauf wird nach sechs Stunden gelöscht.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anmelden" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    await user.click(demo);
    expect(await screen.findByRole("button", { name: "Abmelden" })).toBeInTheDocument();
    expect(posted.map((entry) => entry.url)).toEqual(["/api/auth/guest"]);
    expect(screen.queryByRole("button", { name: "Demo starten" })).not.toBeInTheDocument();
  });

  it("signs in with an invite link and clears the token from the address bar", async () => {
    options = { backend: "invite", guest: true };
    window.history.replaceState(null, "", "/?invite=tok-123");
    render(<App />);
    expect(await screen.findByRole("button", { name: "Abmelden" })).toBeInTheDocument();
    expect(posted).toEqual([
      { url: "/api/auth/invite/login", body: JSON.stringify({ token: "tok-123" }) },
    ]);
    expect(window.location.search).toBe("");
    expect(screen.queryByText("Dieser Link ist nicht mehr gültig.")).not.toBeInTheDocument();
  });

  it("says a refused invite link is no longer valid and still offers the demo", async () => {
    options = { backend: "invite", guest: true };
    inviteStatus = 401;
    window.history.replaceState(null, "", "/?invite=revoked");
    render(<App />);
    expect(await screen.findByText("Dieser Link ist nicht mehr gültig.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Demo starten" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abmelden" })).not.toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  it("starts dark and switches to light on the mode button", async () => {
    const user = userEvent.setup();
    render(<App />);
    const toLight = await screen.findByRole("button", { name: "Hell" });
    expect(document.documentElement.dataset.mode).toBe("dark");
    await user.click(toLight);
    expect(document.documentElement.dataset.mode).toBe("light");
    expect(screen.getByRole("button", { name: "Dunkel" })).toBeInTheDocument();
  });

  it("switches the look on the look button", async () => {
    const user = userEvent.setup();
    render(<App />);
    // the theme endpoint reports the clean look, so the button offers the pixel one
    const toPixel = await screen.findByRole("button", { name: "Pixel" });
    await user.click(toPixel);
    expect(document.documentElement.dataset.look).toBe("pixel");
    expect(screen.getByRole("button", { name: "Klar" })).toBeInTheDocument();
  });

  it("offers the text-face toggle only under the pixel look", async () => {
    const user = userEvent.setup();
    render(<App />);
    // the theme endpoint reports the clean look, so the text toggle stays hidden
    await screen.findByRole("button", { name: "Pixel" });
    expect(screen.queryByRole("button", { name: "Lesbar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pixelschrift" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Pixel" }));
    const toPlain = await screen.findByRole("button", { name: "Lesbar" });
    expect(document.documentElement.dataset.text).toBe("pixel");

    await user.click(toPlain);
    expect(document.documentElement.dataset.text).toBe("plain");
    expect(screen.getByRole("button", { name: "Pixelschrift" })).toBeInTheDocument();
  });

  describe("the language flag", () => {
    afterEach(async () => {
      await tolgee.changeLanguage("de");
    });

    it("switches the UI to English and back on a second click", async () => {
      const user = userEvent.setup();
      render(<App />);
      const toEnglish = await screen.findByRole("button", { name: "English" });
      await user.click(toEnglish);
      expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
      expect(document.documentElement.lang).toBe("en");

      const toGerman = screen.getByRole("button", { name: "Deutsch" });
      await user.click(toGerman);
      expect(await screen.findByRole("button", { name: "Anmelden" })).toBeInTheDocument();
      expect(document.documentElement.lang).toBe("de");
    });
  });
});
