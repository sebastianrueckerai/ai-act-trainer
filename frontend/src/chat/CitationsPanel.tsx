import { useTranslate } from "@tolgee/react";

// The bare citation shape a link needs: both a citations part and a card's
// own citations carry it, `kind` or not.
export type CitationLike = { ref: string; title: string; quote: string; url: string };

export function CitationsPanel({ parts }: { parts: CitationLike[] }) {
  const { t } = useTranslate();
  if (parts.length === 0) return null;
  return (
    <div className="citations-line">
      <span className="citations-label">{t("chat.citations.title")}</span>
      {parts.map((part, index) => (
        <a
          key={index}
          className="citations-ref"
          href={part.url}
          target="_blank"
          rel="noreferrer"
          title={part.quote}
        >
          {part.ref}
        </a>
      ))}
    </div>
  );
}
