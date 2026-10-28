// Drive the real UI one command at a time, so an agent can play a student
// against a running stack and read what the page shows after each step.
//
//   node e2e/drive.mjs --base http://localhost:8000 --subject jo-1 --out /tmp/jo login
//   node e2e/drive.mjs ... pick "Der Freibeuter"
//   node e2e/drive.mjs ... say "was soll ich hier machen"
//   node e2e/drive.mjs ... chip 2
//   node e2e/drive.mjs ... read
//   node e2e/drive.mjs ... click "Neu starten"
//   node e2e/drive.mjs ... link "Öffnen"        # what the file link serves
//   node e2e/drive.mjs --look clean --mode light ... read
//
// Every command signs in as the subject, reloads the page (the backend resumes
// the session), performs the step, waits until the tutor has finished, prints the
// visible state as JSON on stdout and saves a screenshot under --out.

import { chromium } from "@playwright/test";
import { mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
function option(name, fallback) {
  const at = args.indexOf(`--${name}`);
  if (at === -1) return fallback;
  const value = args[at + 1];
  args.splice(at, 2);
  return value;
}
const base = option("base", "http://localhost:8000");
const subject = option("subject", "jo");
const out = option("out", "/tmp/drive");
const viewport = option("viewport", "1280x900").split("x").map(Number);
// the theme lives in local storage, which a fresh context loses: seed it before the page runs
const theme = { look: option("look", ""), mode: option("mode", "") };
const [command, ...rest] = args;
if (!command) {
  console.error("usage: drive.mjs [--base URL] [--subject S] [--out DIR] <login|pick|say|chip|read|click|link|shot> [arg]");
  process.exit(2);
}
mkdirSync(out, { recursive: true });
const step = readdirSync(out).filter((f) => f.endsWith(".png")).length + 1;

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: viewport[0], height: viewport[1] },
  deviceScaleFactor: 1,
  locale: "de-DE",
});
await context.addInitScript((wanted) => {
  for (const [key, value] of Object.entries(wanted)) {
    if (value) window.localStorage.setItem(key, value);
  }
}, theme);
const page = await context.newPage();
const textbox = page.getByRole("textbox");

async function settled() {
  // the composer is disabled while the tutor streams; wait for it to come back
  await textbox.waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForFunction(
    () => !document.querySelector(".composer-text")?.hasAttribute("disabled"),
    null,
    { timeout: 120_000 },
  );
}

async function state() {
  const bubbles = await page.locator(".ui-bubble").evaluateAll((nodes) =>
    nodes.map((n) => ({
      who: n.classList.contains("ui-bubble--user") ? "student" : "tutor",
      text: n.innerText.trim(),
    })),
  );
  const chips = await page.locator(".message-choices button, .composer-row button:not(.composer-send)").allInnerTexts();
  const status = (await page.locator(".course-status").allInnerTexts()).join(" | ");
  const cards = await page.locator(".pick-card").allInnerTexts();
  return { url: page.url(), status, cards, bubbles, chips: chips.map((c) => c.trim()) };
}

async function shot(label) {
  const file = join(out, `${String(step).padStart(2, "0")}-${label}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

async function open() {
  const login = await page.request.post(`${base}/api/auth/dev/login`, { data: { subject } });
  if (!login.ok()) throw new Error(`dev login failed: ${login.status()}`);
  await page.goto(`${base}/`);
  await page.locator(".pick-card, .composer").first().waitFor({ timeout: 30_000 });
  if (await page.locator(".composer").count()) await settled();
}

const started = Date.now();
let result = {};
try {
  await open();
  const t0 = Date.now();
  switch (command) {
    case "login":
    case "read":
      break;
    case "pick": {
      await page.getByRole("button", { name: new RegExp(rest[0]) }).click();
      await settled();
      break;
    }
    case "say": {
      await textbox.fill(rest.join(" "));
      await page.getByRole("button", { name: /^(Senden|Send)$/ }).click();
      await page.waitForFunction(
        () => document.querySelector(".composer-text")?.hasAttribute("disabled"),
        null,
        { timeout: 10_000 },
      ).catch(() => {});
      await settled();
      break;
    }
    case "chip": {
      await page.locator(".message-choices button, .composer-row button:not(.composer-send)").nth(Number(rest[0]) - 1).click();
      await page.waitForTimeout(500);
      await settled();
      break;
    }
    case "click": {
      await page.getByRole("button", { name: new RegExp(rest[0]) }).click();
      await page.waitForTimeout(500);
      if (await page.locator(".composer").count()) await settled();
      break;
    }
    case "link": {
      // a file card opens a PDF in a new tab: report what the link serves
      const href = await page.getByRole("link", { name: new RegExp(rest[0]) }).first().getAttribute("href");
      const target = href.startsWith("http") ? href : `${base}${href}`;
      const response = await page.request.get(target);
      result.link = { href, status: response.status(), type: response.headers()["content-type"] };
      break;
    }
    case "shot":
      break;
    default:
      throw new Error(`unknown command ${command}`);
  }
  // let the last tokens paint before reading and shooting
  await page.waitForTimeout(400);
  result = { ...result, command, arg: rest.join(" "), waitedMs: Date.now() - t0, ...(await state()) };
  result.screenshot = await shot(command);
} catch (error) {
  result = { command, error: String(error), screenshot: await shot("error").catch(() => null) };
} finally {
  result.totalMs = Date.now() - started;
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
}
