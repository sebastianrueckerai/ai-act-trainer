import { afterEach, describe, expect, it, vi } from "vitest";
import {
  closeSession,
  getActiveSession,
  postSession,
  setDisplayLocale,
  streamOpening,
  streamTurn,
} from "./chat";

const fakeFetch = (body: string, splitAt?: number) => {
  const chunks =
    splitAt === undefined ? [body] : [body.slice(0, splitAt), body.slice(splitAt)];
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return vi.fn().mockResolvedValue(
    new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } }),
  );
};

afterEach(() => vi.unstubAllGlobals());

describe("streamTurn", () => {
  it("parses SSE frames and reports events in order", async () => {
    const body =
      'event: status\ndata: {"event":"status","node":"triage"}\n\n' +
      'event: token\ndata: {"event":"token","text":"Gu"}\n\n' +
      'event: token\ndata: {"event":"token","text":"ten Tag"}\n\n';
    vi.stubGlobal("fetch", fakeFetch(body, 30));
    const events: unknown[] = [];
    await streamTurn(1, "Hallo", (e) => events.push(e));
    expect(events).toEqual([
      { event: "status", node: "triage" },
      { event: "token", text: "Gu" },
      { event: "token", text: "ten Tag" },
    ]);
  });

  it("rejects on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
    await expect(streamTurn(1, "Hallo", () => {})).rejects.toBeInstanceOf(Error);
  });
});

describe("streamOpening", () => {
  it("posts to the opening endpoint and parses its frames", async () => {
    const body = 'event: status\ndata: {"event":"status","node":"lesson_step"}\n\n';
    vi.stubGlobal("fetch", fakeFetch(body));
    const events: unknown[] = [];
    await streamOpening(4, (e) => events.push(e));
    expect(events).toEqual([{ event: "status", node: "lesson_step" }]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/chat/4/opening",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("postSession", () => {
  it("posts the chosen persona and returns the session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: 3,
            persona_id: "pirate",
            phase: "lesson",
            hint: { kind: "text", choices: [] },
            messages: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    const session = await postSession("pirate");
    expect(session.id).toBe(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/session",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ persona_id: "pirate", display_locale: "de" }),
      }),
    );
  });
});

describe("setDisplayLocale", () => {
  it("puts the chosen locale and returns the updated session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: 3,
            persona_id: "pirate",
            phase: "lesson",
            hint: { kind: "text", choices: [] },
            messages: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    const session = await setDisplayLocale(3, "en");
    expect(session.id).toBe(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/session/3/display-locale",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ display_locale: "en" }),
      }),
    );
  });
});

describe("getActiveSession", () => {
  it("returns null when no session is open yet", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
    expect(await getActiveSession()).toBeNull();
  });
});

describe("closeSession", () => {
  it("posts to the close endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await closeSession();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/session/close",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
    await expect(closeSession()).rejects.toBeInstanceOf(Error);
  });
});
