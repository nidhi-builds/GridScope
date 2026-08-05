import { useCallback, useEffect, useRef, useState } from "react";

export type PollState<T> = { data?: T; updatedAt?: Date; error?: Error; loading: boolean; refresh: () => void };
type InternalPollState<T> = Omit<PollState<T>, "refresh">;

export function useVisiblePolling<T>(load: (signal: AbortSignal) => Promise<T>, intervalMs = 3000): PollState<T> {
  const [state, setState] = useState<InternalPollState<T>>({ loading: true });
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    void load(next.signal).then((data) => {
      if (!next.signal.aborted) setState({ data, updatedAt: new Date(), loading: false });
    }).catch((error: Error) => {
      if (error.name !== "AbortError" && !next.signal.aborted) {
        // The attempt finished, unsuccessfully. Staying in `loading` here left the
        // cold-start failure stuck on the loading panel and made the
        // API-unavailable state unreachable.
        setState((current) => ({ ...current, error, loading: false }));
      }
    });
  }, [load]);

  useEffect(() => {
    const update = () => { if (!document.hidden) refresh(); };
    update();
    document.addEventListener("visibilitychange", update);
    const timer = window.setInterval(update, intervalMs);
    return () => {
      controller.current?.abort();
      document.removeEventListener("visibilitychange", update);
      window.clearInterval(timer);
    };
  }, [intervalMs, refresh]);

  return { ...state, refresh };
}
