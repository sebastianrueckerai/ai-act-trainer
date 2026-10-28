import { useEffect, useState } from "react";
import { useTolgee, useTranslate } from "@tolgee/react";

type Translate = (key: string, params?: Record<string, string>) => string;

export type Clock = { left: number; countdown: string; time: string; date: string };

const UNITS = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
] as const;

// "2 Std. 14 Min. 08 Sek.": from the first unit that is not zero, every later one two digits.
export function formatCountdown(ms: number, t: Translate): string {
  let rest = Math.ceil(Math.max(0, ms) / 1000);
  const parts: string[] = [];
  for (const [unit, size] of UNITS) {
    const n = Math.floor(rest / size);
    rest -= n * size;
    if (parts.length === 0 && n === 0 && unit !== "second") continue;
    const shown = parts.length === 0 ? String(n) : String(n).padStart(2, "0");
    parts.push(t(`notice.unit.${unit}`, { n: shown }));
  }
  return parts.join(" ");
}

// "14:00 Uhr MESZ (Europe/Berlin)" and "11. Oktober", in the visitor's own zone.
export function formatReset(
  at: Date,
  language: string,
  t: Translate,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): { time: string; date: string } {
  const clock = new Intl.DateTimeFormat(language, { timeStyle: "short", timeZone }).format(at);
  const zone =
    new Intl.DateTimeFormat(language, { hour: "numeric", timeZoneName: "short", timeZone })
      .formatToParts(at)
      .find((part) => part.type === "timeZoneName")?.value ?? "";
  return {
    time: t("notice.time", { clock, zone, id: timeZone }),
    date: new Intl.DateTimeFormat(language, { day: "numeric", month: "long", timeZone }).format(at),
  };
}

export function useCountdown(resetsAt: string | null | undefined): Clock | null {
  const { t } = useTranslate();
  const language = useTolgee(["language"]).getLanguage() ?? "de";
  const target = resetsAt ? Date.parse(resetsAt) : null;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (target === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [target]);
  if (target === null) return null;
  const left = Math.max(0, target - now);
  return { left, countdown: formatCountdown(left, t), ...formatReset(new Date(target), language, t) };
}
