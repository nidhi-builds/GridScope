import type { SimulatorEvent } from "../../api/types";

const OUTCOMES: Record<string, string> = {
  processed: "accepted", audit_only: "stale replay", quarantined: "quarantined",
  pending: "queued", retry: "retrying",
};

/**
 * Only `power_restored` counts. `heartbeat` and `boot` also carry
 * `energized: true`, but scenarios emit them before any repair — an upstream
 * live anchor, reboot replay, heartbeat noise — so treating them as restoration
 * painted the stream green while the fault was still live. Green here means one
 * thing: this pole has power back after being dark.
 */
export function restoredPoles(events: SimulatorEvent[], repaired: boolean): { poleId: string; at: string; accepted: boolean }[] {
  if (!repaired) return [];
  const seen = new Map<string, { poleId: string; at: string; accepted: boolean }>();
  for (const event of events) {
    if (event.event_type !== "power_restored" || !event.pole_id) continue;
    if (!seen.has(event.pole_id)) {
      seen.set(event.pole_id, { poleId: event.pole_id, at: event.received_at, accepted: event.processing_state === "processed" });
    }
  }
  return [...seen.values()];
}

export function EventStream({ events, duplicateAttempts, repaired = false }: { events: SimulatorEvent[]; duplicateAttempts: number; repaired?: boolean }) {
  const restored = restoredPoles(events, repaired);
  const restoredIds = new Set(restored.length ? events.filter((event) => event.event_type === "power_restored").map((event) => event.id) : []);
  return <section className="event-stream" aria-label="Generated event stream">
    <h3>Generated events</h3>
    {duplicateAttempts > 0 && <p>{duplicateAttempts} duplicate deliver{duplicateAttempts === 1 ? "y" : "ies"} rejected at ingest</p>}

    {/* The proof that restoration is telemetry-driven. Without naming these
        events, the only visible evidence that a repaired pole reported back is
        the ticket quietly closing itself. */}
    {restored.length > 0 && <div className="restoration-proof" aria-label="Restoration telemetry">
      <strong>{restored.length} pole{restored.length === 1 ? "" : "s"} reported power back after the repair</strong>
      <ul>{restored.map(({ poleId, at, accepted }) => <li key={poleId}>
        <code>{poleId}</code> — power_restored at {at} · {accepted ? "accepted by ingest" : "not accepted"}
      </li>)}</ul>
      <p>The ticket closes on these events, not on the crew's report.</p>
    </div>}

    {events.length
      ? <table aria-label="Generated events">
        <thead><tr><th>Device time</th><th>Received</th><th>Pole</th><th>Type</th><th>Result</th></tr></thead>
        <tbody>{events.map((event) => <tr key={event.id} className={restoredIds.has(event.id) ? "event-restored" : undefined}>
          <td>{event.device_time}</td>
          <td>{event.received_at}</td>
          <td>{event.pole_id ?? "unknown"}</td>
          <td>{event.event_type}</td>
          <td>{OUTCOMES[event.processing_state] ?? event.processing_state}</td>
        </tr>)}</tbody>
      </table>
      : <p>This scenario generated no accepted events.</p>}
  </section>;
}
