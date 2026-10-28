import { act, fireEvent, render, screen } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { getActiveSession, type BudgetState } from "../api/chat";
import { tolgee } from "../i18n";
import { stageFixture } from "../stage/fixture";
import { LimitNotice } from "./LimitNotice";

vi.mock("../api/chat", () => ({ getActiveSession: vi.fn() }));

const EXHAUSTED: BudgetState = {
  state: "exhausted",
  scope: "pool_day",
  resets_at: "2026-10-11T12:00:00Z",
};

const SESSION = {
  id: 7,
  persona_id: "marvin",
  phase: "lesson",
  display_locale: "de",
  hint: { kind: "text" as const, choices: [], asks: false },
  messages: [],
  stage: stageFixture,
  budget: EXHAUSTED,
};

function withProvider(ui: ReactElement) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {ui}
    </TolgeeProvider>
  );
}

const retry = () => screen.queryByRole("button", { name: "Jetzt weiter" });

beforeAll(async () => {
  await tolgee.run();
});

beforeEach(() => {
  vi.mocked(getActiveSession).mockReset().mockResolvedValue(SESSION);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LimitNotice", () => {
  it("asks for the session from zero every five seconds, and offers the button after ten", async () => {
    vi.useFakeTimers({
      toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "Date"],
    });
    vi.setSystemTime(new Date("2026-10-11T11:59:59Z"));
    const onCheck = vi.fn();
    render(withProvider(<LimitNotice budget={EXHAUSTED} onCheck={onCheck} />));
    expect(screen.getByRole("status")).toHaveTextContent("Weiter in 1 Sek.");
    expect(getActiveSession).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("status")).toHaveTextContent("Weiter in 0 Sek.");
    expect(getActiveSession).toHaveBeenCalledTimes(1);
    expect(onCheck).toHaveBeenCalledWith(SESSION);
    expect(retry()).toBeNull();

    await act(async () => vi.advanceTimersByTime(5000));
    expect(getActiveSession).toHaveBeenCalledTimes(2);
    expect(retry()).toBeNull();

    await act(async () => vi.advanceTimersByTime(5000));
    expect(getActiveSession).toHaveBeenCalledTimes(3);
    expect(retry()).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(retry()!);
    });
    expect(getActiveSession).toHaveBeenCalledTimes(4);
  });

  it("offers the button at once when the refusal has no reset time, and asks only on it", async () => {
    const onCheck = vi.fn();
    render(
      withProvider(
        <LimitNotice
          budget={{ state: "exhausted", scope: "seats", resets_at: null }}
          onCheck={onCheck}
        />,
      ),
    );
    expect(screen.getByRole("heading", { name: "Großer Andrang" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Alle Demo-Plätze sind gerade belegt. In ein paar Minuten wird wieder einer frei.",
    );
    expect(screen.getByRole("status")).not.toHaveTextContent("Weiter in");
    expect(getActiveSession).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(retry()!);
    });
    expect(getActiveSession).toHaveBeenCalledTimes(1);
    expect(onCheck).toHaveBeenCalledWith(SESSION);
  });

  it("titles an account's own budget as work done, and follows the language", async () => {
    const budget: BudgetState = {
      state: "exhausted",
      scope: "month",
      resets_at: new Date(Date.now() + 20 * 86_400_000).toISOString(),
    };
    render(withProvider(<LimitNotice budget={budget} onCheck={() => {}} />));
    expect(screen.getByRole("heading", { name: "Viel geschafft" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      /Dein Guthaben für diesen Monat ist aufgebraucht\. Am \d+\. \S+ um .+ Uhr .+ \(.+\) geht es weiter\./,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/Weiter in \d+ Tg\. \d+ Std\. \d+ Min\. \d+ Sek\./);

    try {
      await act(async () => {
        await tolgee.changeLanguage("en");
      });
      expect(screen.getByRole("heading", { name: "Good work" })).toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(
        /Your budget for this month is used up\. It refills on \S+ \d+ at .+ \(.+\)\./,
      );
      expect(screen.getByRole("status")).toHaveTextContent(/Resets in \d+ d \d+ h \d+ min \d+ s/);
    } finally {
      await tolgee.changeLanguage("de");
    }
  });
});
