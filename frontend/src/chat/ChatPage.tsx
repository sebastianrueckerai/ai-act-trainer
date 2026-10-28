import { useCallback, useEffect, useReducer, useRef, useState, type UIEvent } from "react";
import { createPortal } from "react-dom";
import { useTolgee, useTranslate } from "@tolgee/react";
import {
  closeSession,
  getActiveSession,
  postSession,
  setDisplayLocale,
  streamContinue,
  streamOpening,
  streamTurn,
  type ChatEvent,
  type SessionResponse,
  type Stage,
} from "../api/chat";
import { burst, burstMs, reducedMotion } from "../effects/confetti";
import { tolgee } from "../i18n";
import { PersonaPicker } from "../persona/PersonaPicker";
import { CourseStatus } from "./CourseStatus";
import { EMPTY, reducer } from "./state";
import { InputControl } from "./InputControl";
import { LimitNotice } from "./LimitNotice";
import {
  LATEST_ASSISTANT_SELECTOR,
  MessageList,
  paragraphsOf,
  streamedParagraphs,
  type AnsweredTurn,
  type TypedVerdict,
  type Verdict,
} from "./MessageList";
import { useReveal } from "./useReveal";
import { Avatar, Button, Frame } from "../ui";
import { emitUi, onUi } from "./uiBus";

// A resumed replay pauses a beat before each tutor box: brief, but long enough to
// read as the tutor typing. The thread's very first box waits half as long again.
const REPLAY_BEAT_MS = 1350;
const REPLAY_FIRST_BEAT_MS = REPLAY_BEAT_MS + Math.round(REPLAY_BEAT_MS / 2);
// The chip flash pulses 0.9s twice; a retired grid also waits this tail past its
// moment, so the celebration is cleanly over before anything moves on.
const FLASH_MS = 1800;
const TAIL_MS = 250;
// A finished chapter's portrait hops three times, 0.4s each (pixel.css).
const HOP_MS = 1200;
// Past roughly half a reading pane above the end, the view counts as parked and
// the jump arrow stands.
const JUMP_AT = 480;
// A translation of an older turn takes about a second to land.
const TRANSLATE_POLL_MS = 1500;

