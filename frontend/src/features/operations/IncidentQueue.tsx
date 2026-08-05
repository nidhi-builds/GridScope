import type { IncidentSummary } from "../../api/types";

export function sortIncidents(incidents: IncidentSummary[]): IncidentSummary[] {
  return [...incidents].sort((left, right) => {
    const priority = Number(right.status === "detected") - Number(left.status === "detected");
    return priority || right.affected_count - left.affected_count || Date.parse(right.updated_at) - Date.parse(left.updated_at);
  });
}

export function IncidentQueue({ incidents, selectedIncidentId, onSelect }: { incidents: IncidentSummary[]; selectedIncidentId?: string; onSelect: (id: string) => void }) {
  return <section className="incident-queue"><h2>Incident queue</h2><table aria-label="Incident queue"><thead><tr><th>Incident</th><th>Status</th><th>Affected</th></tr></thead><tbody>{sortIncidents(incidents).map((incident) => <tr key={incident.id} aria-current={incident.id === selectedIncidentId || undefined}><td><button onClick={() => onSelect(incident.id)}>{incident.id}</button><small>{incident.fault_class} · {incident.confidence.level}</small></td><td>{incident.status === "detected" ? "Unacknowledged" : incident.status}</td><td>{incident.affected_count}</td></tr>)}</tbody></table></section>;
}
