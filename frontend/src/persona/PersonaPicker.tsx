import { useTolgee, useTranslate } from "@tolgee/react";
import { useEffect, useState } from "react";
import { getPersonas, type PersonaCard } from "../api/personas";
import { Avatar, TileButton } from "../ui";

// The reaction frames swap in on the next graded answer; warming them at the pick means
// the swap never waits on a fetch.
function warmImages(images: Record<string, string>) {
  for (const url of Object.values(images)) {
    const img = new Image();
    img.src = url;
  }
}

export function PersonaPicker({
  onPick,
  busy,
  error = "",
}: {
  onPick: (personaId: string) => void;
  busy: boolean;
  error?: string;
}) {
  const { t } = useTranslate();
  const lang = useTolgee(["language"]).getLanguage() ?? "de";
  const shown = (text: Record<string, string>) => text[lang] ?? text.de;
  const [personas, setPersonas] = useState<PersonaCard[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPersonas()
      .then((loaded) => !cancelled && setPersonas(loaded))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  // The error arrives as its key, so a flip of the flag translates it with everything else.
  const problem = failed ? t("chat.error") : error === "" ? "" : t(error);

  return (
    <section className="pick">
      <div className="pick-hero">
        <h1 className="pick-title">{t("app.title")}</h1>
        <p className="pick-subtitle">{t("app.subtitle")}</p>
      </div>
      <h2 className="pick-lead">{t("pick.lead")}</h2>
      {problem !== "" && (
        <p className="pick-error" style={{ color: "var(--c-danger)" }}>
          {problem}
        </p>
      )}
      <ul className="pick-grid">
        {(personas ?? []).map((persona) => (
          <li key={persona.id}>
            <TileButton
              className="pick-card"
              disabled={busy}
              onClick={() => {
                warmImages(persona.images);
                onPick(persona.id);
              }}
            >
              <Avatar
                name={shown(persona.name)}
                imageUrl={persona.images.neutral ?? null}
                mood="neutral"
                size={256}
              />
              <span className="pick-name">{shown(persona.name)}</span>
              <span className="pick-tagline">{shown(persona.tagline)}</span>
            </TileButton>
          </li>
        ))}
      </ul>
      <p className="pick-note">{t("chat.disclaimer")}</p>
    </section>
  );
}
