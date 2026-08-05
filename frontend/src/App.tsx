import { DeviceHealthPage } from "./features/health/DeviceHealthPage";
import { PlannedOperationsPage } from "./features/health/PlannedOperationsPage";
import { SystemHealthPage } from "./features/health/SystemHealthPage";
import { OperationsPage } from "./features/operations/OperationsPage";
import { SimulatorPage } from "./features/simulator/SimulatorPage";

export default function App() {
  switch (window.location.pathname) {
    case "/simulator": return <SimulatorPage />;
    case "/planned-operations": return <PlannedOperationsPage />;
    case "/device-health": return <DeviceHealthPage />;
    case "/system-health": return <SystemHealthPage />;
    default: return <OperationsPage />;
  }
}
