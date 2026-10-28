import { act, renderHook } from "@testing-library/react";
import { TolgeeProvider } from "@tolgee/react";
import type { ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { tolgee } from "../i18n";
import { formatCountdown, formatReset, useCountdown } from "./useCountdown";

const t = (key: string, params?: Record<string, string>) => tolgee.t(key, params);

function wrapper({ children }: { children: ReactNode }) {
  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {children}
    </TolgeeProvider>
  );
}

beforeAll(async () => {
  await tolgee.run();
});

afterEach(async () => {
  vi.useRealTimers();
  await tolgee.changeLanguage("de");
});

describe("formatCountdown", () => {
  it("counts down in hours, minutes and two-digit seconds", async () => {
    // 2 h 14 min 8 s = 8048 s
    expect(formatCountdown(8_048_000, t)).toBe("2 Std. 14 Min. 08 Sek.");
    // a part second still to go shows as the whole second
    expect(formatCountdown(8_047_001, t)).toBe("2 Std. 14 Min. 08 Sek.");
    await tolgee.changeLanguage("en");
    expect(formatCountdown(8_048_000, t)).toBe("2 h 14 min 08 s");
  });

  it("starts at the first unit that is not zero and keeps the zeros after it", () => {
    expect(formatCountdown(8_000, t)).toBe("8 Sek.");
    expect(formatCountdown(0, t)).toBe("0 Sek.");
    expect(formatCountdown(-5_000, t)).toBe("0 Sek.");
    // 1 day, 0 h, 5 min, 2 s = 86702 s
    expect(formatCountdown(86_702_000, t)).toBe("1 Tg. 00 Std. 05 Min. 02 Sek.");
  });
});

describe("formatReset", () => {
  it("names the time, the zone and the zone id in the active language", async () => {
    // 12:00 UTC is 14:00 in Berlin's summer time
    const at = new Date("2026-10-11T12:00:00Z");
    expect(formatReset(at, "de", t, "Europe/Berlin")).toEqual({
      time: "14:00 Uhr MESZ (Europe/Berlin)",
      date: "11. Oktober",
    });
    await tolgee.changeLanguage("en");
    expect(formatReset(at, "en", t, "Europe/Berlin")).toEqual({
      time: "2:00 PM GMT+2 (Europe/Berlin)",
      date: "October 11",
    });
  });

  it("gives a month reset its date, after the clocks went back to winter time", async () => {
    // midnight UTC on 1 November is 01:00 in Berlin's winter time
    const at = new Date("2026-11-01T00:00:00Z");
    expect(formatReset(at, "de", t, "Europe/Berlin")).toEqual({
      time: "01:00 Uhr MEZ (Europe/Berlin)",
      date: "1. November",
    });
    await tolgee.changeLanguage("en");
    expect(formatReset(at, "en", t, "Europe/Berlin")).toEqual({
      time: "1:00 AM GMT+1 (Europe/Berlin)",
      date: "November 1",
    });
  });
});

describe("useCountdown", () => {
  it("ticks every second towards the reset, in the visitor's zone", () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(new Date("2026-10-11T09:45:52Z"));
    const { result } = renderHook(() => useCountdown("2026-10-11T12:00:00Z"), { wrapper });
    expect(result.current?.countdown).toBe("2 Std. 14 Min. 08 Sek.");
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(result.current?.time).toContain(`(${zone})`);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current?.countdown).toBe("2 Std. 14 Min. 07 Sek.");
    expect(result.current?.left).toBe(8_047_000);
  });

  it("stops at zero", () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(new Date("2026-10-11T11:59:58Z"));
    const { result } = renderHook(() => useCountdown("2026-10-11T12:00:00Z"), { wrapper });
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current?.left).toBe(0);
    expect(result.current?.countdown).toBe("0 Sek.");
  });

  it("has no clock without a reset time", () => {
    const { result } = renderHook(() => useCountdown(null), { wrapper });
    expect(result.current).toBeNull();
  });
});
