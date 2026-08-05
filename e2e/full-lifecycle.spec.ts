import { expect, test } from "@playwright/test";
import { incidentDetail, recordMetrics, repairRun, resetSimulator, selectIncident, startScenario } from "./helpers";

/**
 * The complete operator workflow on the real stack: inject a known span fault,
 * see exactly one localized incident, acknowledge, assign, repair, and wait for
 * telemetry-driven verification. Both lifecycle timings are browser-observed —
 * measured from the moment the fault is injected to the moment an operator can
 * actually see the consequence, not from a server-side field.
 */
test("known span fault runs from injection to telemetry-verified closure", async ({ page, request }) => {
  await resetSimulator(request);

  const injectedAt = Date.now();
  const run = await startScenario(request, "known_span");
  expect(run.expected.incident_count).toBe(1);
  expect(run.incident_ids).toHaveLength(1);
  const incidentId = run.incident_ids[0];

  // Detection: injection until the incident is visible to an operator.
  await page.goto("/operations");
  const queueRow = page.getByRole("button", { name: incidentId, exact: true });
  await expect(queueRow).toBeVisible();
  const detectionSeconds = (Date.now() - injectedAt) / 1000;

  await expect(page.getByRole("table", { name: "Incident queue" }).locator("tbody tr")).toHaveCount(1);

  const detail = await selectIncident(page, incidentId);
  const facts = await incidentDetail(request, incidentId);

  // Localization facts an operator dispatches on.
  expect(facts.fault_class).toBe("span");
  expect(facts.boundary.kind).toBe("span");
  expect(facts.affected_count).toBeGreaterThan(0);
  expect(["high", "medium", "low"]).toContain(facts.confidence.level);
  expect(typeof facts.navigation.latitude).toBe("number");
  expect(typeof facts.navigation.longitude).toBe("number");

  await expect(detail).toContainText(incidentId);
  await expect(detail).toContainText(`${facts.affected_count}`);
  await expect(detail).toContainText(facts.confidence.level);
  await expect(detail).toContainText(`${facts.navigation.latitude}`);
  await expect(detail).toContainText("PIN");
  await expect(detail).toContainText("Ticket history");
  await expect(detail).toContainText("Evidence");

  // No unobserved pole may be presented as confirmed dark.
  const dark = Number(facts.evidence.class_counts.confirmed_dark ?? 0);
  const evidenceTotal = Object.values(facts.evidence.class_counts as Record<string, number>).reduce((sum, count) => sum + count, 0);
  expect(dark).toBeLessThanOrEqual(evidenceTotal);

  await detail.getByRole("button", { name: "Acknowledge" }).click();
  await expect(detail).toContainText("acknowledged");

  await detail.getByRole("button", { name: "Assign crew" }).click();
  await expect(detail).toContainText("crew assigned");

  // Physical repair arrives as ordinary restoration telemetry, not a shortcut.
  const repairedAt = Date.now();
  await repairRun(request, run.id);

  await detail.getByRole("button", { name: "Report repair" }).click();

  // Restoration: repair until the operator can see verified or closed.
  const closed = page.getByRole("table", { name: "Incident queue" })
    .locator("tbody tr", { has: page.getByRole("button", { name: incidentId, exact: true }) });
  await expect(closed).toContainText(/verified|closed/, { timeout: 180_000 });
  const restorationSeconds = (Date.now() - repairedAt) / 1000;

  const final = await incidentDetail(request, incidentId);
  expect(["verified", "closed"]).toContain(final.status);
  expect(final.ticket_events.map((event: { type: string }) => event.type))
    .toEqual(expect.arrayContaining(["acknowledge", "assign_crew", "report_resolved"]));

  recordMetrics("lifecycle.json", {
    scenario: "known_span",
    run_id: run.id,
    incident_id: incidentId,
    detection_seconds: detectionSeconds,
    restoration_seconds: restorationSeconds,
    target_seconds: 120,
    detection_within_target: detectionSeconds < 120,
    restoration_within_target: restorationSeconds < 120,
    final_status: final.status,
    affected_count: final.affected_count,
    confidence: final.confidence.level,
  });

  // The PRD target is p95 < 120s; a single browser run is one sample of it.
  expect(detectionSeconds).toBeLessThan(120);
  expect(restorationSeconds).toBeLessThan(120);
});
