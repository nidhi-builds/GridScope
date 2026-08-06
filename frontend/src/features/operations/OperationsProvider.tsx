import { createContext, useCallback, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { loadOperations } from "../../api/client";
import type { FeatureCollection, IncidentSummary, OperationsData } from "../../api/types";
import { useVisiblePolling, type PollState } from "../../api/polling";
import { useLocation, setQuery } from "../../navigation";
import { emptyFilters, filterIncidents, hasActiveFilters, type Filters } from "./IncidentFilters";
import { useNetworkGeometry } from "./useNetworkGeometry";

type OperationsContext = PollState<OperationsData> & {
  selectedIncidentId?: string;
  selected?: IncidentSummary;
  select: (incidentId?: string) => void;
  filters: Filters;
  setFilters: (filters: Filters) => void;
  resetQueue: () => void;
  canResetQueue: boolean;
  incidents: IncidentSummary[];
  overview: FeatureCollection;
};

const Context = createContext<OperationsContext | undefined>(undefined);

/**
 * Mounted above the route switch so the incident queue, the poll, the filters,
 * the map geometry cache and the selection all survive moving between tabs.
 * Previously each route owned its own poll and its own selection, and both died
 * on navigation.
 *
 * Selection lives in `?incident=`, not in React state, so it also survives a
 * hard reload and can be linked to — the simulator has always emitted
 * `/operations?incident=...` links, and until now nothing read them.
 */
export function OperationsProvider({ children }: PropsWithChildren) {
  const load = useCallback((signal: AbortSignal) => loadOperations(signal), []);
  const poll = useVisiblePolling(load);
  const { query } = useLocation();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const selectedIncidentId = query.get("incident") ?? undefined;
  const select = useCallback((incidentId?: string) => setQuery("incident", incidentId), []);
  // Optional all the way down: this provider wraps every route, so a partial or
  // malformed payload here would otherwise white-screen the whole application
  // rather than degrading one panel.
  const selected = poll.data?.incidents?.items?.find(({ id }) => id === selectedIncidentId);
  const incidents = useMemo(
    () => filterIncidents(
      poll.data?.incidents?.items ?? [],
      filters,
      new Set(poll.data?.planned?.items?.flatMap(({ incident_id }) => incident_id ? [incident_id] : []) ?? []),
    ),
    [poll.data, filters],
  );
  const overview = useNetworkGeometry(incidents);
  // Reset clears the *view* — filters and selection — and never the incidents
  // themselves. Wiping real tickets from an operator console is not a button.
  const resetQueue = useCallback(() => { setFilters(emptyFilters); select(undefined); }, [select]);
  const canResetQueue = hasActiveFilters(filters) || Boolean(selectedIncidentId);
  const value = useMemo(
    () => ({ ...poll, selectedIncidentId, selected, select, filters, setFilters, resetQueue, canResetQueue, incidents, overview }),
    [poll, selectedIncidentId, selected, select, filters, resetQueue, canResetQueue, incidents, overview],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useOperations(): OperationsContext {
  const context = useContext(Context);
  if (!context) throw new Error("useOperations must be used inside OperationsProvider");
  return context;
}
