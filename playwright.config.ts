import { defineConfig, devices } from "@playwright/test";

/**
 * The suite runs against an already-running stack (`docker compose up`), never a
 * server Playwright starts itself, so the measured numbers describe the same
 * image a reviewer runs.
 */
const baseURL = process.env.GRIDSCOPE_BASE_URL ?? "http://web:8000";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./performance/results/playwright-artifacts",
  // Lifecycle assertions wait on real telemetry, a 30s stability window, and a
  // 3s poll, so a single spec can legitimately take over a minute.
  timeout: 240_000,
  expect: { timeout: 30_000 },
  // Sequential by design: every spec mutates shared simulator and incident state.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "./performance/results/e2e.json" }]],
  use: {
    baseURL,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
