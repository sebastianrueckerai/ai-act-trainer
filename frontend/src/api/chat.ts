import type { components, operations } from "./schema";

export type ChatEvent =
  operations["post_turn_api_chat__session_id__turns_post"]["responses"][200]["content"]["application/json"];
export type SessionResponse = components["schemas"]["SessionResponse"];
export type BudgetState = components["schemas"]["BudgetState"];
export type InputHint = components["schemas"]["InputHint"];
export type CardOut = components["schemas"]["CardOut"];
export type PartOut =
  | CardOut
  | components["schemas"]["CitationsOut"]
  | components["schemas"]["FileOut"]
  | components["schemas"]["ChapterDoneOut"]
  | components["schemas"]["ChapterStartOut"];
export type Stage = components["schemas"]["StageBlock"];

async function requireOk(response: Response): Promise<Response> {
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response;
}

export async function postSession(
  personaId: string,
  displayLocale: "de" | "en" = "de",
): Promise<SessionResponse> {
  const response = await requireOk(
    await fetch("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ persona_id: personaId, display_locale: displayLocale }),
    }),
  );
  return (await response.json()) as SessionResponse;
}

export async function setDisplayLocale(
  sessionId: number,
  displayLocale: "de" | "en",
): Promise<SessionResponse> {
  const response = await requireOk(
    await fetch(`/api/session/${sessionId}/display-locale`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ display_locale: displayLocale }),
    }),
  );
  return (await response.json()) as SessionResponse;
}

// null when the student has not picked a persona yet: the picker opens instead.
export async function getActiveSession(): Promise<SessionResponse | null> {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  if (response.status === 404) return null;
  return (await (await requireOk(response)).json()) as SessionResponse;
}

export async function closeSession(): Promise<void> {
  await requireOk(await fetch("/api/session/close", { method: "POST" }));
}

async function readEvents(response: Response, onEvent: (event: ChatEvent) => void): Promise<void> {
  const body = response.body;
  if (body === null) throw new Error("empty stream");
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (dataLine) onEvent(JSON.parse(dataLine.slice(6)) as ChatEvent);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function streamOpening(
  sessionId: number,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await requireOk(
    await fetch(`/api/chat/${sessionId}/opening`, { method: "POST", signal }),
  );
  await readEvents(response, onEvent);
}

export async function streamContinue(
  sessionId: number,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await requireOk(
    await fetch(`/api/chat/${sessionId}/continue`, { method: "POST", signal }),
  );
  await readEvents(response, onEvent);
}

export async function streamTurn(
  sessionId: number,
  text: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
  shown?: string,
): Promise<void> {
  const response = await requireOk(
    await fetch(`/api/chat/${sessionId}/turns`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(shown === undefined ? { text } : { text, shown }),
      signal,
    }),
  );
  await readEvents(response, onEvent);
}
