import { expect, test } from "@playwright/test";

// The internal words a student must never see: persona directories, graph nodes
// and question ids. The chip bug put "clerk" in the student's own bubble.
const IDENTIFIERS = [
  "clerk",
  "jester",
  "marvin",
  "pirate",
  "sergeant",
  "lesson_step",
  "persona_id",
  "q-01-",
];

const bubbles = ".ui-bubble";

// The backend resumes the signed-in subject's active session, so a shared subject
// makes every picker test depend on no earlier test having started a course. Each
// test signs in under its own subject instead.
let subjectSerial = 0;

test.beforeEach(async ({ page }) => {
  const subject = `e2e-${Date.now()}-${subjectSerial++}`;
  await page.route("**/api/auth/dev/login", (route) =>
    route.continue({ postData: JSON.stringify({ subject }) }),
  );
});

test("a student picks a persona, is taught, and never reads an identifier", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("KI-Führerschein");
  await page.getByRole("button", { name: "Anmelden" }).click();

  await expect(page.getByRole("heading", { name: "KI-Führerschein" })).toBeVisible();
  await expect(page.getByText("Wer soll dich durch den Kurs bringen?")).toBeVisible();
  const cards = page.locator(".pick-card");
  await expect(cards).toHaveCount(5);
  await expect(page.getByText("Enterhaken ja, Datenklau nein.")).toBeVisible();

  await expect(page.locator("html")).toHaveAttribute("data-mode", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-look", "pixel");

  await page.getByRole("button", { name: /Der Freibeuter/ }).click();

  await expect(page.locator(".message--assistant")).toHaveCount(1);
  // Its own turn may span several bubbles, one per paragraph (D91's neighbor).
  // The turn arrives at reading pace (D97); the composer comes back when it is whole.
  const settled = async () => expect(page.locator(".composer-text")).toBeEnabled({ timeout: 20000 });
  await settled();
  const opening = await page.locator(".message--assistant").first().innerText();
  expect(opening.length).toBeGreaterThan(80);
  await expect(page.locator(".message--user")).toHaveCount(0);

  const column = await page.locator(".chat-thread").first().boundingBox();
  expect(column?.width).toBeGreaterThan(700);

  const portrait = await page.locator(".chat-portrait .ui-avatar").boundingBox();
  expect(portrait?.width).toBe(256);

  // A step counts once its question is settled, not when it is taught.
  const bar = page.locator(".course-status [role='progressbar']");
  await expect(bar).toHaveAttribute("aria-valuetext", "Schritt 1 von 6");
  await expect(bar.locator(".ui-cell[data-state='done']")).toHaveCount(0);

  // The step teaches first and checks in; its case comes on the nod (D96).
  const said: string[] = [opening];
  const stepChips = page.locator(".message-choices .ui-chip");
  await expect(stepChips).toHaveCount(0);
  const checkIn = page.getByRole("button", { name: "Ja, weiter" });
  await expect(checkIn).toBeVisible();
  await checkIn.click();
  await expect(page.locator(".message--assistant")).toHaveCount(2);
  await settled();
  await expect(stepChips).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Weiter", exact: true })).toHaveCount(0);
  said.push(await page.locator(".message--assistant").last().innerText());

  // Answering folds the verdict straight into the next step's turn: no card,
  // no Weiter to click (D89).
  await stepChips.first().click();
  await settled();
  await expect(page.locator(".ui-card")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Weiter", exact: true })).toHaveCount(0);
  await expect(page.locator(".message--assistant")).toHaveCount(3);
  // The answered question keeps its grid, in the turn that asked it (D104).
  await expect(page.locator(".message--assistant").nth(1).locator(".message-choices--settled")).toHaveCount(1);
  said.push(await page.locator(".message--assistant").last().innerText());
  await expect(bar).toHaveAttribute("aria-valuetext", "Schritt 2 von 6");
  await expect(bar.locator(".ui-cell[data-state='done']")).toHaveCount(1);

  // A citation a lesson step actually carries: linked, opens in a new tab, titled with its
  // quote. The step's own sources stand with the step, which is the turn that taught it.
  const taughtMessage = page.locator(".message--assistant").first();
  const citation = taughtMessage.locator(".citations-line .citations-ref").first();
  await expect(citation).toBeVisible();
  await expect(citation).toHaveAttribute("target", "_blank");
  await expect(citation).toHaveAttribute("rel", "noreferrer");
  await expect(citation).toHaveAttribute("title", /.+/);
  await expect(citation).toHaveAttribute("href", /.+/);
  const citedRef = (await citation.innerText()).trim();
  expect(citedRef.length).toBeGreaterThan(0);

  // Starting the test is a request, not a "Weiter" click: a real student would type it.
  await page.getByRole("textbox").fill("Ich will jetzt den Test starten.");
  await page.getByRole("button", { name: "Senden" }).click();
  await expect(page.locator(".message--assistant")).toHaveCount(4);
  await settled();
  said.push(await page.locator(".message--assistant").last().innerText());
  expect(new Set(said).size, `said=${JSON.stringify(said)}`).toBe(said.length);

  // The test counts: a confirmation turn stands between the request and the
  // first question.
  await page.getByRole("button", { name: "Ja" }).click();
  await expect(page.locator(".message--assistant")).toHaveCount(5);
  await settled();
  said.push(await page.locator(".message--assistant").last().innerText());
  expect(new Set(said).size, `said=${JSON.stringify(said)}`).toBe(said.length);

  // The frozen draw opens the test with a written question (D128: mainly open
  // questions, guided, no way to fail).
  const chips = page.locator('[data-latest-assistant="true"] .message-choices .ui-chip');
  await expect(chips).toHaveCount(0);
  await expect(page.locator(".composer textarea")).toBeVisible();

  await page.getByRole("textbox").fill("Erlaubt, wenn ich das Ergebnis vorher prüfe.");
  await page.getByRole("button", { name: "Senden" }).click();

  // The typed test request and "Ja" and the typed answer: a picked chip is the
  // answer on screen and draws no bubble of its own (D104), and Weiter never
  // did (D90).
  const mine = page.locator(".message--user");
  await expect(mine).toHaveCount(3);
  await expect(mine.last()).toHaveText("Erlaubt, wenn ich das Ergebnis vorher prüfe.");
  for (const own of await mine.allInnerTexts()) {
    expect(["A", "B", "C", "D"]).not.toContain(own.trim());
  }

  // Grading folds the verdict and the next question into one turn: one more
  // assistant message, carrying a model-answer card. The chapter step earlier
  // carried none of its own (D89), so this is the transcript's first card.
  await expect(page.locator(".message--assistant")).toHaveCount(6);
  await expect(page.locator(".ui-card")).toHaveCount(1);

  // The verdict colours the picked chip's frame: a ring in green, orange or red.
  const picked = page.locator('.message-choices .ui-chip[aria-pressed="true"]');
  await expect(picked.last()).toHaveClass(/chip-verdict--(ok|partial|miss)/, { timeout: 10000 });
  const rings = await picked.evaluateAll((els) =>
    els.map((el) => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineColor]),
  );
  for (const [style, color] of rings) {
    expect(style).toBe("solid");
    expect(["rgb(86, 174, 108)", "rgb(246, 195, 48)", "rgb(222, 60, 55)"]).toContain(color);
  }

  const transcript = (await page.locator(bubbles).allInnerTexts()).join("\n").toLowerCase();
  for (const identifier of IDENTIFIERS) {
    expect(transcript, `transcript leaks ${identifier}`).not.toContain(identifier);
  }

  // A reload replays the whole thread from the backend: an earlier message's
  // citation is still there, not just the newest turn's.
  await page.reload();
  // The reload replays the thread at typing pace; the beats need more than the
  // default five seconds before all six turns stand.
  await expect(page.locator(".message--assistant")).toHaveCount(6, { timeout: 20000 });
  const secondMessageAfterReload = page.locator(".message--assistant").first();
  const citationAfterReload = secondMessageAfterReload.locator(".citations-line .citations-ref").first();
  await expect(citationAfterReload).toHaveText(citedRef);

  // "Neu starten" asks first, only leaving for the picker once confirmed.
  await page.getByRole("button", { name: "Neu starten" }).click();
  await expect(page.getByText("Kurs wirklich von vorn beginnen?")).toBeVisible();
  await page.getByRole("button", { name: "Abbrechen" }).click();
  await expect(page.getByText("Kurs wirklich von vorn beginnen?")).toHaveCount(0);
  await expect(page.locator(bubbles).first()).toBeVisible();

  await page.getByRole("button", { name: "Neu starten" }).click();
  await page.getByRole("button", { name: "Ja, von vorn" }).click();
  await expect(page.getByText("Wer soll dich durch den Kurs bringen?")).toBeVisible();
  await expect(cards).toHaveCount(5);
});

