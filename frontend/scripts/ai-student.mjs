#!/usr/bin/env node
// The AI student: walks the real UI of the trainer with a real model as the learner.
// One browser context per run, a fresh dev subject, the real tutor stack. State comes
// from the session API the page itself uses; every action goes through the real DOM
// (chips, buttons, the composer). Screenshots only at anomalies, chapter boundaries
// and the end. Artifacts land in runs/ai-student/<run>/.
//
// Arms: warm — the student sees the current chapter in full plus a digest of the
// chapters before it; cold — only the question on screen, no course material, which
// measures what the course adds over the model's prior knowledge.
//
// Usage, from frontend/:
//   node scripts/ai-student.mjs --model glm-5.3-flash --arm warm [--max-turns 130]
import { chromium } from "@playwright/test";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import fs from "node:fs";
import path from "node:path";

const arg = (name, dflt) => {
  const i = process.argv.indexOf("--" + name);
  return i >= 0 ? process.argv[i + 1] : dflt;
};
const MODEL = arg("model", "glm-5.3-flash");
const ARM = arg("arm", "warm");
const BASE = arg("base", "http://localhost:8000");
const MAX_TURNS = Number(arg("max-turns", "400"));
const PERSONA_INDEX = Number(arg("persona", "0"));

const REPO = path.resolve("..");
const zaiKey =
  process.env.ZAI_API_KEY ??
  (existsSync(path.join(REPO, ".env.tools"))
    ? readFileSync(path.join(REPO, ".env.tools"), "utf8").match(/^ZAI_API_KEY=(.+)$/m)?.[1]?.trim()
    : undefined);
if (!zaiKey) {
  console.error("no ZAI_API_KEY: set it or put it in ../.env.tools");
  process.exit(2);
}

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const RUN_DIR = path.join(REPO, "runs", "ai-student", stamp + "-" + MODEL + "-" + ARM);
const SHOTS = path.join(RUN_DIR, "shots");
mkdirSync(SHOTS, { recursive: true });
const SUBJECT = "guest-ai-student-" + stamp.slice(0, 16);

const anomalies = [];
const turnLog = [];
const sseLog = [];
const chapterTimes = [];
let tokensIn = 0;
let tokensOut = 0;
let studentMsTotal = 0;
let tutorMsTotal = 0;
let currentTurn = 0;

