import { useEffect, useRef, useState } from "react";
import { useTranslate } from "@tolgee/react";
import type { InputHint } from "../api/chat";
import type { Verdict } from "./MessageList";
import { Button, Chip, TextArea } from "../ui";

// The choices hint's own chip grid: rendered by MessageList as the last block
// of the latest assistant message, not by the composer (D73 amended in wave 7 -
// a four-option grid in the foot halved the reading pane). InputControl still
// owns the letter and submit logic; MessageList only places the grid.
export function ChoiceGrid({
  hint,
  disabled,
  onSend,
  result = null,
}: {
  hint: InputHint;
  disabled: boolean;
  onSend: (text: string, shown?: string) => void;
  // The picked choice keeps the plain chip look; its verdict rings the frame
  // green when the try met a required point, orange when it met none but is on
  // the right track, red when it met none; it pulses and then stays (D104).
  // Settling recedes the other options.
  result?: { key: string; verdict: Verdict | null; settled: boolean } | null;
}) {
  return (
    <div className={result?.settled ? "message-choices message-choices--settled" : "message-choices"}>
      {(hint.choices ?? []).map((choice, index) => {
        const letter = /^[a-zA-Z]$/.test(choice.key)
          ? choice.key.toUpperCase()
          : String.fromCharCode(65 + index);
        const shown = `${letter}. ${choice.label}`;
        const picked = result !== null && result.key === choice.key;
        const verdict =
          picked && result.verdict !== null
            ? `chip-${result.settled ? "verdict" : "flash"}--${result.verdict}`
            : undefined;
        return (
          <Chip
            key={choice.key}
            disabled={disabled}
            aria-pressed={picked}
            className={verdict}
            onClick={() => onSend(choice.key, shown)}
          >
            <span className="chip-key">{letter}.</span> <span className="chip-text">{choice.label}</span>
          </Chip>
        );
      })}
    </div>
  );
}

export function InputControl({
  hint,
  disabled,
  hideChoices = false,
  onSend,
  onAdvance,
}: {
  hint: InputHint;
  disabled: boolean;
  // Set while a modal confirmation (e.g. restart) is open: only that dialog's
  // own buttons stay clickable.
  hideChoices?: boolean;
  // `shown` is what the student sees in their own bubble; `text` is what the tutor
  // receives. They differ for a choice chip, whose key is an internal identifier.
  onSend: (text: string, shown?: string) => void;
  // Moving on is an action, not a message (D90): the confirm button calls this
  // directly instead of sending a "weiter" the student never typed.
  onAdvance: () => void;
}) {
  const { t } = useTranslate();
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grows the composer from one line up to three as the student types; the
  // CSS max-height clamp does the rest. scrollHeight excludes the border even
  // under border-box, so the pixel skin's 12px nine-slice border has to be
  // added back in or the last line clips.
  useEffect(() => {
    const el = textareaRef.current;
    if (el === null) return;
    const style = getComputedStyle(el);
    const borderY = (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.borderBottomWidth) || 0);
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + borderY}px`;
  }, [text]);

  const submit = (value: string, shown?: string) => {
    if (disabled || value.trim() === "") return;
    onSend(value.trim(), shown);
    setText("");
  };

  return (
    <div className="composer">
      <div className="composer-row">
        {!hideChoices && hint.kind === "yes_no" && (
          <>
            <Button variant="primary" disabled={disabled} onClick={() => submit("yes", t("chat.yes"))}>
              {t("chat.yes")}
            </Button>
            <Button variant="primary" disabled={disabled} onClick={() => submit("no", t("chat.no"))}>
              {t("chat.no")}
            </Button>
          </>
        )}
        {!hideChoices && hint.kind === "confirm" && (
          <Button variant="primary" disabled={disabled} onClick={() => onAdvance()}>
            {hint.label ?? t("chat.confirm")}
          </Button>
        )}
        <TextArea
          ref={textareaRef}
          className="composer-text"
          aria-label={t("chat.placeholder")}
          rows={1}
          value={text}
          placeholder={t(hint.kind === "confirm" ? "chat.placeholder_ask" : "chat.placeholder")}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit(text);
            }
          }}
        />
        <Button
          variant="secondary"
          icon="send"
          className="composer-send"
          disabled={disabled}
          onClick={() => submit(text)}
        >
          {t("chat.send")}
        </Button>
      </div>
    </div>
  );
}
