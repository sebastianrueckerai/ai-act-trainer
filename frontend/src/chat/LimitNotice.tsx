import { useCallback, useEffect, useState } from "react";
import { useTranslate } from "@tolgee/react";
import { getActiveSession, type BudgetState, type SessionResponse } from "../api/chat";
import { Button, Notice } from "../ui";
import { useCountdown, type Clock } from "./useCountdown";

// The proxy resets up to two minutes late and the backend reads spend through a
// 30-second cache, so zero is when the page starts asking, not when it knows.
const POLL_MS = 5_000;
const RETRY_AFTER_MS = 10_000;

type Scope = NonNullable<BudgetState["scope"]>;

export function BudgetNotice({
  scope,
  clock,
  onRetry,
}: {
  scope: Scope;
  clock: Clock | null;
  onRetry?: () => void;
}) {
  const { t } = useTranslate();
  const timed = scope !== "seats" && scope !== "global";
  return (
    <Notice
      className="chat-notice"
      icon="hourglass"
      title={t(scope === "day" || scope === "month" ? "notice.work.title" : "notice.demand.title")}
    >
      <p>
        {t(timed && clock === null ? "notice.global" : `notice.${scope}`, {
          time: clock?.time ?? "",
          date: clock?.date ?? "",
        })}
      </p>
      {clock && (
        <p className="ui-notice-meta" aria-live="off">
          {t("notice.countdown", { countdown: clock.countdown })}
        </p>
      )}
      {onRetry && (
        <Button variant="primary" onClick={onRetry}>
          {t("notice.retry_now")}
        </Button>
      )}
    </Notice>
  );
}

// At zero the page asks for the session until its budget is ok; a reset that lags
// more than ten seconds gets a button to ask by hand. A refusal without a reset time
// (seats, the turn count) has the button from the start.
export function LimitNotice({
  budget,
  onCheck,
}: {
  budget: BudgetState;
  onCheck: (session: SessionResponse | null) => void;
}) {
  const clock = useCountdown(budget.resets_at);
  const zero = clock !== null && clock.left === 0;
  const [stalled, setStalled] = useState(false);
  const check = useCallback(() => {
    getActiveSession()
      .then(onCheck)
      .catch(() => undefined);
  }, [onCheck]);
  useEffect(() => {
    if (!zero) return;
    check();
    const poll = setInterval(check, POLL_MS);
    const late = setTimeout(() => setStalled(true), RETRY_AFTER_MS);
    return () => {
      clearInterval(poll);
      clearTimeout(late);
      setStalled(false);
    };
  }, [zero, check]);
  return (
    <BudgetNotice
      scope={budget.scope ?? "global"}
      clock={clock}
      onRetry={clock === null || stalled ? check : undefined}
    />
  );
}