const norm = (s) =>
  (s ?? "").toLowerCase().replace(/["'«»„“”’]/g, "").replace(/\s+/g, " ").trim();

const SYSTEM_WARM = [
  "Du bist Jo, ein fleißiger Angestellter ohne Rechtshintergrund, und machst gerade",
  'den Pflichtkurs "KI-Führerschein" zum EU AI Act. Du chattest mit einem KI-Tutor',
  "und willst den Kurs gut abschließen.",
  "- Antworte auf Deutsch, kurz und in eigenen Worten, meist ein bis drei Sätze, wie ein Mensch im Chat.",
  "- Beantworte die Fragen des Tutors mit dem, was der Kurs dich bisher gelehrt hat.",
  "  Wenn du es aus dem Kurs wirklich nicht weißt, sag es kurz und frage nach.",
  "- Wenn der Tutor nur fragt, ob du bereit oder einverstanden bist, antworte knapp zustimmend.",
].join("\n");

const SYSTEM_COLD = [
  "Du bist ein Angestellter und beantwortest gerade Fragen zum EU AI Act.",
  "Du hast keinen Kurs dazu besucht und das Kursmaterial nie gesehen.",
  "- Antworte auf Deutsch, kurz, ein bis drei Sätze, aus deinem Allgemeinwissen.",
].join("\n");

async function askStudent(messages, opts) {
  let budget = opts?.maxTokens ?? 4000;
let empties = 0;
  for (let attempt = 1; ; attempt++) {
    const t0 = Date.now();
    let res;
    try {
      res = await fetch("https://api.z.ai/api/paas/v4/chat/completions", {
        method: "POST",
        headers: { Authorization: "Bearer " + zaiKey, "Content-Type": "application/json" },
        body: JSON.stringify({ model: MODEL, messages, temperature: 0.6 + empties * 0.15, max_tokens: budget }),
      });
    } catch (e) {
      if (attempt >= 5) {
        console.error("zai unreachable: " + e);
        process.exit(3);
      }
      await new Promise((r) => setTimeout(r, 5000));
      continue;
    }
    if (res.status === 429 || res.status >= 500) {
      if (attempt >= 5) {
        console.error("zai " + res.status + " after retries: " + (await res.text()).slice(0, 200));
        process.exit(3);
      }
      await new Promise((r) => setTimeout(r, 8000));
      continue;
    }
    if (!res.ok) {
      console.error("zai " + res.status + ": " + (await res.text()).slice(0, 200));
      process.exit(3);
    }
    const data = await res.json();
    const text = (data.choices?.[0]?.message?.content ?? "").trim();
    tokensIn += data.usage?.prompt_tokens ?? 0;
    tokensOut += data.usage?.completion_tokens ?? 0;
    const ms = Date.now() - t0;
    studentMsTotal += ms;
    if (!text) {
      console.error("zai empty content, finish " + data.choices?.[0]?.finish_reason);
if (empties++ < 3) { budget *= 2; await new Promise((r) => setTimeout(r, 8000)); continue; }
      process.exit(3);
    }
    return { text, ms };
  }
}

async function readDom(page) {
  return page.evaluate(() => {
    const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    const assistant = [...document.querySelectorAll(".message--assistant")];
    const latest =
      assistant.filter((el) => el.getAttribute("data-latest-assistant") === "true").at(-1) ??
      assistant.at(-1);
    const chips = latest ? [...latest.querySelectorAll(".message-choices .ui-chip")] : [];
    const input = document.querySelector(".composer textarea, .composer input");
    const notice = document.querySelector(".ui-notice");
    const navButtons = [...document.querySelectorAll("button")]
      .filter((b) => visible(b) && !b.disabled && b.textContent.trim())
      .map((b) => b.textContent.trim())
      .filter((t) => !/^(Senden|English|Deutsch|Anmelden|Abmelden|Pixel|Dunkel|Neu starten)$/.test(t));
    return {
      assistantCount: assistant.length,
      latestText: latest ? latest.innerText.trim() : "",
      chips: chips.map((c) => ({
        label: c.textContent.trim(),
        pressed: c.getAttribute("aria-pressed") === "true", disabled: c.disabled,
      })),
      composerEnabled: !!input && !input.disabled && !input.readOnly,
      noticeText: notice && visible(notice) ? notice.innerText.trim() : null,
      navButtons,
    };
  });
}

async function getSession(page) {
  try {
    const res = await page.request.get(BASE + "/api/session");
    return res.ok() ? await res.json() : null;
  } catch {
    return null;
  }
}

const chaptersDone = (sess) =>
  (sess?.messages ?? []).reduce(
    (n, m) => n + (m.parts ?? []).filter((p) => p.kind === "chapter_done").length,
    0,
  );

// Everything since the last chapter_done part, as {role, text} pairs.
function chapterSlice(messages) {
  const out = [];
  let cut = -1;
  for (const m of messages ?? []) {
    out.push({ role: m.role === "user" ? "user" : "assistant", text: m.text ?? "" });
    if ((m.parts ?? []).some((p) => p.kind === "chapter_done")) cut = out.length - 1;
  }
  return out.slice(cut + 1).filter((m) => m.text);
}

function buildMessages(sess, dom, digest) {
  const open = dom.chips.filter((c) => !c.pressed && !c.disabled);
  const affordance = [];
  if (open.length)
    affordance.push(
      "Der Chat zeigt Auswahlmoeglichkeiten: " +
        open.map((c) => JSON.stringify(c.label)).join(", ") +
        ". Antworte mit genau einer dieser Beschriftungen, wortgleich.",
    );
  else if (dom.navButtons.length)
    affordance.push(
      "Der Chat bietet diese Schaltflaechen: " +
        dom.navButtons.map((b) => JSON.stringify(b)).join(", ") +
        ". Wenn eine passt, antworte mit ihrer Beschriftung; sonst mit deiner Antwort als Text.",
    );
  if (ARM === "cold")
    return [
      { role: "system", content: SYSTEM_COLD },
      { role: "user", content: (dom.latestText + "\n\n" + affordance.join(" ")).trim() },
    ];
  const msgs = [{ role: "system", content: SYSTEM_WARM }];
  if (digest)
    msgs.push(
      {
        role: "user",
        content: "Zusammenfassung der Kapitel, die du schon hinter dir hast:\n" + digest,
      },
      { role: "assistant", content: "Verstanden, weiter im naechsten Kapitel." },
    );
  msgs.push(
    ...chapterSlice(sess?.messages)
      .slice(-40)
      .map((m) => ({ role: m.role, content: m.text })),
  );
  msgs.push({
    role: "user",
    content: affordance.length
      ? affordance.join(" ")
      : "Antworte jetzt auf die letzte Nachricht des Tutors. Nur die Antwort selbst.",
  });
  return msgs;
}

async function makeDigest(chapterText) {
  const { text } = await askStudent(
    [
      { role: "system", content: "Du fasst Schulungschats praezise zusammen." },
      {
        role: "user",
        content:
          "Fasse den Stoff dieses Kurskapitels in hoechstens acht Stichpunkten zusammen, nur das fachlich Inhaltliche:\n\n" +
          chapterText.slice(0, 30000),
      },
    ],
    { maxTokens: 2500 },
  );
  return text;
}

async function act(page, reply, dom) {
  const cleaned = norm(reply.replace(/^(jo|student|antwort|meine antwort|auswahl)\s*[:\-]\s*/i, ""));
  const open = dom.chips.filter((c) => !c.pressed && !c.disabled);
  if (open.length) {
    const hit =
      open.find((c) => norm(c.label) === cleaned) ??
      open.find((c) => cleaned.includes(norm(c.label))) ??
      open.find((c) => norm(c.label).startsWith(cleaned) || cleaned.startsWith(norm(c.label)));
    const pick = hit ?? open[0];
    if (!hit) anomalies.push({ turn: currentTurn, type: "chip-fallback", reply: reply.slice(0, 100) });
    const chipLoc = (label) =>
      page
        .locator("[data-latest-assistant=\"true\"] .message-choices .ui-chip")
        .filter({ hasText: label })
        .first();
    try {
      await chipLoc(pick.label).click({ timeout: 15000 });
      return { kind: "chip", label: pick.label };
    } catch {
      await page.screenshot({ path: RUN_DIR + "/shots/act-fail-" + currentTurn + ".png" });
      const fresh = await readDom(page);
      const again = fresh.chips.filter((c) => !c.pressed && !c.disabled).find((c) => norm(c.label) === norm(pick.label));
      try {
        await chipLoc(again ? again.label : pick.label).click({ timeout: 5000 });
        return { kind: "chip", label: pick.label, retried: true };
      } catch {
        anomalies.push({ turn: currentTurn, type: "chip-click-failed", reply: reply.slice(0, 100) });
      }
    }
  }
  const button =
    dom.navButtons.find((b) => norm(b) === cleaned) ??
    (cleaned.length <= 24
      ? dom.navButtons.find((b) => norm(b).startsWith(cleaned) || cleaned.startsWith(norm(b)))
      : undefined);
  if (button) {
    await page.locator("button:not(.ui-chip)").filter({ hasText: button }).first().click({ timeout: 15000 });
    return { kind: "button", label: button };
  }
  if (!dom.composerEnabled) {
    if (dom.navButtons.length) {
      anomalies.push({ turn: currentTurn, type: "composer-closed-button-fallback", reply: reply.slice(0, 100) });
      await page.locator("button:not(.ui-chip)").filter({ hasText: dom.navButtons[0] }).first().click({ timeout: 15000 });
      return { kind: "button", label: dom.navButtons[0] };
    }
    console.error("nowhere to answer: composer closed, no buttons; reply=" + reply.slice(0, 80));
    process.exit(4);
  }
  await page.locator(".composer textarea").first().fill(reply.slice(0, 1500), { timeout: 15000 });
  await page.getByRole("button", { name: "Senden" }).first().click({ timeout: 15000 });
  return { kind: "text", label: reply.slice(0, 80) };
}

// Quiet for 2.5s and interactive again (composer, open chips or a button): the
// tutor turn is whole (D97).
async function waitSettled(page, timeoutMs) {
  const limit = timeoutMs ?? 150000;
  const t0 = Date.now();
  let sig = "";
  let stableSince = Date.now();
  while (Date.now() - t0 < limit) {
    const dom = await readDom(page);
    const s = JSON.stringify([
      dom.assistantCount,
      dom.latestText.length,
      dom.chips.length,
      dom.composerEnabled,
      dom.navButtons.join("|"),
      (dom.noticeText ?? "").slice(0, 40),
    ]);
    if (s !== sig) {
      sig = s;
      stableSince = Date.now();
    } else if (Date.now() - stableSince >= 2500) {
      const interactive =
        dom.composerEnabled || dom.chips.some((c) => !c.pressed) || dom.navButtons.length > 0;
      if (interactive || dom.noticeText) return dom;
    }
    await page.waitForTimeout(1200);
  }
  return null;
}

const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
page.on("pageerror", (e) =>
  anomalies.push({ turn: currentTurn, type: "pageerror", msg: String(e).slice(0, 200) }),
);
page.on("console", (m) => {
  if (m.type() === "error" && anomalies.length < 40)
    anomalies.push({ turn: currentTurn, type: "console", msg: m.text().slice(0, 200) });
});
page.on("response", (r) => {
  if (r.url().includes("/api/") && r.status() >= 500)
    anomalies.push({ turn: currentTurn, type: "http " + r.status(), url: r.url().slice(0, 120) });
  if (/\/api\/chat\/\d+\/(opening|turns)$/.test(r.url()))
    r.text()
      .then((body) => sseLog.push({ t: Date.now(), url: r.url(), body: body.slice(0, 200000) }))
      .catch(() => {});
});

await page.route("**/api/auth/dev/login", (route) =>
  route.continue({ postData: JSON.stringify({ subject: SUBJECT }) }),
);
await page.goto(BASE + "/");
await page.getByRole("button", { name: "Anmelden" }).click({ timeout: 20000 });
const card = page.locator(".pick-card").nth(PERSONA_INDEX);
const personaName = ((await card.innerText()).split("\n")[0] ?? "").trim();
await card.click({ timeout: 20000 });
console.log(
  "run " + path.basename(RUN_DIR) + " subject=" + SUBJECT + " persona=" + personaName +
    " model=" + MODEL + " arm=" + ARM,
);

const t0 = Date.now();
let digest = "";
let chapterText = "";
let chaptersSeen = 0;
let resend = null;
let wasResend = false;
let lastTutorText = "";
let lastReplyN = "";
let repeats = 0;
let outcome = "max-turns";

await page.waitForSelector(".message--assistant, .ui-notice", { timeout: 120000 });
let settled = await waitSettled(page, 180000);
if (!settled) {
  anomalies.push({ turn: 0, type: "opening-never-settled" });
  outcome = "stuck";
}

for (currentTurn = 1; currentTurn <= MAX_TURNS; currentTurn++) {
  if (outcome !== "max-turns") break;
  const sess = await getSession(page);
  if (!sess) { anomalies.push({ turn: currentTurn, type: "no-session" }); break; }
  const phase = String(sess.phase ?? "");
  if (phase === "done") { outcome = "done"; break; }
  const notice = (settled?.noticeText ?? "").slice(0, 300);
  if (/aufgebraucht|andrang|high demand/i.test(notice)) { outcome = "budget"; break; }

  const done = chaptersDone(sess);
  if (done > chaptersSeen) {
    for (let i = chaptersSeen; i < done; i++) {
      const elapsed = Math.round((Date.now() - t0) / 1000);
      chapterTimes.push(elapsed);
      const shot = "shots/chapter-" + (i + 1) + ".png";
      await page.screenshot({ path: RUN_DIR + "/" + shot });
      if (ARM === "warm" && chapterText)
        try { digest = digest + "\n\n" + (await makeDigest(chapterText)); } catch {}
      console.log("chapter " + (i + 1) + " done at " + Math.round(elapsed / 60) + "min");
    }
    chaptersSeen = done;
  }
  chapterText = chapterSlice(sess.messages ?? [])
    .map((m) => m.role.toUpperCase() + ": " + m.text)
    .join("\n");

  const tAsk = Date.now();
  // A pending confirm closes the composer and waits for a button (the bell): the
  // student's answer went out last turn, so click it without a model call.
  if (
    settled &&
    !settled.composerEnabled &&
    settled.navButtons.length &&
    !settled.chips.some((c) => !c.pressed && !c.disabled)
  ) {
    const label = settled.navButtons[0];
    await page.locator("button:not(.ui-chip)").filter({ hasText: label }).first().click({ timeout: 15000 });
    const tSend = Date.now();
    settled = await waitSettled(page);
    const tutorMs = Date.now() - tSend;
    tutorMsTotal += tutorMs;
    turnLog.push({ turn: currentTurn, phase, chapter: chaptersSeen, reply: "[confirm] " + label, tutor: (settled?.latestText ?? "").slice(0, 600), studentMs: 0, tutorMs, chipsUsed: "confirm", resend: false });
    fs.appendFileSync(
      RUN_DIR + "/transcript.jsonl",
      JSON.stringify({ turn: currentTurn, role: "student", ts: tSend, text: "[confirm] " + label }) + "\n" +
        JSON.stringify({ turn: currentTurn, role: "tutor", ts: Date.now(), text: settled?.latestText ?? "" }) + "\n",
    );
    console.log("turn " + currentTurn + " " + phase + " ch" + chaptersSeen + " | confirm: " + label.slice(0, 60).replace(/\n/g, " "));
    continue;
  }
  let askMsgs = buildMessages(sess, settled ?? readDom(page), digest);
  if (repeats >= 2 && !resend && lastReplyN.length > 6)
    askMsgs.push({
      role: "user",
      content:
        "Deine letzte Antwort wurde offenbar nicht angenommen. Wiederhole sie nicht. Formuliere sie anders und beantworte die Frage direkt.",
    });
  wasResend = Boolean(resend);
      const reply = resend ?? (await askStudent(askMsgs)).text;
  repeats = norm(reply) === lastReplyN ? repeats + 1 : 0;
  lastReplyN = norm(reply);
  const acted = await act(page, reply, settled);
  const tSend = Date.now();
  settled = await waitSettled(page);
  const tutorMs = Date.now() - tSend;
  tutorMsTotal += tutorMs;
  turnLog.push({ turn: currentTurn, phase, chapter: chaptersSeen, reply: reply.slice(0, 600), tutor: (settled?.latestText ?? "").slice(0, 600), studentMs: tSend - tAsk, tutorMs, chipsUsed: acted?.kind, resend: resend !== null });
  fs.appendFileSync(RUN_DIR + "/transcript.jsonl",
    JSON.stringify({ turn: currentTurn, role: "student", ts: tSend, text: reply }) + "\n" +
    JSON.stringify({ turn: currentTurn, role: "tutor", ts: Date.now(), text: settled?.latestText ?? "" }) + "\n");
  console.log(
    "turn " + currentTurn + " " + phase + " ch" + chaptersSeen + " | student " +
      Math.round((tSend - tAsk) / 1000) + "s tutor " + Math.round(tutorMs / 1000) + "s | " +
      acted.kind + ": " + reply.slice(0, 60).replace(/\n/g, " "),
  );

  if (!settled) {
    anomalies.push({ turn: currentTurn, type: "stuck-no-settle" });
    await page.screenshot({ path: RUN_DIR + "/shots/anomaly-stuck-" + currentTurn + ".png" });
    outcome = "stuck";
    break;
  }
  if (norm(settled.latestText) === norm(lastTutorText)) {
    anomalies.push({ turn: currentTurn, type: "tutor-repeat" });
    resend = (acted.kind === "text" || acted.kind === "chip") && !wasResend ? reply : null;
  } else { resend = null; }
  lastTutorText = settled.latestText;
  if (/clerk|jester|marvin|pirate|sergeant|lesson_step|persona_id|q-\d{2}-/i.test(settled.latestText)) {
    anomalies.push({ turn: currentTurn, type: "identifier-leak" });
    await page.screenshot({ path: RUN_DIR + "/shots/anomaly-leak-" + currentTurn + ".png" });
  }
}

const wall = Math.round((Date.now() - t0) / 1000);
const finalSess = (await getSession(page)) ?? {};
await page.screenshot({ path: RUN_DIR + "/shots/final.png" });
const tailTexts = (finalSess.messages ?? []).slice(-6).map((m) => String(m.text ?? ""));
let score = null;
for (const t of tailTexts) {
  const m = t.match(/(\d{1,2})\s*(?:\/|von)\s*10/);
  if (m) score = parseInt(m[1], 10);
}
const verdicts = [];
for (const rec of sseLog)
  for (const line of rec.body.split("\n")) {
    if (!line.startsWith("data: ")) continue;
    try {
      const ev = JSON.parse(line.slice(6));
      if (["answer_result", "finale", "chapter_complete"].includes(ev.name))
        verdicts.push({ t: rec.t, name: ev.name, data: ev.data });
    } catch {}
  }
const summary = {
  model: MODEL, arm: ARM, subject: SUBJECT, persona: personaName, outcome,
  score, passed: score !== null && score >= 8,
  turns: currentTurn, wallSec: wall,
  studentSec: Math.round(studentMsTotal / 1000), tutorSec: Math.round(tutorMsTotal / 1000),
  tokensIn, tokensOut, chapters: chaptersSeen, chapterTimes, anomalies, verdicts, turnLog,
};
fs.writeFileSync(RUN_DIR + "/summary.json", JSON.stringify(summary, null, 2));
fs.writeFileSync(RUN_DIR + "/sse.jsonl", sseLog.map((r) => JSON.stringify(r)).join("\n"));
fs.writeFileSync(
  RUN_DIR + "/transcript.md",
  (finalSess.messages ?? []).map((m) => "## " + String(m.role).toUpperCase() + "\n\n" + String(m.text ?? "")).join("\n\n"),
);
console.log(
  "OUTCOME " + outcome + " score=" + (score ?? "?") + "/10 passed=" + summary.passed +
    " turns=" + currentTurn + " wall=" + Math.round(wall / 60) + "m chapters=" + chaptersSeen +
    " anomalies=" + anomalies.length,
);
console.log("run dir: " + RUN_DIR);
await browser.close();
process.exit(outcome === "done" ? 0 : 1);
