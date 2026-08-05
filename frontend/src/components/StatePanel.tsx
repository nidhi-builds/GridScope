import type { ReactNode } from "react";

export function StatePanel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="state-panel" aria-live="polite"><h2>{title}</h2><p>{children}</p></section>;
}
