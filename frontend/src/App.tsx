import { TolgeeProvider, useTolgee, useTranslate } from "@tolgee/react";
import { useCallback, useEffect, useState } from "react";
import {
  devLogin,
  getAuthOptions,
  getDevUsers,
  getMe,
  guestLogin,
  inviteLogin,
  logout,
} from "./api/client";
import type { AuthOptions, DevUser, Me } from "./api/client";
import { ChatPage } from "./chat/ChatPage";
import { useEffects } from "./effects/useEffects";
import { GalleryPage } from "./gallery/GalleryPage";
import { tolgee } from "./i18n";
import { useTheme } from "./theme/useTheme";
import { Button, Select } from "./ui";

function LookMenu() {
  const { t } = useTranslate();
  const { look, mode, text, setLook, setMode, setText } = useTheme();
  const language = useTolgee(["language"]).getLanguage();
  const nextLang = language === "en" ? "de" : "en";
  const lookLabel = look === "pixel" ? t("theme.look.clean") : t("theme.look.pixel");
  const modeLabel = mode === "dark" ? t("theme.mode.light") : t("theme.mode.dark");
  const textLabel = text === "pixel" ? t("theme.text.plain") : t("theme.text.pixel");
  const langLabel = nextLang === "en" ? t("lang.en") : t("lang.de");
  return (
    <div className="app-tools" role="group" aria-label={t("theme.look")}>
      <Button
        variant="ghost"
        icon="look"
        aria-label={lookLabel}
        onClick={() => setLook(look === "pixel" ? "clean" : "pixel")}
      >
        <span className="app-tool-label">{lookLabel}</span>
      </Button>
      {look === "pixel" && (
        <Button
          variant="ghost"
          icon="text"
          aria-label={textLabel}
          onClick={() => setText(text === "pixel" ? "plain" : "pixel")}
        >
          <span className="app-tool-label">{textLabel}</span>
        </Button>
      )}
      <Button
        variant="ghost"
        icon="mode"
        aria-label={modeLabel}
        onClick={() => setMode(mode === "dark" ? "light" : "dark")}
      >
        <span className="app-tool-label">{modeLabel}</span>
      </Button>
      <Button
        variant="ghost"
        icon={nextLang === "en" ? "flag-en" : "flag-de"}
        aria-label={langLabel}
        onClick={() => void tolgee.changeLanguage(nextLang)}
      >
        <span className="app-tool-label">{langLabel}</span>
      </Button>
    </div>
  );
}

function SignIn({
  users,
  guest,
  refused,
  onSignedIn,
}: {
  users: DevUser[] | null;
  guest: boolean;
  refused: boolean;
  onSignedIn: () => void;
}) {
  const { t } = useTranslate();
  const [subject, setSubject] = useState(users?.[0]?.subject ?? "");
  return (
    <div className="app-signin">
      {refused && <p className="pick-note">{t("auth.invite_invalid")}</p>}
      {users && (
        <form
          className="app-signin-row"
          onSubmit={async (event) => {
            event.preventDefault();
            await devLogin(subject);
            onSignedIn();
          }}
        >
          <label className="sr-only" htmlFor="dev-user">
            {t("auth.pick_user")}
          </label>
          <Select id="dev-user" value={subject} onChange={(event) => setSubject(event.target.value)}>
            {users.map((user) => (
              <option key={user.subject} value={user.subject}>
                {user.name}
              </option>
            ))}
          </Select>
          <Button variant="primary" type="submit">
            {t("auth.sign_in")}
          </Button>
        </form>
      )}
      {guest && (
        <>
          <Button
            variant="primary"
            onClick={async () => {
              await guestLogin();
              onSignedIn();
            }}
          >
            {t("auth.demo_start")}
          </Button>
          <p className="pick-note">{t("auth.demo_note")}</p>
        </>
      )}
    </div>
  );
}

function Shell() {
  useEffects();
  const { t } = useTranslate();
  const [me, setMe] = useState<Me | null>(null);
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [devUsers, setDevUsers] = useState<DevUser[] | null>(null);
  const [refused, setRefused] = useState(false);

  const refresh = useCallback(async () => {
    const [who, auth, users] = await Promise.all([getMe(), getAuthOptions(), getDevUsers()]);
    setMe(who);
    setOptions(auth);
    setDevUsers(users);
  }, []);

  // An invite link signs in once and leaves the address bar, so the token is not
  // bookmarked or shared from it.
  useEffect(() => {
    void (async () => {
      const token = new URLSearchParams(window.location.search).get("invite");
      if (token !== null) {
        window.history.replaceState(null, "", window.location.pathname);
        await inviteLogin(token).catch(() => setRefused(true));
      }
      await refresh();
    })();
  }, [refresh]);

  const principal = me?.principal;
  const [toolsSlot, setToolsSlot] = useState<HTMLDivElement | null>(null);

  return (
    <main className="app">
      <header className="app-bar">
        <span className="app-title">{t("app.title")}</span>
        <LookMenu />
        <div className="app-tools-slot" ref={setToolsSlot} />
        {principal && (
          <Button
            variant="ghost"
            icon="signout"
            aria-label={t("auth.sign_out")}
            onClick={async () => {
              await logout();
              await refresh();
            }}
          >
            <span className="app-tool-label">{t("auth.sign_out")}</span>
          </Button>
        )}
      </header>
      {principal ? (
        <ChatPage toolsSlot={toolsSlot} />
      ) : (
        options && (
          <SignIn users={devUsers} guest={options.guest} refused={refused} onSignedIn={refresh} />
        )
      )}
    </main>
  );
}

export function App() {
  const gallery =
    typeof window !== "undefined" &&
    window.location.pathname.replace(/\/+$/, "") === "/gallery";

  return (
    <TolgeeProvider tolgee={tolgee} fallback="…">
      {gallery ? <GalleryPage /> : <Shell />}
    </TolgeeProvider>
  );
}