test("light mode gives the text on the scene a halo, dark mode keeps the scrim", async ({ page }) => {
  // The bright rooms carry nothing over the art (D98), so text floating directly
  // on the scene draws its own separation: an outline in the page colour.
  await page.addInitScript(() => window.localStorage.setItem("mode", "light"));
  await page.goto("/");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { name: "KI-Führerschein" })).toBeVisible();

  const shadow = (selector: string) =>
    page.locator(selector).first().evaluate((el) => getComputedStyle(el).textShadow);
  for (const selector of [".pick-title", ".pick-subtitle", ".pick-lead", ".pick-note"]) {
    expect(await shadow(selector)).not.toBe("none");
  }

  await page.getByRole("button", { name: /Der Freibeuter/ }).click();
  await expect(page.locator(bubbles).first()).toBeVisible();
  expect(await shadow(".course-status")).not.toBe("none");
  expect(await shadow(".citations-line")).not.toBe("none");

  // Dark mode never needed one: the scrim over the scene does this work.
  await page.getByRole("button", { name: "Dunkel" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-mode", "dark");
  expect(await shadow(".course-status")).toBe("none");
});

test("the narrow layout fits a 420px phone without overflow", async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await page.getByRole("button", { name: /Der Freibeuter/ }).click();
  await expect(page.locator(".chat-portrait")).toBeVisible();
  await expect(page.locator(bubbles).first()).toBeVisible();

  // The app bar's tools collapse to icon-only; the label stays for screen
  // readers via aria-label, but its text must not render.
  for (const label of ["Klar", "Hell", "Abmelden"]) {
    const button = page.getByRole("button", { name: label });
    await expect(button).toBeVisible();
    await expect(button.locator(".app-tool-label")).toBeHidden();
  }

  const layout = await page.evaluate(() => {
    const choices = document.querySelector(".message-choices");
    return {
      scrollWidth: document.documentElement.scrollWidth,
      appBarScrollWidth: document.querySelector(".app-bar")?.scrollWidth,
      chatFootHeight: document.querySelector(".chat-foot")?.getBoundingClientRect().height,
      choicesHeight: choices?.getBoundingClientRect().height,
      choicesScrollHeight: choices?.scrollHeight,
      scrollHeight: document.querySelector(".chat-scroll")?.getBoundingClientRect().height,
    };
  });
  expect(layout.scrollWidth).toBe(420);
  expect(layout.appBarScrollWidth).toBe(420);
  // Wave 7 moved the option grid out of the foot and into the scrolling thread
  // (D73 amended), dropping its old height cap: a long label wraps to two lines
  // on a phone, so the grid's own rendered height must match its full content
  // height (scrollHeight) rather than being clipped to some fixed budget.
  expect(layout.choicesHeight).toBe(layout.choicesScrollHeight);
  // The disclaimer moved to the persona picker (it is a one-time notice, not a
  // per-chat one), so the foot now only carries the portrait, status row and
  // composer: 128px portrait + 20px frame chrome + 4px margin, status row 28,
  // composer ~40 (line-prose driven), one 4px gap, 8px bottom padding and
  // border, with a margin for a wrapped status row.
  expect(layout.chatFootHeight).toBeLessThan(340);
  // The foot no longer halves the pane, so the reading area is well past the old
  // (foot-with-choices) floor of 360.
  expect(layout.scrollHeight).toBeGreaterThan(480);
});

