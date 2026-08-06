import { useCallback } from "react";
import { loadNetwork } from "../../api/client";
import type { FeatureCollection } from "../../api/types";
import { useVisiblePolling } from "../../api/polling";

/**
 * The live network, polled more slowly than the incident queue.
 *
 * Pole states change on telemetry, not on operator action, and the payload is
 * the whole grid rather than a page of tickets — so refetching it every three
 * seconds alongside the queue would be pure waste. Fifteen seconds keeps the map
 * honest without competing with detection latency for connections.
 */
export function useLiveNetwork(): { network?: FeatureCollection; error?: Error } {
  const load = useCallback((signal: AbortSignal) => loadNetwork(signal), []);
  const { data, error } = useVisiblePolling(load, 15_000);
  return { network: data, error };
}
