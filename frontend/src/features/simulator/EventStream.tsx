import type { SimulatorEvent } from "../../api/types";

const OUTCOMES: Record<string, string> = {
  processed: "accepted", audit_only: "stale replay", quarantined: "quarantined",
  pending: "queued", retry: "retrying",
};

export function EventStream({ events, duplicateAttempts }: { events: SimulatorEvent[]; duplicateAttempts: number }) {
  return <section className="event-stream" aria-label="Generated event stream">
    <h3>Generated events</h3>
    {duplicateAttempts > 0 && <p>{duplicateAttempts} duplicate deliver{duplicateAttempts === 1 ? "y" : "ies"} rejected at ingest</p>}
    {events.length
      ? <table aria-label="Generated events">
        <thead><tr><th>Device time</th><th>Received</th><th>Pole</th><th>Type</th><th>Result</th></tr></thead>
        <tbody>{events.map((event) => <tr key={event.id}>
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
