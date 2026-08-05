import type { PropsWithChildren } from "react";

export function AppShell({ children }: PropsWithChildren) {
  return <div className="app-shell">
    <nav className="icon-rail" aria-label="Primary navigation"><a href="/operations" aria-label="Operations">⌁</a></nav>
    <main>{children}</main>
  </div>;
}
