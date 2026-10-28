import { useEffect, useState, type ReactNode } from "react";
import { useTranslate } from "@tolgee/react";
import type { InputHint, PartOut } from "../api/chat";
import { ChapterDivider, LevelCard } from "./ChapterMarks";
import { CitationsPanel } from "./CitationsPanel";
import { FileCard } from "./FileCard";
import { ChoiceGrid } from "./InputControl";
import { ModelAnswerCard } from "./ModelAnswerCard";
import { Bubble } from "../ui";
import type { ChatMessage, ChatState } from "./state";

function isCitations(part: PartOut): part is Extract<PartOut, { kind: "citations" }> {
  return part.kind === "citations";
}

function isCard(part: PartOut): part is Extract<PartOut, { kind: "card" }> {
  return part.kind === "card";
}

// A blank line is the tutor's own paragraph break: one bubble per paragraph,
// so a long turn reads as a few short messages instead of one wall of text.
export function paragraphsOf(text: string, hasFooter: boolean): string[] {
  const split = text.split(/\n[ \t]*\n/).filter((paragraph) => paragraph !== "");
  if (split.length > 0) return split;
  return hasFooter ? [""] : [];
}

// The tutor bolds with asterisks while it types; a bubble never shows them.
export function streamedParagraphs(streaming: string): string[] {
  return paragraphsOf(streaming.replace(/\*{1,3}/g, ""), false);
}

// The scroll target for req 4: the newest assistant message (or, while streaming,
// the growing placeholder bubble) so its top can be brought into view.
export const LATEST_ASSISTANT_SELECTOR = '[data-latest-assistant="true"]';

// One answered choices question: which turn asked it, the hint it showed, and
// the verdict on the pick. The grid stays with its question for the rest of
// the session (D104); the verdict settles from a pulse into a steady tint.
export type AnsweredTurn = {
  turn: number;
  hint: InputHint;
  result: { key: string; verdict: Verdict | null; settled: boolean } | null;
};

// Green, orange or red, for a picked chip and a typed answer alike.
export type Verdict = "ok" | "partial" | "miss";

export type TypedVerdict = { turn: number; verdict: Verdict; settled: boolean };

export function MessageBubble({
  message,
  latest = false,
  question = false,
  choices = null,
  revealed,
  held = false,
  own = null,
}: {
  message: ChatMessage;
  latest?: boolean;
  // How many of this message's paragraphs are on screen: a turn arrives at
  // reading pace, not all at once (D97).
  revealed?: number;
  // The turn ends on a question the student is meant to answer (D86): its
  // last bubble is marked so the theme can set it apart.
  question?: boolean;
  // The latest message's own choices hint, rendered as the turn's last block
  // so the options scroll with the question that ends the bubble above them.
  choices?: ReactNode;
  // The confetti is playing: the newest turn waits, silent, until it is gone —
  // no new line and no typing dots before the celebration has played out.
  held?: boolean;
  // The verdict on this typed answer: the bubble pulses, then keeps the tint.
  own?: TypedVerdict | null;
}) {
  const { t } = useTranslate();
  const citations = message.parts.filter(isCitations);
  const all = paragraphsOf(message.text, citations.length > 0);
  const paragraphs = revealed === undefined ? all : all.slice(0, revealed);
  return (
    <div
      className={`message message--${message.role} flex flex-col gap-[8px] ${message.role === "user" ? "self-end items-end" : "self-start items-start"}${message.translating ? " message--translating" : ""}`}
      data-latest-assistant={latest ? "true" : undefined}
      aria-busy={message.translating ? "true" : undefined}
    >
      {message.translating && <span className="sr-only">{t("chat.translating")}</span>}
      {!held && (
        <>
          {message.parts.filter(isCard).map((part, partIndex) => (
            <ModelAnswerCard key={`card-${partIndex}`} part={part} />
          ))}
          {message.parts.map((part, partIndex) =>
            part.kind === "chapter_start" ? <LevelCard key={`level-${partIndex}`} part={part} /> : null,
          )}
          {paragraphs.map((paragraph, index) => {
            const isLast = index === all.length - 1;
            return (
              <Bubble
                key={index}
                role={message.role}
                className={[
                  isLast && question ? "ui-bubble--question" : undefined,
                  own
                    ? `own-${own.settled ? "verdict" : "flash"}--${own.verdict}`
                    : undefined,
                ]
                  .filter(Boolean)
                  .join(" ") || undefined}
                footer={isLast ? <CitationsPanel parts={citations} /> : undefined}
              >
                {paragraph}
              </Bubble>
            );
          })}
        </>
      )}
      {!held && (
        <>
          {/* The sheet and the chapter's divider close the turn, once its text is all there. */}
          {paragraphs.length === all.length &&
            message.parts.map((part, partIndex) =>
              part.kind === "file" ? (
                <FileCard key={partIndex} part={part} />
              ) : part.kind === "chapter_done" ? (
                <ChapterDivider key={partIndex} part={part} />
              ) : null,
            )}
          {choices}
        </>
      )}
    </div>
  );
}