test(
  "a guest on a spent pool reads the notice above a locked composer, in both languages",
  { tag: "@budget" },
  async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Demo: Der Verlauf wird nach sechs Stunden gelöscht.")).toBeVisible();
    await page.getByRole("button", { name: "Demo starten" }).click();
    await page.getByRole("button", { name: /Der Freibeuter/ }).click();

    const notice = page.locator(".ui-notice");
    await expect(notice).toBeVisible();
    await expect(notice.getByRole("heading", { name: "Großer Andrang" })).toBeVisible();
    await expect(notice).toContainText("Das Demo-Guthaben für heute ist aufgebraucht.");
    await expect(notice).toContainText(/Weiter in \d+ Std\. \d+ Min\. \d+ Sek\./);
    const zone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
    await expect(notice).toContainText(`(${zone})`);
    await expect(page.getByRole("textbox")).toBeDisabled();
    // the opening is a model call too: it waits for the budget
    await expect(page.locator(".message--assistant")).toHaveCount(0);

    await page.getByRole("button", { name: "English" }).click();
    await expect(notice.getByRole("heading", { name: "High demand" })).toBeVisible();
    await expect(notice).toContainText("Today's demo budget is used up.");
    await expect(notice).toContainText(/Resets in \d+ h \d+ min \d+ s/);
    await expect(notice).toContainText(`(${zone})`);
    await expect(page.getByRole("textbox")).toBeDisabled();
  },
);

test("the flag in the app bar switches the student to English and back", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("button", { name: "Abmelden" })).toBeVisible();

  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveTitle("AI drivers license");

  await page.getByRole("button", { name: "Deutsch" }).click();
  await expect(page.getByRole("button", { name: "Abmelden" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
  await expect(page).toHaveTitle("KI-Führerschein");
});

test("the readable setting reaches the app bar, the picker and the composer", async ({ page }) => {
  // Every text, labels included, reads in the reading font under "Lesbar" (D140).
  await page.addInitScript(() => window.localStorage.setItem("text", "plain"));
  await page.goto("/");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { name: "KI-Führerschein" })).toBeVisible();

  const family = (selector: string) =>
    page.locator(selector).first().evaluate((el) => getComputedStyle(el).fontFamily);
  for (const selector of [".app-title", ".app-tool-label", ".pick-title", ".pick-name"]) {
    expect(await family(selector), selector).not.toContain("Tiny5");
  }

  await page.getByRole("button", { name: /Der Freibeuter/ }).click();
  await expect(page.locator(bubbles).first()).toBeVisible();
  for (const selector of [".course-status", ".composer-row .ui-button"]) {
    expect(await family(selector), selector).not.toContain("Tiny5");
  }

  await page.getByRole("button", { name: "Pixelschrift" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-text", "pixel");
  expect(await family(".app-title")).toContain("Tiny5");
});
