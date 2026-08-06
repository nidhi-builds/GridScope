import { useEffect, useState } from "react";

/**
 * Client-side navigation, without a router dependency.
 *
 * Every route used to be a plain `<a href>`, so switching tabs was a full page
 * load: the incident queue, the selected ticket, the map geometry cache and the
 * simulator run were all discarded and refetched. Routes now swap in place, so
 * in-memory state survives moving between them.
 */
export type Location = { path: string; query: URLSearchParams };

const read = (): Location => typeof window === "undefined"
  ? { path: "/operations", query: new URLSearchParams() }
  : { path: window.location.pathname, query: new URLSearchParams(window.location.search) };

const LISTENERS = new Set<() => void>();
const announce = () => LISTENERS.forEach((listener) => listener());

/** Push a new route. `replace` avoids stacking history entries for selection
 * changes, so Back leaves the workspace rather than stepping through clicks. */
export function navigate(path: string, query?: URLSearchParams, replace = false): void {
  if (typeof window === "undefined") return;
  const search = query?.toString();
  const url = `${path}${search ? `?${search}` : ""}`;
  window.history[replace ? "replaceState" : "pushState"]({}, "", url);
  announce();
}

/** Update only the query string, keeping the current route. */
export function setQuery(key: string, value: string | undefined, replace = true): void {
  if (typeof window === "undefined") return;
  const query = new URLSearchParams(window.location.search);
  if (value) query.set(key, value); else query.delete(key);
  navigate(window.location.pathname, query, replace);
}

export function useLocation(): Location {
  const [location, setLocation] = useState<Location>(read);
  useEffect(() => {
    const update = () => setLocation(read());
    LISTENERS.add(update);
    window.addEventListener("popstate", update);
    return () => { LISTENERS.delete(update); window.removeEventListener("popstate", update); };
  }, []);
  return location;
}

/**
 * Intercept a link click, unless the person is asking the browser for a new tab
 * or window. Middle-click, ctrl/cmd-click and shift-click must keep working.
 */
type LinkClick = { defaultPrevented: boolean; button: number; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean; preventDefault: () => void };

export function interceptNavigation(event: LinkClick, href: string): void {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  const [path, search] = href.split("?");
  navigate(path, search ? new URLSearchParams(search) : undefined);
}
