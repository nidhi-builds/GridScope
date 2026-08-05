import { expect, test } from "@playwright/test";
import { percentile, recordMetrics, resetSimulator, startScenario } from "./helpers";

const SAMPLES = 20;
const TARGET_SECONDS = 2;

/**
 * Incident-list responsiveness with real incidents present. Timing is taken in
 * the browser, from navigation start to the queue actually being painted, so it
 * includes API latency, React render, and the map, not just the API call.
 */
test("incident list stays under the 2s p95 target with a populated queue", async ({ page, request }) => {
  await resetSimulator(request);
  await startScenario(request, "three_branch_faults");
  await startScenario(request, "known_span", 20260804);

  const queue = page.getByRole("table", { name: "Incident queue" });
  const durations: number[] = [];

  for (let sample = 0; sample < SAMPLES; sample += 1) {
    const startedAt = Date.now();
    await page.goto("/operations");
    await queue.locator("tbody tr").first().waitFor({ state: "visible" });
    durations.push((Date.now() - startedAt) / 1000);
  }

  const p50 = percentile(durations, 0.5);
  const p95 = percentile(durations, 0.95);

  recordMetrics("ui-load.json", {
    route: "/operations",
    samples: SAMPLES,
    target_p95_seconds: TARGET_SECONDS,
    p50_seconds: p50,
    p95_seconds: p95,
    max_seconds: Math.max(...durations),
    durations_seconds: durations,
    within_target: p95 < TARGET_SECONDS,
  });

  expect(p95).toBeLessThan(TARGET_SECONDS);
});

test("the simulator and health routes load without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  page.on("pageerror", (error) => errors.push(error.message));

  for (const route of ["/simulator", "/planned-operations", "/device-health", "/system-health"]) {
    await page.goto(route);
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
  }

  await expect(page.getByText(/Demo view/)).toHaveCount(0);
  expect(errors, `console errors: ${errors.join(" | ")}`).toHaveLength(0);
});
