import { expect, test } from "@playwright/test";
import { countIncidents, incidentDetail, recordMetrics, resetSimulator, selectIncident, startScenario } from "./helpers";

const negatives: Record<string, number> = {};

test.describe.configure({ mode: "serial" });

test("three simultaneous branch faults stay three separate incidents", async ({ page, request }) => {
  await resetSimulator(request);
  const run = await startScenario(request, "three_branch_faults");

  expect(run.expected.incident_count).toBe(3);
  expect(run.incident_ids).toHaveLength(3);

  await page.goto("/operations");
  const queue = page.getByRole("table", { name: "Incident queue" });
  await expect(queue.locator("tbody tr")).toHaveCount(3);
  for (const incidentId of run.incident_ids) {
    await expect(page.getByRole("button", { name: incidentId, exact: true })).toBeVisible();
  }
});

test("device death raises no fault ticket", async ({ request }) => {
  await resetSimulator(request);
  const before = await countIncidents(request);
  const run = await startScenario(request, "device_death");

  expect(run.expected.incident_count).toBe(0);
  expect(run.incident_ids).toHaveLength(0);
  expect(await countIncidents(request)).toBe(before);
  negatives.device_death = run.incident_ids.length;
});

test("a matched planned outage raises no fault ticket and stays in planned operations", async ({ page, request }) => {
  await resetSimulator(request);
  const before = await countIncidents(request);
  const run = await startScenario(request, "planned_outage");

  expect(run.incident_ids).toHaveLength(0);
  expect(await countIncidents(request)).toBe(before);
  negatives.planned_outage = run.incident_ids.length;

  await page.goto("/planned-operations");
  await expect(page.getByText(/Planned work is not a fault ticket/)).toBeVisible();
});

test("stale delivery and reboot replay raise no fault ticket", async ({ request }) => {
  await resetSimulator(request);
  const before = await countIncidents(request);

  for (const scenario of ["reboot_replay", "transport_noise", "noise_baseline"]) {
    const run = await startScenario(request, scenario);
    expect(run.incident_ids, `${scenario} must not open a ticket`).toHaveLength(0);
    negatives[scenario] = run.incident_ids.length;
  }
  expect(await countIncidents(request)).toBe(before);
});

test("repair reported while poles are still dark is rejected with operator-safe wording", async ({ page, request }) => {
  await resetSimulator(request);
  const run = await startScenario(request, "known_span");
  const incidentId = run.incident_ids[0];

  const detail = await selectIncident(page, incidentId);
  await detail.getByRole("button", { name: "Acknowledge" }).click();
  await expect(detail).toContainText("acknowledged");
  await detail.getByRole("button", { name: "Assign crew" }).click();
  await expect(detail).toContainText("crew assigned");

  // No repair telemetry has arrived, so restoration must not be accepted.
  await detail.getByRole("button", { name: "Report repair" }).click();
  await expect(detail.getByRole("alert")).toContainText(/still reporting dark/);

  const facts = await incidentDetail(request, incidentId);
  expect(facts.status).toBe("crew_assigned");
});

test("weak inferred topology localizes to a corridor and says the count is estimated", async ({ page, request }) => {
  await resetSimulator(request);
  const run = await startScenario(request, "weak_inferred");
  const incidentId = run.incident_ids[0];
  const facts = await incidentDetail(request, incidentId);

  expect(facts.fault_class).toBe("corridor");
  expect(facts.topology.source).toBe("inferred");
  expect(facts.affected_count_estimated).toBe(true);
  expect(["medium", "low"]).toContain(facts.confidence.level);

  const detail = await selectIncident(page, incidentId);
  await expect(detail).toContainText("Search corridor");
  await expect(detail).toContainText("estimated");
  await expect(detail).toContainText(/uninstrumented poles between/);
});

test("an unavailable API shows a state panel instead of an empty console", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.abort("failed"));
  await page.goto("/operations");

  await expect(page.getByText(/API unavailable|Starting GridScope/)).toBeVisible();
  await expect(page.getByRole("table", { name: "Incident queue" })).toHaveCount(0);
});

test("a transient API failure keeps the last good data and marks it stale", async ({ page, request }) => {
  await resetSimulator(request);
  const run = await startScenario(request, "known_span");
  const incidentId = run.incident_ids[0];

  await page.goto("/operations");
  await expect(page.getByRole("button", { name: incidentId, exact: true })).toBeVisible();

  await page.route("**/api/v1/ready", (route) => route.abort("failed"));
  await expect(page.getByText("Live updates paused")).toBeVisible({ timeout: 30_000 });
  // The operator keeps seeing the last valid incident rather than an empty queue.
  await expect(page.getByRole("button", { name: incidentId, exact: true })).toBeVisible();
});

test("the console stays usable in a narrow reviewer viewport", async ({ page, request }) => {
  await resetSimulator(request);
  const run = await startScenario(request, "known_span");
  const incidentId = run.incident_ids[0];

  await page.setViewportSize({ width: 390, height: 780 });
  await page.goto("/operations");

  const button = page.getByRole("button", { name: incidentId, exact: true });
  await expect(button).toBeVisible();

  // Nothing may overflow the viewport horizontally.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  // Navigation stays reachable, with icons standing in for the full labels.
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Simulator (demo)" })).toHaveCount(1);

  recordMetrics("negative-cases.json", {
    zero_ticket_scenarios: negatives,
    false_ticket_count: Object.values(negatives).reduce((sum, count) => sum + count, 0),
    narrow_viewport_overflow_px: overflow,
  });
});
