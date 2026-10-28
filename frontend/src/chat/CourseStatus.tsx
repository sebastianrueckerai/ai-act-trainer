import { useEffect, useState } from "react";
import { useTranslate } from "@tolgee/react";
import type { Stage } from "../api/chat";
import { Badge, Button, Cells, type CellState } from "../ui";

const FLASH_MS = 1800;

type Bar = { index: number; step: number; steps: number };
type Shown = { bar: Bar; flash?: number };

function chapterBar(chapters: Stage["chapters"]): Bar | null {
  const index = chapters.findIndex((chapter) => chapter.state === "current");
  if (index !== -1) return { index, step: chapters[index].step ?? 0, steps: chapters[index].steps };
  // At a chapter end none is current until the click: the bar stays on the one just
  // finished.
  const last = chapters.filter((chapter) => chapter.state === "done").length - 1;
  return last < 0 ? null : { index: last, step: chapters[last].steps, steps: chapters[last].steps };
}

function flashBetween(before: Bar | null, after: Bar | null): Shown | null {
  if (before === null || after === null) return null;
  if (after.index === before.index && after.step > before.step) {
    return { bar: after, flash: after.step - 1 };
  }
  return null;
}

// The just-done cell flashes. A finished chapter needs no hold: it stays full, flag up,
// until the student clicks on to the next one.
function useShownBar(bar: Bar | null): Shown | null {
  const [last, setLast] = useState(bar);
  const [held, setHeld] = useState<Shown | null>(null);
  if (bar?.index !== last?.index || bar?.step !== last?.step || bar?.steps !== last?.steps) {
    setLast(bar);
    setHeld(flashBetween(last, bar));
  }
  useEffect(() => {
    if (held === null) return;
    const timer = setTimeout(() => setHeld(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [held]);
  return held ?? (bar && { bar });
}

export function StageName({ stage }: { stage: Stage }) {
  const { t } = useTranslate();
  const shown = useShownBar(chapterBar(stage.chapters));
  // The graded test covers the whole course, so no chapter belongs beside it. A step's
  // own question is part of the chapter and shows no label of its own.
  if (stage.attempt?.kind === "test") {
    const { results, total } = stage.attempt;
    const cells = Array.from({ length: total }, (_, i): CellState =>
      i >= results.length ? "ahead" : results[i] ? "ok" : "wrong",
    );
    return (
      <div className="stage-name">
        <span>{t("stage.test")}</span>
        <Cells
          cells={cells}
          label={t("stage.test_of", { n: results.filter(Boolean).length, total })}
        />
      </div>
    );
  }
  if (shown === null) return null;
  const { index, step, steps } = shown.bar;
  const cells = Array.from({ length: steps }, (_, i): CellState =>
    i < step ? "done" : i === step ? "now" : "ahead",
  );
  return (
    <div className="stage-name">
      <span>{t("stage.chapter_of", { n: index + 1, total: stage.chapters.length })}</span>
      <Cells
        cells={cells}
        flag={step < steps ? "down" : "up"}
        label={t("stage.step_of", { n: Math.min(step + 1, steps), total: steps })}
        flashIndex={shown.flash}
      />
    </div>
  );
}

export function CourseStatus({
  stage,
  confirming = false,
  onConfirm,
  onCancel,
}: {
  stage: Stage | null;
  confirming?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}) {
  const { t } = useTranslate();

  if (stage === null) return null;
  return (
    <div className="course-status">
      <StageName stage={stage} />
      {stage.streak > 1 && <Badge tone="success">{t("stage.streak", { n: stage.streak })}</Badge>}
      {confirming && (
        <div className="course-status-confirm">
          <span>{t("stage.restart_confirm")}</span>
          <Button variant="primary" onClick={onConfirm}>
            {t("stage.restart_yes")}
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            {t("stage.restart_cancel")}
          </Button>
        </div>
      )}
    </div>
  );
}
