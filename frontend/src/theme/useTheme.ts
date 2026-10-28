import { useCallback, useEffect, useState } from "react";
import { getTheme } from "../api/theme";
import {
  DEFAULT_COLORS,
  derivePalette,
  type Look,
  type Mode,
  type Palette,
  type ThemeColors,
} from "./palette";

export type { Look, Mode } from "./palette";

// The pixel look's own prose face, or the plain reading font it can borrow
// from the clean look (D91). Clean already reads in the plain font, so this
// setting only ever matters, and only ever shows, under the pixel look.
export type Text = "pixel" | "plain";

const LOOK_KEY = "look";
const MODE_KEY = "mode";
const TEXT_KEY = "text";
const LOOKS: Look[] = ["pixel", "clean"];
const MODES: Mode[] = ["dark", "light"];
const TEXTS: Text[] = ["pixel", "plain"];

function readStored<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function applyPalette(palette: Palette): void {
  const root = document.documentElement;
  for (const [name, value] of Object.entries(palette)) {
    root.style.setProperty(name, value);
  }
}

export function useTheme() {
  const [look, setLookState] = useState<Look>(() => readStored(LOOK_KEY, LOOKS, "pixel"));
  const [colors, setColors] = useState<ThemeColors>(DEFAULT_COLORS);
  // Dark is the product's default. The student who wants light says so (D42).
  const [mode, setModeState] = useState<Mode>(() => readStored(MODE_KEY, MODES, "dark"));
  // The pixel look's own face is the default; the student who finds Tiny5 hard
  // to read says so (D91).
  const [text, setTextState] = useState<Text>(() => readStored(TEXT_KEY, TEXTS, "pixel"));

  useEffect(() => {
    let storedChoice: string | null = null;
    try {
      storedChoice = window.localStorage.getItem(LOOK_KEY);
    } catch {
      storedChoice = null;
    }
    let cancelled = false;
    getTheme()
      .then((theme) => {
        if (cancelled) return;
        setColors({
          primary: theme.primary,
          secondary: theme.secondary,
          accent: theme.accent,
          background: theme.background,
        });
        if (storedChoice === null && LOOKS.includes(theme.look as Look)) {
          setLookState(theme.look as Look);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.look = look;
    root.dataset.mode = mode;
    root.dataset.text = text;
    applyPalette(derivePalette(colors, mode, look));
  }, [look, mode, text, colors]);

  const setLook = useCallback((next: Look) => {
    setLookState(next);
    try {
      window.localStorage.setItem(LOOK_KEY, next);
    } catch {
      /* private browsing */
    }
  }, []);

  const setMode = useCallback((next: Mode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      /* private browsing */
    }
  }, []);

  const setText = useCallback((next: Text) => {
    setTextState(next);
    try {
      window.localStorage.setItem(TEXT_KEY, next);
    } catch {
      /* private browsing */
    }
  }, []);

  return { look, mode, text, colors, setLook, setMode, setText };
}
