import { Component, type ErrorInfo, type PropsWithChildren } from "react";

/**
 * Last line of defence for the console.
 *
 * Three separate crashes in this codebase came from reading a field that a
 * malformed or partial API payload did not carry, and each one unmounted the
 * whole application: queue, map and status bar together. Each specific case is
 * now guarded, but an operator staring at a blank white page during an outage is
 * a bad enough failure that it deserves a general catch as well.
 */
export class ErrorBoundary extends Component<PropsWithChildren, { error?: Error }> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("GridScope console error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <div className="state-panel" role="alert">
      <h2>The console hit an unexpected error</h2>
      <p>Incident data is unaffected — this is a display fault. Reload to continue.</p>
      <button type="button" onClick={() => window.location.reload()}>Reload console</button>
    </div>;
  }
}
