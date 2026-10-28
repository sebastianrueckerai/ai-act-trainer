import type {
  BudgetState,
  ChatEvent,
  InputHint,
  PartOut,
  SessionResponse,
  Stage,
} from "../api/chat";

export type ChatMessage = {
  // The stored message's id; a student message the page appended itself has none.
  id?: string | null;
  role: "user" | "assistant";
  text: string;
  parts: PartOut[];
  // The hint the turn ended on, in the display locale; null on a student message.
  hint?: InputHint | null;
  // The text still shows the stored German while its translation is on its way.
  translating?: boolean;
};

export type ChatState = {
  messages: ChatMessage[];
  streaming: string;
  // The step that runs now, in the character's words, for the line beside the dots.
  working: string;
  hint: InputHint;
  sending: boolean;
  error: string;
  stage: Stage | null;
  // While exhausted, a notice stands above the composer and the composer is off.
  budget: BudgetState;
};

export type Action =
  | { type: "hydrate"; session: SessionResponse }
  // A flag flip: the thread's texts change language in place, the turn in flight,
  // its hint and its stage stay as they are.
  | { type: "retext"; session: SessionResponse }
  | { type: "event"; event: ChatEvent }
  | { type: "user_message"; text: string }
  | { type: "sending" }
  | { type: "budget"; budget: BudgetState }
  | { type: "reset" };

export const EMPTY: ChatState = {
  messages: [],
  streaming: "",
  working: "",
  hint: { kind: "text", asks: false },
  sending: false,
  error: "",
  stage: null,
  budget: { state: "ok" },
};

const REFUSED: BudgetState = { state: "exhausted", scope: "global", resets_at: null };

function fromSession(message: SessionResponse["messages"][number]): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.text,
    parts: message.parts ?? [],
    hint: message.hint,
    translating: message.translating,
  };
}

function hydrate(session: SessionResponse): ChatState {
  return {
    messages: session.messages.map(fromSession),
    streaming: "",
    working: "",
    hint: session.hint,
    sending: false,
    error: "",
    stage: session.stage,
    budget: session.budget,
  };
}

function isStage(payload: Record<string, unknown>): payload is Stage {
  const stage = payload as Partial<Stage>;
  return (
    typeof stage.mood === "string" && typeof stage.streak === "number" && Array.isArray(stage.chapters)
  );
}

function applyEvent(state: ChatState, event: ChatEvent): ChatState {
  switch (event.event) {
    case "token":
      return { ...state, streaming: state.streaming + event.text };
    case "working":
      return { ...state, working: event.text };
    case "message":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: event.id,
            role: "assistant",
            text: event.text,
            parts: event.parts ?? [],
            hint: event.hint,
            translating: event.translating,
          },
        ],
        streaming: "",
        working: "",
        hint: event.hint,
        sending: false,
        error: "",
      };
    case "input_hint":
      return { ...state, hint: event.hint };
    case "error":
      return event.code === "limit"
        ? { ...state, streaming: "", working: "", sending: false, budget: event.budget ?? REFUSED }
        : { ...state, streaming: "", working: "", sending: false, error: event.message };
    case "ui":
      if (event.name === "stage" && event.payload && isStage(event.payload)) {
        return { ...state, stage: event.payload };
      }
      return state;
    default:
      return state;
  }
}

export function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "hydrate":
      return hydrate(action.session);
    case "retext": {
      const idle = !state.sending && state.streaming === "";
      // By id, never by position: the server compacts old turns away while the page
      // keeps every one it showed.
      const fresh = new Map(action.session.messages.map((message) => [message.id, message]));
      return {
        ...state,
        hint: idle ? action.session.hint : state.hint,
        messages: state.messages.map((message) => {
          const served = message.id ? fresh.get(message.id) : undefined;
          return served === undefined ? message : fromSession(served);
        }),
      };
    }
    case "event":
      return applyEvent(state, action.event);
    case "user_message":
      return {
        ...state,
        messages: [...state.messages, { role: "user", text: action.text, parts: [] }],
        error: "",
      };
    case "sending":
      return { ...state, sending: true, working: "" };
    case "budget":
      return { ...state, budget: action.budget };
    case "reset":
      return EMPTY;
  }
}
