import { useCallback } from "react";
import { loadDeviceHealth } from "../../api/client";
import { useVisiblePolling } from "../../api/polling";
import type { DeviceHealth, Page } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { StatePanel } from "../../components/StatePanel";

const SILENCE: Record<string, string> = {
  unknown_silent: "silent", confirmed_dark: "dark", confirmed_live: "live",
  uninstrumented: "uninstrumented", device_suspect: "suspect",
};

export function DeviceHealthPage({ page }: { page?: Page<DeviceHealth> }) {
  const load = useCallback((signal: AbortSignal) => page ? Promise.resolve(page) : loadDeviceHealth(signal), [page]);
  const { data: polled, loading } = useVisiblePolling(load, 15_000);
  const data = page ?? polled;

  if (!data) return <AppShell><StatePanel title={loading ? "Loading device health" : "Device health unavailable"}>Device health is not a power outage; retry when the API is ready.</StatePanel></AppShell>;
  return <AppShell>
    <header className="secondary-header"><h1>Device health</h1><p>Device health is not a power outage. Sensor maintenance never opens a fault ticket.</p></header>
    {data.items.length
      ? <table aria-label="Device health">
        <thead><tr><th>Device</th><th>Pole</th><th>Link</th><th>Evidence</th><th>Battery</th><th>RSSI</th><th>Assignment mismatches</th><th>Stale replays</th></tr></thead>
        <tbody>{data.items.map((device) => <tr key={device.device_id}>
          <td>{device.serial_number}</td>
          <td>{device.pole_id}</td>
          <td>{device.is_online ? "online" : "offline"}</td>
          <td>{SILENCE[device.evidence_class] ?? device.evidence_class}</td>
          <td>{device.battery_pct}%</td>
          <td>{device.rssi_dbm} dBm</td>
          <td>{device.mismatch_events}</td>
          <td>{device.stale_replay_events}</td>
        </tr>)}</tbody>
      </table>
      : <StatePanel title="No device anomalies">Every assigned device is reporting normally.</StatePanel>}
    <p>Duplicate deliveries are rejected at ingest by fingerprint and are not attributed to a device.</p>
  </AppShell>;
}
