import { Fragment } from "react";
import { useTranslate } from "@tolgee/react";
import type { PartOut } from "../api/chat";
import { Bubble } from "../ui";

// The chapter end as a stored part, so the thread reads as chapters on a reload too: a
// frameless line with the course's route, the chapters done lit and the rest hollow.
export function ChapterDivider({ part }: { part: Extract<PartOut, { kind: "chapter_done" }> }) {
  const { t } = useTranslate();
  const { index, total } = part;
  return (
    <div className="chapter-divider" title={part.title}>
      <span className="chapter-divider-line" />
      <span className="chapter-divider-what">
        {index === total ? t("chat.course_done", { total }) : t("chat.chapter_done", { n: index })}
      </span>
      <span className="chapter-route" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <Fragment key={i}>
            {i > 0 && <s />}
            <i data-lit={i < index || undefined} />
          </Fragment>
        ))}
      </span>
      <span className="chapter-divider-line" />
    </div>
  );
}

// The next chapter opens on its title between two short lines, then its curated intro.
export function LevelCard({ part }: { part: Extract<PartOut, { kind: "chapter_start" }> }) {
  return (
    <>
      <h2 className="level-card-title">{part.title}</h2>
      <Bubble role="assistant">{part.intro}</Bubble>
    </>
  );
}
