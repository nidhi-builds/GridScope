import { useEffect, useRef, useState } from "react";
import { loadIncidentGeometry } from "../../api/client";
import type { FeatureCollection, IncidentSummary } from "../../api/types";

/** Concurrent geometry fetches. The queue can hold 100 incidents; firing all of
 * them at once starves the poll that keeps the workspace live. */
const CONCURRENCY = 6;
const CACHE_LIMIT = 300;

const empty: FeatureCollection = { type: "FeatureCollection", features: [] };

/**
 * Geometry for the whole visible queue, so the map shows the network instead of
 * an empty basemap until something is clicked.
 *
 * An incident's geometry only changes when the incident does, so results are
 * cached on `id + updated_at`. A re-poll that returns the same incidents costs
 * no requests, and the map does not flicker while they resolve. Incidents are
 * published as they arrive rather than in one batch at the end.
 */
export function useNetworkGeometry(incidents: IncidentSummary[]): FeatureCollection {
  const cache = useRef(new Map<string, FeatureCollection>());
  const [collection, setCollection] = useState<FeatureCollection>(empty);
  const wanted = incidents.map((incident) => ({ incident, key: `${incident.id}:${incident.updated_at}` }));
  const signature = wanted.map(({ key }) => key).join(",");

  useEffect(() => {
    const controller = new AbortController();
    const publish = () => {
      if (controller.signal.aborted) return;
      setCollection({ type: "FeatureCollection", features: wanted.flatMap(({ key }) => cache.current.get(key)?.features ?? []) });
    };
    publish();

    const missing = wanted.filter(({ key }) => !cache.current.has(key));
    let next = 0;
    const worker = async () => {
      while (next < missing.length && !controller.signal.aborted) {
        const { incident, key } = missing[next++];
        try {
          cache.current.set(key, await loadIncidentGeometry(incident.id, controller.signal));
          publish();
        } catch {
          // One incident without geometry must not blank the rest of the map.
        }
      }
    };
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, missing.length) }, worker));

    if (cache.current.size > CACHE_LIMIT) {
      const live = new Set(wanted.map(({ key }) => key));
      for (const key of cache.current.keys()) if (!live.has(key)) cache.current.delete(key);
    }
    return () => controller.abort();
    // `signature` encodes every id and updated_at in `wanted`; re-running on the
    // array identity alone would refetch on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  return collection;
}