const WORKING_LINE_AFTER_MS = 3000;

export function MessageList({
  state,
  hint = { kind: "text", choices: [], asks: false },
  disabled = false,
  hideChoices = false,
  onSend = () => {},
  revealed,
  revealing = false,
  answered = [],
  typed = [],
  awaitingVerdict = false,
  replay = null,
  holding = false,
}: {
  state: ChatState;
  hint?: InputHint;
  disabled?: boolean;
  // Set while a modal confirmation (e.g. restart) is open.
  hideChoices?: boolean;
  onSend?: (text: string, shown?: string) => void;
  // The newest turn's revealed paragraph count; undefined shows the whole turn.
  revealed?: number;
  revealing?: boolean;
  // The choices questions already answered, each kept inside the turn that
  // asked it (D104).
  answered?: AnsweredTurn[];
  // The verdicts on the student's typed answers, each on its own bubble.
  typed?: TypedVerdict[];
  // An answer's grade is pending: the tutor has nothing to type yet, so the
  // indicator stays dark instead of promising and being revoked.
  awaitingVerdict?: boolean;
  // A resumed thread replays: how many message blocks are on screen so far, or
  // null when the thread is not replaying.
  replay?: number | null;
  // The confetti is playing: the newest turn waits until it is gone.
  holding?: boolean;
}) {
  const { t } = useTranslate();
  // The turn in progress is the last message when it is the tutor's: while a reply
  // streams in, the placeholder bubble is that turn; once it settles into a real
  // message, the message takes the mark. The tutor's previous turn is never it —
  // it must not be paced (or blanked) while the student's own message waits for
  // the model.
  const lastIndex = state.messages.length - 1;
  const latest =
    state.streaming === "" && state.messages[lastIndex]?.role === "assistant" ? lastIndex : -1;
  // The choices belong to the turn that asks the question: the hint event can land
  // while that turn is still generating, and showing the options before the question
  // has revealed puts the answer above its own question.
  const showChoices = !hideChoices && hint.kind === "choices" && !disabled;
  const streamingParagraphs = streamedParagraphs(state.streaming);
  const shownStreaming = holding
    ? 0
    : Math.min(revealed ?? streamingParagraphs.length, streamingParagraphs.length);
  const shown = replay ?? state.messages.length;
  const replaying = replay !== null && replay < state.messages.length;
  // ONE indicator for the whole turn: it lights when the tutor takes over and goes
  // dark only when the turn is fully shown (or while the celebration holds the
  // floor). Sending and the post-settle reveal hand over to each other, so the
  // condition is monotonic within a turn — bubbles may grow, nothing revokes.
  const turnDots =
    !holding && !replaying && !awaitingVerdict && (state.sending || revealing);
  // The step's line is for a turn that takes its time: a quick reply gets the dots alone,
  // and each turn starts the wait afresh.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!state.sending) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), WORKING_LINE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [state.sending]);
  const working = slow && state.sending ? state.working : "";
  return (
    <div className="flex flex-col gap-[16px]" aria-live="polite">
      {state.messages.slice(0, shown).map((message, index) => {
        const answeredHere = answered.find((entry) => entry.turn === index);
        // The picked chip already says the answer; the student's echo of it
        // would say it twice.
        if (message.role === "user" && answered.some((entry) => entry.turn === index - 1)) return null;
        return (
          <MessageBubble
            key={index}
            message={message}
            latest={index === latest}
            question={index === latest && Boolean(hint.asks)}
            revealed={index === latest && replay === null ? (holding ? 0 : revealed) : undefined}
            held={holding && index === latest}
            own={typed.find((entry) => entry.turn === index) ?? null}
            choices={
              index === latest && showChoices ? (
                <ChoiceGrid hint={hint} disabled={disabled} onSend={onSend} />
              ) : answeredHere ? (
                <ChoiceGrid
                  hint={answeredHere.hint}
                  disabled
                  onSend={() => {}}
                  result={answeredHere.result}
                />
              ) : null
            }
          />
        );
      })}
      {replaying && (
        <div className="chat-wait-bubble" aria-hidden="true">
          <span className="chat-wait" />
        </div>
      )}
      {state.streaming !== "" && (
        <div
          className="message message--assistant flex flex-col gap-[8px] self-start items-start"
          data-latest-assistant="true"
        >
          {streamingParagraphs.slice(0, shownStreaming).map((paragraph, index) => (
            <Bubble key={index} role="assistant">
              {paragraph}
            </Bubble>
          ))}
        </div>
      )}
      {turnDots && (
        <div className="chat-wait-bubble" aria-label={t("chat.thinking")}>
          <span className="chat-wait" aria-hidden="true" />
          {working !== "" && <span className="chat-working">{working}</span>}
        </div>
      )}
      {!turnDots && working !== "" && (
        <p className="chat-working chat-working-bare">{working}</p>
      )}
      {state.error !== "" && (
        <p className="text-sm" style={{ color: "var(--c-danger)" }}>
          {t(state.error)}
        </p>
      )}
    </div>
  );
}
