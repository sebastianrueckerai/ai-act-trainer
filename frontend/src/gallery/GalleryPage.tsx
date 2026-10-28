import type { CSSProperties, ReactNode } from "react";
import { useTolgee, useTranslate } from "@tolgee/react";
import { stageFixture } from "../stage/fixture";
import { ChapterDivider, LevelCard } from "../chat/ChapterMarks";
import { CourseStatus } from "../chat/CourseStatus";
import { BudgetNotice } from "../chat/LimitNotice";
import { formatCountdown, formatReset } from "../chat/useCountdown";
import {
  Avatar,
  Badge,
  Bubble,
  Button,
  Card,
  Cells,
  Chip,
  Frame,
  Icon,
  Select,
  TextArea,
  TextInput,
} from "../ui";
import { DEFAULT_COLORS, derivePalette, type Look, type Mode } from "../theme/palette";
import type { Text } from "../theme/useTheme";
import type { GallerySection } from "./sections";

export { GALLERY_SECTIONS, type GallerySection } from "./sections";

function Section({ id, children }: { id: GallerySection; children: ReactNode }) {
  return (
    <section className="mt-6" data-gallery={id}>
      <h2>{id}</h2>
      {children}
    </section>
  );
}

// Fixed times in a fixed zone, so the shots never move: a day reset 2:14:08 ahead at
// 14:00 MESZ, a month reset on 1 November.
const NOW = Date.parse("2026-10-11T09:45:52Z");
const DAY_RESET = new Date("2026-10-11T12:00:00Z");
const MONTH_RESET = new Date("2026-11-01T00:00:00Z");

function Notices() {
  const { t } = useTranslate();
  const language = useTolgee(["language"]).getLanguage() ?? "de";
  const clock = (at: Date) => ({
    left: at.getTime() - NOW,
    countdown: formatCountdown(at.getTime() - NOW, t),
    ...formatReset(at, language, t, "Europe/Berlin"),
  });
  return (
    <div className="flex flex-col gap-2">
      <BudgetNotice scope="seats" clock={null} onRetry={() => {}} />
      <BudgetNotice scope="pool_day" clock={clock(DAY_RESET)} />
      <BudgetNotice scope="pool_month" clock={clock(MONTH_RESET)} />
      <BudgetNotice scope="day" clock={clock(DAY_RESET)} />
      <BudgetNotice scope="month" clock={clock(MONTH_RESET)} />
      <BudgetNotice scope="global" clock={null} onRetry={() => {}} />
    </div>
  );
}

type ColumnProps = { look: Look; mode: Mode; text?: Text };

function Column({ look, mode, text = "pixel", children }: ColumnProps & { children: ReactNode }) {
  return (
    <div
      data-look={look}
      data-mode={mode}
      data-text={text}
      style={{
        ...(derivePalette(DEFAULT_COLORS, mode, look) as CSSProperties),
        background: "var(--c-bg)",
        color: "var(--c-text)",
      }}
      className="flex flex-col rounded border border-neutral-300 p-4"
    >
      <h3 className="mb-2 font-bold">
        {look} {mode} {text === "plain" ? "plain" : ""}
      </h3>
      {children}
    </div>
  );
}