export function ChatPage({ toolsSlot = null }: { toolsSlot?: HTMLDivElement | null }) {
  const { t } = useTranslate();
  const [state, dispatch] = useReducer(reducer, undefined, () => EMPTY);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [picking, setPicking] = useState(false);
  const [resumed, setResumed] = useState(false);
  const [confirmingRestart, setConfirmingRestart] = useState(false);
  // The stage whose reaction portrait has had its moment: the face stays neutral
  // until the next stage moves it again.
  const [spent, setSpent] = useState<Stage | null>(null);
  // The choices questions the student answered stay in the thread, each inside
  // the turn that asked it (D104): after the flash the picked chip keeps its
  // verdict steady and the unpicked options recede.
  const [answered, setAnswered] = useState<AnsweredTurn[]>([]);
  // A typed answer's verdict pulses the student's own bubble green when the try met
  // a required point, red when it met none, and keeps the tint, as a picked chip does (D104).
  const [typed, setTyped] = useState<TypedVerdict[]>([]);
  const typedTurn = useRef(-1);
  const settleTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // The moment settles: the pulse gives way to the steady tint. Only the newest
  // answer can be unsettled — sending gates the next one until this one is done.
  const settleAnswered = useCallback((delay: number) => {
    clearTimeout(settleTimer.current);
    settleTimer.current = setTimeout(() => {
      setAnswered((list) =>
        list.map((entry, index) =>
          index === list.length - 1 && entry.result
            ? { ...entry, result: { ...entry.result, settled: true } }
            : entry,
        ),
      );
      setTyped((list) => list.map((entry) => ({ ...entry, settled: true })));
    }, delay);
  }, []);
  const recordVerdict = useCallback((key: string, verdict: Verdict) => {
    setAnswered((list) =>
      list.map((entry, index) =>
        index === list.length - 1
          ? { ...entry, result: { key, verdict, settled: false } }
          : entry,
      ),
    );
  }, []);
  const pickedKey = useRef<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const wasStreaming = useRef(false);
  // The confetti is a moment of its own: while a burst plays, the reply waits and
  // the typing dots stand in for the tutor.
  const [holding, setHolding] = useState(false);
  // While an answer's grade is pending, the tutor has nothing to type yet: the
  // indicator stays dark, because dots that appear now would be revoked by the
  // verdict's celebration a moment later. The chip flash stands in instead.
  const [awaitingVerdict, setAwaitingVerdict] = useState(false);
  const holdUntil = useRef(0);
  const holdTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // `replace` cuts a running hold short to `ms`, where a later celebration replaces one.
  const hold = useCallback((ms: number, replace = false) => {
    const now = performance.now();
    const end = replace ? now + ms : Math.max(holdUntil.current, now + ms);
    holdUntil.current = end;
    clearTimeout(holdTimer.current);
    setHolding(end > now);
    if (end > now) holdTimer.current = setTimeout(() => setHolding(false), end - now);
  }, []);
  // A resumed thread replays one box at a time, each tutor box after its own
  // typing beat; a click anywhere finishes the replay.
  const [replay, setReplay] = useState<number | null>(null);
  const replayTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const finishReplay = useCallback(() => {
    clearTimeout(replayTimer.current);
    setReplay(null);
  }, []);
  const startReplay = useCallback((messages: SessionResponse["messages"]) => {
    const total = messages.length;
    if (total === 0) return;
    let shown = 0;
    setReplay(0);
    const step = () => {
      shown += 1;
      setReplay(shown);
      if (shown >= total) {
        setReplay(null);
        return;
      }
      const next = messages[shown];
      replayTimer.current = setTimeout(step, next.role === "assistant" ? REPLAY_BEAT_MS : 0);
    };
    replayTimer.current = setTimeout(step, REPLAY_FIRST_BEAT_MS);
  }, []);
  const [hopping, setHopping] = useState(false);
  const hopTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const burstTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(
    () => () => {
      clearTimeout(holdTimer.current);
      clearTimeout(replayTimer.current);
      clearTimeout(settleTimer.current);
      clearTimeout(hopTimer.current);
      clearTimeout(burstTimer.current);
    },
    [],
  );

  // A turn that ends without a verdict (an error, or a message that routed to
  // the coach) closes the pending-grade window with it.
  useEffect(() => {
    if (!state.sending) setAwaitingVerdict(false);
  }, [state.sending]);

  // The thread follows new text only while the student is at its end. A manual
  // scroll up parks the view wherever the student put it until they return to
  // the end; their own send resumes the following. Far enough up, the jump
  // arrow stands and takes them back to the newest line in one click.
  const atBottom = useRef(true);
  const settleAt = useRef(0);
  const [away, setAway] = useState(0);
  const follow = (el: Element | null, block: ScrollLogicalPosition) => {
    if (el === null) return;
    settleAt.current = performance.now() + 150;
    el.scrollIntoView({ block });
  };
  const onThreadScroll = (event: UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget;
    setAway(el.scrollHeight - el.scrollTop - el.clientHeight);
    if (performance.now() < settleAt.current) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight <= 80;
  };

  const fail = useCallback(
    () =>
      dispatch({
        type: "event",
        event: { event: "error", code: "network", message: "chat.error" },
      }),
    [],
  );

  const consume = useCallback((event: ChatEvent) => {
    // The student reads one line for every failure, or the notice for a refusal;
    // the provider's own text goes to the console, never onto the page.
    if (event.event === "error") {
      console.warn("chat error", event.code, event.message);
      dispatch({
        type: "event",
        event: event.code === "limit" ? event : { ...event, message: "chat.error" },
      });
      return;
    }
    dispatch({ type: "event", event });
    if (event.event === "ui") emitUi({ name: event.name, payload: event.payload ?? {} });
  }, []);

  const open = useCallback(
    (session: SessionResponse) => {
      setSessionId(session.id);
      dispatch({ type: "hydrate", session });
      // A resumed session's own locale wins over whatever the toggle showed
      // before the page knew a session existed.
      synced.current = { id: session.id, language: session.display_locale };
      if (session.display_locale !== tolgee.getLanguage()) {
        void tolgee.changeLanguage(session.display_locale as "de" | "en");
      }
      // A seeded thread with nothing in it has never had its opening: a reload
      // between the persona click and the first step lands here.
      if (session.messages.length > 0) {
        startReplay(session.messages);
        return Promise.resolve();
      }
      // The opening is a model call too: it waits for the budget to come back.
      if (session.budget.state === "exhausted") return Promise.resolve();
      dispatch({ type: "sending" });
      return streamOpening(session.id, consume);
    },
    [consume, startReplay],
  );

  useEffect(() => {
    let cancelled = false;
    getActiveSession()
      .then((session) => {
        if (cancelled) return undefined;
        return session === null ? undefined : open(session);
      })
      .catch(fail)
      .finally(() => !cancelled && setResumed(true));
    return () => {
      cancelled = true;
    };
  }, [fail, open]);

  // The flag in the app bar is global; an open session follows it, in either
  // direction, the moment the student flips it.
  // Only a flip writes: a session opens with its own locale already in place, and a
  // write during the opening turn would race the stream.
  const language = useTolgee(["language"]).getLanguage();
  const synced = useRef<{ id: number; language: string } | null>(null);
  // The flip and every poll after it land the same way: texts, parts and hints in
  // place, and the answered grids take the labels of the turn that asked them.
  const messagesRef = useRef(state.messages);
  messagesRef.current = state.messages;
  const applyFlip = useCallback((session: SessionResponse) => {
    dispatch({ type: "retext", session });
    const fresh = new Map(session.messages.map((message) => [message.id, message]));
    setAnswered((list) =>
      list.map((entry) => {
        const id = messagesRef.current[entry.turn]?.id;
        const hint = id ? fresh.get(id)?.hint : undefined;
        return hint ? { ...entry, hint } : entry;
      }),
    );
  }, []);
  useEffect(() => {
    if (sessionId === null || language === undefined) return;
    if (synced.current?.id === sessionId && synced.current.language === language) return;
    synced.current = { id: sessionId, language };
    setDisplayLocale(sessionId, language as "de" | "en").then(applyFlip).catch(fail);
  }, [sessionId, language, applyFlip, fail]);

  // The older turns translate behind the flip, one landing after another: while
  // any still shows its German, the thread asks again until all have followed.
  const translating = state.messages.some((message) => message.translating);
  useEffect(() => {
    if (!translating) return;
    const timer = setInterval(() => {
      getActiveSession()
        .then((session) => {
          if (session !== null) applyFlip(session);
        })
        .catch(fail);
    }, TRANSLATE_POLL_MS);
    return () => clearInterval(timer);
  }, [translating, applyFlip, fail]);

  // The turn in progress arrives one bubble at a time, from its first streamed word to
  // the settled message (D97). The turn identity tells the reveal when one turn ends
  // and the next begins; within a turn the revealed count carries across the stream
  // settling into a message, so nothing flashes whole and nothing restarts. The
  // identity must move on a continue too: a "Weiter" adds no student message, yet its
  // reply owes the same beats — so the streaming flag is part of the identity, and the
  // settle (one more message, streaming over) lands on the very identity the stream
  // used, keeping what it showed.
  const newest = state.messages.at(-1);
  const turnParagraphs =
    state.streaming !== ""
      ? streamedParagraphs(state.streaming)
      : newest?.role === "assistant"
        ? paragraphsOf(newest.text, newest.parts.some((part) => part.kind === "citations"))
        : [];
  const turn = state.messages.length + (state.streaming !== "" ? 1 : 0);
  const replaying = replay !== null;
  const { revealed, revealing, revealAll } = useReveal(turn, turnParagraphs, holding || replaying);
  // The replay types the thread back; when it hands over, the tutor's last word
  // stands whole instead of folding back behind the pacing.
  const wasReplaying = useRef(false);
  useEffect(() => {
    if (replay !== null) {
      wasReplaying.current = true;
    } else if (wasReplaying.current) {
      wasReplaying.current = false;
      revealAll();
    }
  }, [replay, revealAll]);
  const stillRevealing = revealing || state.streaming !== "";
  const locked = state.budget.state === "exhausted";
  const gated =
    state.sending || stillRevealing || confirmingRestart || holding || replay !== null || locked;
  const choicesLive = !gated && state.hint.kind === "choices";
  // Content growing while the view is parked changes the distance without a
  // scroll event firing.
  useEffect(() => {
    const scroller = threadRef.current?.parentElement;
    if (scroller) setAway(scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight);
  }, [state.messages, state.streaming, state.sending, revealed, replay]);

  // The student's own turn keeps the classic scroll-to-bottom; sending is itself
  // the wish to follow again.
  useEffect(() => {
    if (state.messages.at(-1)?.role === "user") {
      atBottom.current = true;
      follow(bottom.current, "end");
    }
  }, [state.messages]);

  // The waiting dots are the thread's new end while the tutor thinks; when they
  // appear, the view follows them — a continue turn has no student bubble whose
  // send would have done it.
  useEffect(() => {
    if (!state.sending || state.streaming !== "" || holding || replaying) return;
    if (!atBottom.current) return;
    follow(bottom.current, "end");
  }, [state.sending, state.streaming, holding, replaying]);

  // The whole reply is what the student reads next, card and bubble alike (a
  // graded turn folds a card before the bubble). A turn that fits the scroll
  // box stands whole; a taller one aligns its own top and then brings its
  // options into view too, since the options are what the student acts on
  // next. A reply still streaming in keeps its top.
  useEffect(() => {
    const streaming = state.streaming !== "";
    const justStartedStreaming = streaming && !wasStreaming.current;
    wasStreaming.current = streaming;
    if (!atBottom.current) return;
    // The notice takes room from the pane below the thread's end; the end stays in view.
    if (state.error !== "" || locked) {
      follow(bottom.current, "end");
      return;
    }
    const arrived = state.messages.at(-1)?.role === "assistant";
    if (!justStartedStreaming && !arrived) return;
    const el = threadRef.current?.querySelector(LATEST_ASSISTANT_SELECTOR);
    const scroller = threadRef.current?.parentElement;
    if (!el || !scroller) return;
    const height = el.getBoundingClientRect().height;
    if (justStartedStreaming || height > scroller.clientHeight - 24) {
      follow(el, "start");
      // A turn that ends on options ends on what the student acts on: the thread's own
      // end brings the last option up with the clearance the scroll box's mask needs,
      // which aligning the options themselves does not.
      if (el.querySelector(".message-choices")) {
        follow(bottom.current, "end");
      }
    } else {
      follow(bottom.current, "end");
    }
  }, [state.error, locked, state.messages, state.streaming, replay]);

  // The verdict arrives as the turn's answer_result event, in the chapter and in
  // the test alike: a picked chip or the student's own typed bubble flashes green
  // when the try met a required point, orange when it met none but is on the
  // right track, and red when it met none. A green that
  // settles the question throws confetti right after the flash starts, and the
  // reply waits for the celebration: a burst, verdict or finale, holds every new
  // line — and every typing dot — until it has played out. A green that leaves
  // the question open only flashes; the tutor's next question follows at once.
  useEffect(
    () =>
      onUi((detail) => {
        if (detail.name === "answer_result") {
          setAwaitingVerdict(false);
          const verdict = detail.payload.verdict;
          const green = verdict === "correct";
          const settled = detail.payload.settled === true;
          const tone: Verdict = green ? "ok" : verdict === "partial" ? "partial" : "miss";
          if (pickedKey.current !== null) {
            const key = pickedKey.current;
            pickedKey.current = null;
            recordVerdict(key, tone);
          } else {
            const turn = typedTurn.current;
            setTyped((list) => [...list, { turn, verdict: tone, settled: false }]);
          }
          if (green && settled) {
            burstTimer.current = setTimeout(() => burst(60), 250);
            hold(250 + burstMs());
            // The grid stays through the celebration, then settles with it.
            settleAnswered(250 + burstMs() + TAIL_MS);
          } else {
            settleAnswered(FLASH_MS + TAIL_MS);
          }
        } else if (detail.name === "confetti" || detail.name === "finale") {
          hold(burstMs());
        } else if (detail.name === "chapter_complete") {
          // One click, one celebration: the chapter end hops instead of the answer's
          // confetti, and the turn waits for the hop alone.
          clearTimeout(burstTimer.current);
          clearTimeout(hopTimer.current);
          setHopping(true);
          hopTimer.current = setTimeout(() => setHopping(false), HOP_MS);
          hold(reducedMotion() ? 0 : HOP_MS, true);
        }
      }),
    [hold, settleAnswered, recordVerdict],
  );

  // The reaction portrait answers the verdict, not the next question: the face returns
  // to neutral once the turn's question is on screen, and six seconds after the stage
  // at most. Every stage restarts it, so a second miss in a row frowns again.
  const reaction = state.stage;
  useEffect(() => {
    if ((reaction?.mood ?? "neutral") === "neutral") return;
    const timer = setTimeout(() => setSpent(reaction), 6_000);
    return () => clearTimeout(timer);
  }, [reaction]);
  const questionUp =
    !state.sending && !stillRevealing && !holding && replay === null && Boolean(state.hint.asks);
  useEffect(() => {
    if (questionUp) setSpent(reaction);
  }, [questionUp, reaction]);
  const decayed = questionUp || spent === reaction;
  const mood = decayed ? "neutral" : (reaction?.mood ?? "neutral");
  const portraitSrc = decayed
    ? (reaction?.persona?.neutral_image_url ?? reaction?.persona?.image_url ?? null)
    : (reaction?.persona?.image_url ?? null);

  // The persona's own room stands behind the chat; without one the office does,
  // which is also what stands behind the picker (D67).
  const sceneUrl = state.stage?.persona?.scene_url ?? null;
  const sceneLightUrl = state.stage?.persona?.scene_light_url ?? null;
  useEffect(() => {
    const root = document.documentElement;
    if (sceneUrl === null) {
      root.style.removeProperty("--scene-image");
      root.style.removeProperty("--scene-image-light");
      return;
    }
    root.style.setProperty("--scene-image", `url("${sceneUrl}")`);
    if (sceneLightUrl !== null) {
      root.style.setProperty("--scene-image-light", `url("${sceneLightUrl}")`);
    }
    return () => {
      root.style.removeProperty("--scene-image");
      root.style.removeProperty("--scene-image-light");
    };
  }, [sceneUrl, sceneLightUrl]);

  // Once the growing reply passes the fold, follow its bottom (and the
  // cursor with it); a settled turn pacing in behind the dots does the same,
  // one paragraph at a time. The follow targets the thread's end sentinel,
  // whose own height keeps the newest line clear of the scroll box's fade
  // mask: fully shown, never half cut off. Stops the moment the student
  // scrolls away from the end.
  useEffect(() => {
    if (!atBottom.current) return;
    const el = threadRef.current?.querySelector<HTMLElement>(LATEST_ASSISTANT_SELECTOR);
    const scroller = threadRef.current?.parentElement;
    if (!el || !scroller) return;
    if (el.getBoundingClientRect().bottom > scroller.getBoundingClientRect().bottom) {
      follow(bottom.current, "end");
    }
  }, [state.streaming, revealed]);

  // When the question's reveal ends, the options un-hide; they are what the
  // student acts on next, so they bring themselves into view.
  useEffect(() => {
    if (!choicesLive || !atBottom.current) return;
    follow(bottom.current, "end");
  }, [choicesLive]);

  const start = (personaId: string) => {
    setPicking(true);
    postSession(personaId, (tolgee.getLanguage() ?? "de") as "de" | "en")
      .then(open)
      .catch(fail)
      .finally(() => setPicking(false));
  };

  const send = (text: string, shown?: string) => {
    if (sessionId === null || state.sending) return;
    typedTurn.current = state.messages.length;
    // An answer to a live question grades before the tutor speaks: the indicator
    // stays dark until the verdict, so nothing shown gets taken back.
    setAwaitingVerdict(state.hint.kind === "choices" || state.hint.kind === "yes_no");
    if (/^[a-f]$/i.test(text) && state.hint.kind === "choices") {
      pickedKey.current = text;
      // The answer joins the thread inside the turn that asked the question
      // (D104). A practice hint names its own answer: the picked chip flashes
      // on the click, and the arriving verdict confirms or corrects it.
      const optimistic = state.hint.correct_key === text;
      setAnswered((list) => [
        ...list,
        {
          turn: state.messages.length - 1,
          hint: state.hint,
          result: { key: text, verdict: optimistic ? "ok" : null, settled: false },
        },
      ]);
      if (optimistic) settleAnswered(FLASH_MS + TAIL_MS);
    }
    dispatch({ type: "user_message", text: shown ?? text });
    dispatch({ type: "sending" });
    streamTurn(sessionId, text, consume, undefined, shown).catch(fail);
  };

  // Moving on is an action, not something the student says (D90): it carries
  // no message of its own.
  const advance = () => {
    if (sessionId === null || state.sending) return;
    dispatch({ type: "sending" });
    streamContinue(sessionId, consume).catch(fail);
  };

  const forget = useCallback(() => {
    dispatch({ type: "reset" });
    setSessionId(null);
    clearTimeout(settleTimer.current);
    setAnswered([]);
    setTyped([]);
  }, []);

  const restart = useCallback(() => {
    closeSession().then(forget).catch(fail);
  }, [forget, fail]);

  // What the session says once the notice's clock has run out. A guest whose rows were
  // cleaned while waiting has no session left and starts over at the picker.
  const recheck = useCallback(
    (session: SessionResponse | null) => {
      if (session === null) {
        forget();
        return;
      }
      dispatch({ type: "budget", budget: session.budget });
      if (session.budget.state === "ok" && session.messages.length === 0) {
        dispatch({ type: "sending" });
        streamOpening(session.id, consume).catch(fail);
      }
    },
    [forget, consume, fail],
  );

  if (!resumed) return null;
  if (sessionId === null)
    return <PersonaPicker onPick={start} busy={picking} error={state.error} />;

  const stage = state.stage;
  const portrait = stage?.persona ? (
    <div className="chat-portrait" data-hop={hopping || undefined}>
      <Frame>
        <Avatar
          name={stage.persona.name}
          imageUrl={portraitSrc}
          mood={mood}
          size={256}
        />
      </Frame>
    </div>
  ) : null;

  return (
    <div className="chat">
      {toolsSlot &&
        stage &&
        createPortal(
          <Button
            variant="ghost"
            icon="restart"
            aria-label={t("stage.restart")}
            onClick={() => setConfirmingRestart(true)}
          >
            <span className="app-tool-label">{t("stage.restart")}</span>
          </Button>,
          toolsSlot,
        )}
      <div className="chat-pane">
        <div
          className="chat-scroll"
          onClick={() => {
            finishReplay();
            revealAll();
          }}
          onScroll={onThreadScroll}
        >
          <div ref={threadRef} className="chat-thread">
            <MessageList
              state={state}
              hint={state.hint}
              disabled={gated}
              hideChoices={confirmingRestart}
              onSend={send}
              revealed={revealed}
              revealing={stillRevealing}
              answered={answered}
              typed={typed}
              awaitingVerdict={awaitingVerdict}
              replay={replay}
              holding={holding}
            />
            <div ref={bottom} className="chat-thread-end" />
          </div>
        </div>
        {away > JUMP_AT && (
          <Button
            variant="secondary"
            icon="down"
            className="chat-jump"
            aria-label={t("chat.jump")}
            title={t("chat.jump")}
            onClick={() => {
              atBottom.current = true;
              follow(bottom.current, "end");
            }}
          />
        )}
      </div>
      <div className="chat-foot">
        <div className="chat-thread chat-foot-row">
          {portrait}
          <div className="chat-foot-main">
            <CourseStatus
              stage={state.stage}
              confirming={confirmingRestart}
              onConfirm={() => {
                setConfirmingRestart(false);
                restart();
              }}
              onCancel={() => setConfirmingRestart(false)}
            />
            {locked && <LimitNotice budget={state.budget} onCheck={recheck} />}
            <InputControl
              hint={state.hint}
              disabled={gated}
              hideChoices={confirmingRestart}
              onSend={send}
              onAdvance={advance}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
