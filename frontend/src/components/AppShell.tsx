import type { PropsWithChildren } from "react";
import { interceptNavigation, useLocation } from "../navigation";

const LINKS = [
  { href: "/operations", icon: "⌁", label: "Operations" },
  { href: "/planned-operations", icon: "▤", label: "Planned operations" },
  { href: "/device-health", icon: "◉", label: "Device health" },
  { href: "/system-health", icon: "✚", label: "System health" },
  { href: "/simulator", icon: "▶", label: "Simulator (demo)" },
];

export function AppShell({ children }: PropsWithChildren) {
  const { path, query } = useLocation();
  const current = path === "/" ? "/operations" : path;
  // Carry the selected incident across tabs, so moving to the simulator to
  // repair a fault does not lose the ticket you were looking at.
  const incident = query.get("incident");
  return <div className="app-shell">
    <nav className="icon-rail" aria-label="Primary navigation">{LINKS.map(({ href, icon, label }) => {
      const target = incident ? `${href}?incident=${encodeURIComponent(incident)}` : href;
      return <a key={href} href={target} aria-label={label} aria-current={current === href ? "page" : undefined}
        onClick={(event) => interceptNavigation(event, target)}>
        <span aria-hidden="true">{icon}</span><span className="rail-label">{label}</span>
      </a>;
    })}</nav>
    <main>{children}</main>
  </div>;
}