function LookColumn(props: ColumnProps) {
  return (
    <Column {...props}>
      <Section id="buttons">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="send">
            Primary
          </Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button disabled>Disabled</Button>
          <Chip selected>Selected</Chip>
          <Chip>Chip</Chip>
        </div>
      </Section>
      <Section id="inputs">
        <div className="flex flex-col gap-2">
          <TextInput aria-label="text input" placeholder="TextInput" />
          <TextArea aria-label="text area" placeholder="TextArea" rows={2} />
          <Select aria-label="select" defaultValue="one">
            <option value="one">Select</option>
            <option value="two">Second option</option>
          </Select>
        </div>
      </Section>
      <Section id="chat">
        <Frame>
          <div className="flex flex-col gap-2">
            <Bubble role="user">User message</Bubble>
            <Bubble role="assistant">Assistant message with a longer sentence.</Bubble>
            {props.look === "pixel" && (
              <Bubble role="assistant" className="ui-bubble--question">
                Assistant message ending on a question?
              </Bubble>
            )}
            <div className="chat-wait-bubble" aria-label="Antwort wird vorbereitet …">
              <span className="chat-wait" aria-hidden="true" />
              <span className="chat-working">Die Beute wird gewogen.</span>
            </div>
            <div className="relative" style={{ height: 80 }}>
              <Button variant="secondary" icon="down" className="chat-jump" aria-label="Zur neuesten Nachricht" />
            </div>
            <div className="message-choices">
              <Chip>
                <span className="chip-key">A.</span>{" "}
                <span className="chip-text">A short option</span>
              </Chip>
              <Chip className="chip-verdict--ok">
                <span className="chip-key">B.</span>{" "}
                <span className="chip-text">An option whose sentence needs two lines to say it</span>
              </Chip>
            </div>
          </div>
        </Frame>
      </Section>
      <Section id="cards">
        <Card title="Model answer">
          <p>Card body with a citation line.</p>
          <Badge tone="success">correct</Badge> <Badge tone="danger">wrong</Badge>{" "}
          <Badge>neutral</Badge>
        </Card>
      </Section>
      <Section id="icons">
        <div className="flex flex-wrap gap-2">
          <Icon name="send" />
          <Icon name="lock" />
          <Icon name="check" />
          <Icon name="look" />
          <Icon name="signout" />
          <Icon name="file" />
        </div>
      </Section>
      <Section id="progress">
        <div className="flex flex-col items-start gap-2">
          <Cells
            cells={["done", "done", "now", "ahead", "ahead", "ahead"]}
            flag="down"
            label="Schritt 3 von 6"
          />
          <Cells
            cells={["done", "done", "done", "done", "done", "done"]}
            flag="up"
            label="Schritt 6 von 6"
            flashIndex={5}
          />
          <Cells
            cells={["ok", "ok", "wrong", "ok", ...Array<"ahead">(6).fill("ahead")]}
            label="3 von 10 richtig"
          />
        </div>
      </Section>
      <Section id="avatars">
        <div className="flex items-end gap-3">
          <Avatar name="Depressobot" imageUrl={null} mood="neutral" />
          <Avatar name="Depressobot" imageUrl={null} mood="happy" size={48} />
        </div>
      </Section>
      <Section id="stage">
        <CourseStatus stage={{ ...stageFixture, streak: 0, attempt: null }} />
        <CourseStatus
          stage={{
            ...stageFixture,
            persona: { id: "marvin", name: "Depressobot", image_url: null },
            mood: "happy",
            streak: 2,
            attempt: { kind: "test", index: 4, results: [true, true, false, true], total: 10 },
          }}
        />
        <CourseStatus
          stage={{
            ...stageFixture,
            chapters: stageFixture.chapters.map((chapter) => ({
              ...chapter,
              state: "done",
              step: null,
            })),
            attempt: null,
          }}
        />
      </Section>
      <Section id="notices">
        <Notices />
      </Section>
    </Column>
  );
}

// The chapter marks stand in a grid of their own below the rest, so no settled
// screenshot above them moves.
function ChapterColumn(props: ColumnProps) {
  return (
    <Column {...props}>
      <Section id="chapter">
        <div className="flex flex-col gap-2">
          {[1, 8].map((index) => (
            <div key={index} className="message flex flex-col">
              <ChapterDivider
                part={{ kind: "chapter_done", chapter_id: "01", index, total: 8, title: "Kapitel" }}
              />
            </div>
          ))}
          <div className="message flex flex-col items-start gap-[8px]">
            <LevelCard
              part={{
                kind: "chapter_start",
                title: "Was du hineingeben darfst",
                intro: "Eine Frage stellt sich jeden Tag: Was darf in den Chatassistenten hinein?",
              }}
            />
          </div>
        </div>
      </Section>
    </Column>
  );
}

const COLUMNS: ColumnProps[] = [
  { look: "pixel", mode: "dark" },
  { look: "clean", mode: "dark" },
  { look: "pixel", mode: "light" },
  { look: "clean", mode: "light" },
  { look: "pixel", mode: "dark", text: "plain" },
];

export function GalleryPage() {
  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1>Primitives gallery</h1>
      <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
        {COLUMNS.map((column) => (
          <LookColumn key={`${column.look}-${column.mode}-${column.text}`} {...column} />
        ))}
      </div>
      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        {COLUMNS.map((column) => (
          <ChapterColumn key={`${column.look}-${column.mode}-${column.text}`} {...column} />
        ))}
      </div>
    </main>
  );
}
