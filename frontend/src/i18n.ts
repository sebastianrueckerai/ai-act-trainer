import { FormatSimple, Tolgee } from "@tolgee/react";
import de from "./locales/de.json";
import en from "./locales/en.json";

const LANG_KEY = "lang";
const TAB_TITLES = { de: de["app.title"], en: en["app.title"] } as const;

function storedLanguage(): "de" | "en" {
  try {
    return localStorage.getItem(LANG_KEY) === "en" ? "en" : "de";
  } catch {
    return "de";
  }
}

const initialLanguage = storedLanguage();

if (typeof document !== "undefined") {
  document.documentElement.lang = initialLanguage;
  document.title = TAB_TITLES[initialLanguage];
}

export const tolgee = Tolgee()
  .use(FormatSimple())
  .init({
    language: initialLanguage,
    apiUrl: import.meta.env.VITE_TOLGEE_API_URL,
    apiKey: import.meta.env.VITE_TOLGEE_API_KEY,
    staticData: { de, en },
  });

tolgee.on("language", ({ value }) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = value;
    document.title = TAB_TITLES[value as "de" | "en"];
  }
  try {
    localStorage.setItem(LANG_KEY, value);
  } catch {
    /* private browsing */
  }
});
