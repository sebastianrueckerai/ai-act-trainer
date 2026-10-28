import { useTranslate } from "@tolgee/react";
import type { PartOut } from "../api/chat";
import { Badge, Card } from "../ui";
import { CitationsPanel } from "./CitationsPanel";

export function ModelAnswerCard({ part }: { part: Extract<PartOut, { kind: "card" }> }) {
  const { t } = useTranslate();
  return (
    <Card title={part.question}>
      <div className="answer-block">
        <span className="answer-label">{t("chat.card.model_answer")}</span>
        <p className="answer-body">{part.model_answer}</p>
      </div>
      <div className="answer-block">
        <span className="answer-label">{t("chat.card.explanation")}</span>
        <p className="answer-body">{part.explanation}</p>
      </div>
      <CitationsPanel parts={part.citations} />
      <div className="answer-verdict">
        {part.correct && part.tries > 1 ? (
          <Badge tone="neutral">{t("chat.card.settled")}</Badge>
        ) : (
          <Badge tone={part.correct ? "success" : "danger"}>
            {part.correct ? t("chat.card.correct") : t("chat.card.incorrect")}
          </Badge>
        )}
      </div>
    </Card>
  );
}
