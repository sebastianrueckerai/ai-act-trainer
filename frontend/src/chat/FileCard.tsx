import { useTolgee, useTranslate } from "@tolgee/react";
import type { PartOut } from "../api/chat";
import { Card, Icon } from "../ui";

export function FileCard({ part }: { part: Extract<PartOut, { kind: "file" }> }) {
  const { t } = useTranslate();
  const englishUi = useTolgee(["language"]).getLanguage() === "en";
  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <Icon name="file" />
          {part.title}
        </span>
      }
    >
      <div className="flex items-center gap-3">
        <a
          className="ui-button ui-button--primary"
          href={part.url}
          target="_blank"
          rel="noreferrer"
        >
          {t("chat.file.open")}
        </a>
      </div>
      {englishUi && <p className="file-card-note">{t("files.german_only")}</p>}
    </Card>
  );
}
