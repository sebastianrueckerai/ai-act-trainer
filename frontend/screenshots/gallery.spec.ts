import { expect, test, type Page } from "@playwright/test";
import { GALLERY_SECTIONS } from "../src/gallery/sections";
import { contrastRatio } from "../src/theme/palette";

// The gallery renders every column at once, so a column is addressed by look,
// mode and text face. Both modes are shot: one sprite set has to carry both
// (D42). The plain-text pixel column is the odd one out (D91), so it keeps its
// own filename suffix instead of renaming the four settled baselines.
const COLUMNS = [
  ["pixel", "dark", "pixel"],
  ["clean", "dark", "pixel"],
  ["pixel", "light", "pixel"],
  ["clean", "light", "pixel"],
  ["pixel", "dark", "plain"],
] as const;

async function shoot(
  page: Page,
  section: string,
  look: string,
  mode: string,
  text: string,
): Promise<void> {
  await page.goto("/gallery");
  const target = page.locator(
    `main [data-look='${look}'][data-mode='${mode}'][data-text='${text}'] [data-gallery='${section}']`,
  );
  await target.waitFor();
  await page.evaluate(async () => {
    await document.fonts.ready;
    document.documentElement.setAttribute("data-freeze", "");
  });
  const suffix = text === "plain" ? `-${text}` : "";
  await expect(target).toHaveScreenshot(`${section}-${look}-${mode}${suffix}.png`);
}

for (const [look, mode, text] of COLUMNS) {
  for (const section of GALLERY_SECTIONS) {
    test(`gallery ${section} in ${look} ${mode} ${text}`, async ({ page }) => {
      await shoot(page, section, look, mode, text);
    });
  }
}

// The clean look draws no pixel icons beside a label; a button that has nothing but
// its icon keeps it, or it is an empty circle.
test("an icon-only button keeps its glyph in the clean look", async ({ page }) => {
  await page.goto("/gallery");
  for (const mode of ["dark", "light"]) {
    const icon = page.locator(
      `main [data-look='clean'][data-mode='${mode}'][data-text='pixel'] .chat-jump .ui-icon`,
    );
    await expect(icon).toBeVisible();
  }
});

// The readable setting covers every text, labels included (D140): a button, a
// badge, the status row and a card title read in the reading font, and only
// the pixel text keeps Tiny5.
test("the readable setting sets the labels in the reading font too", async ({ page }) => {
  await page.goto("/gallery");
  const family = (text: string, selector: string) =>
    page
      .locator(`main [data-look='pixel'][data-mode='dark'][data-text='${text}'] ${selector}`)
      .first()
      .evaluate((el) => getComputedStyle(el).fontFamily);
  for (const selector of [".ui-button", ".ui-badge", ".course-status", ".ui-card-title"]) {
    expect(await family("plain", selector), selector).not.toContain("Tiny5");
    expect(await family("pixel", selector), selector).toContain("Tiny5");
  }
});

// The pixel text marks the closing question in the accent alone (D86), so it has
// to read as text in both rooms (D142): WCAG AA, 4.5:1.
test("the closing question reads in both modes", async ({ page }) => {
  await page.goto("/gallery");
  const hex = (css: string) =>
    `#${css
      .match(/\d+/g)!
      .slice(0, 3)
      .map((n) => Number(n).toString(16).padStart(2, "0"))
      .join("")}`;
  for (const mode of ["dark", "light"]) {
    const [text, fill] = await page
      .locator(`main [data-look='pixel'][data-mode='${mode}'][data-text='pixel'] .ui-bubble--question`)
      .first()
      .evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]);
    expect(contrastRatio(hex(text), hex(fill)), mode).toBeGreaterThanOrEqual(4.5);
  }
});
