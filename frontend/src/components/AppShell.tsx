import type { PropsWithChildren } from "react";

const LINKS = [
  { href: "/operations", icon: "⌁", label: "Operations" },
  { href: "/planned-operations", icon: "▤", label: "Planned operations" },
  { href: "/device-health", icon: "◉", label: "Device health" },
  { href: "/system-health", icon: "✚", label: "System health" },
  { href: "/simulator", icon: "▶", label: "Simulator (demo)" },
];

export function AppShell({ children }: PropsWithChildren) {
  const current = typeof window === "undefined" ? "/operations" : window.location.pathname;
  return <div className="app-shell">
    <nav className="icon-rail" aria-label="Primary navigation">{LINKS.map(({ href, icon, label }) => (
      <a key={href} href={href} aria-label={label} aria-current={current === href ? "page" : undefined}>
        <span aria-hidden="true">{icon}</span><span className="rail-label">{label}</span>
      </a>
    ))}</nav>
    <main>{children}</main>
  </div>;
}
