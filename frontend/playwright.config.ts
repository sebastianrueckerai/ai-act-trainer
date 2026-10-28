import { defineConfig } from "@playwright/test";

// The real API and the built UI, with scripted models so a click path is
// deterministic (D43). The second server is the public demo with its money spent:
// the tests tagged @budget run against it.
export default defineConfig({
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:4173",
    viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 1,
  },
  projects: [
    { name: "app", testDir: "./e2e", grepInvert: /@budget/ },
    {
      name: "budget",
      testDir: "./e2e",
      grep: /@budget/,
      use: { baseURL: "http://localhost:4174" },
    },
    { name: "screens", testDir: "./screenshots" },
  ],
  webServer: [
    {
      command: "cd ../backend && uv run python ../tools/browser_stack.py --port 4173",
      url: "http://localhost:4173/api/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "cd ../backend && uv run python ../tools/browser_stack.py --port 4174",
      env: { BROWSER_STACK_BUDGET: "exhausted" },
      url: "http://localhost:4174/api/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.01 },
  },
});
