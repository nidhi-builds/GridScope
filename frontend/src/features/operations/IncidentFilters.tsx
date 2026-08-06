import type { IncidentSummary } from "../../api/types";

export type Filters = { status: string; faultClass: string; confidence: string; feeder: string; transformer: string; planned: string };
export const emptyFilters: Filters = { status: "", faultClass: "", confidence: "", feeder: "", transformer: "", planned: "" };

export function filterIncidents(incidents: IncidentSummary[], filters: Filters, plannedIncidentIds = new Set<string>()): IncidentSummary[] {
  return incidents.filter((incident) =>
    (!filters.status || incident.status === filters.status) &&
    (!filters.faultClass || incident.fault_class === filters.faultClass) &&
    (!filters.confidence || incident.confidence.level === filters.confidence) &&
    (!filters.feeder || incident.feeder_id === filters.feeder) &&
    (!filters.transformer || incident.transformer_id === filters.transformer) &&
    (!filters.planned || plannedIncidentIds.has(incident.id)),
  );
}

export const hasActiveFilters = (filters: Filters): boolean => Object.values(filters).some(Boolean);

export function IncidentFilters({ incidents, filters, onChange, onReset, canReset }: { incidents: IncidentSummary[]; filters: Filters; onChange: (filters: Filters) => void; onReset?: () => void; canReset?: boolean }) {
  const options = (key: keyof Filters, values: Array<string | null>, label: string) => <label>{label}<select aria-label={label} value={filters[key]} onChange={(event) => onChange({ ...filters, [key]: event.target.value })}><option value="">All</option>{[...new Set(values.filter(Boolean) as string[])].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>;
  return <div className="filters" aria-label="Incident filters">
    {options("status", incidents.map(({ status }) => status), "Status")}
    {options("faultClass", incidents.map(({ fault_class }) => fault_class), "Class")}
    {options("confidence", incidents.map(({ confidence }) => confidence.level), "Confidence")}
    {options("feeder", incidents.map(({ feeder_id }) => feeder_id), "Feeder")}
    {options("transformer", incidents.map(({ transformer_id }) => transformer_id), "DT")}
    <label>Planned<select aria-label="Planned" value={filters.planned} onChange={(event) => onChange({ ...filters, planned: event.target.value })}><option value="">All</option><option value="linked">Associated</option></select></label>
    {/* Clears the view, not the data: filters and the selected ticket go back to
        default so the full queue is visible again. No incident is touched. */}
    <button type="button" className="reset-queue" onClick={onReset} disabled={!canReset}>Reset queue view</button>
  </div>;
}
