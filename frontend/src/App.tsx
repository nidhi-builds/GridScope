import { DeviceHealthPage } from "./features/health/DeviceHealthPage";
import { PlannedOperationsPage } from "./features/health/PlannedOperationsPage";
import { SystemHealthPage } from "./features/health/SystemHealthPage";
import { OperationsPage } from "./features/operations/OperationsPage";
import { OperationsProvider } from "./features/operations/OperationsProvider";
import { SimulatorPage } from "./features/simulator/SimulatorPage";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useLocation } from "./navigation";

function Route({ path }: { path: string }) {
  switch (path) {
    case "/simulator": return <SimulatorPage />;
    case "/planned-operations": return <PlannedOperationsPage />;
    case "/device-health": return <DeviceHealthPage />;
    case "/system-health": return <SystemHealthPage />;
    default: return <OperationsPage />;
  }
}

export default function App() {
  const { path } = useLocation();
  // The provider sits outside the switch on purpose: the incident queue and the
  // selected ticket must outlive the route that happens to be showing them.
  return <ErrorBoundary><OperationsProvider><Route path={path} /></OperationsProvider></ErrorBoundary>;
}
