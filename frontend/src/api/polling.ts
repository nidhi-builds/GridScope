import { useCallback, useEffect, useRef, useState } from "react";

export type PollState<T> = { data?: T; updatedAt?: Date; error?: Error; loading: boolean };

export function useVisiblePolling<T>(load: (signal: AbortSignal) => Promise<T>, intervalMs = 3000): PollState<T> {
  const [state, setState] = useState<PollState<T>>({ loading: true });
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    void load(next.signal).then((data) => {
      if (!next.signal.aborted) setState({ data, updatedAt: new Date(), loading: false });
    }).catch((error: Error) => {
      if (error.name !== "AbortError" && !next.signal.aborted) {
        setState((current) => ({ ...current, error, loading: !current.data }));
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

  return state;
}
