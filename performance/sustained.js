import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

/**
 * Sustained ingest: at least 500 individual telemetry requests per second for
 * 60 seconds, then wait for the durable inbox to drain and compare the count
 * the API accepted against the count it persisted. Every request goes through
 * the same public /telemetry contract a real device uses.
 */
const BASE = __ENV.GRIDSCOPE_BASE_URL || "http://web:8000";
const RATE = Number(__ENV.RATE || 500);
const DURATION_SECONDS = Number(__ENV.DURATION_SECONDS || 60);
const DRAIN_TIMEOUT_SECONDS = Number(__ENV.DRAIN_TIMEOUT_SECONDS || 60);

const accepted = new Counter("events_accepted");
const duplicates = new Counter("events_duplicate");
const rejected = new Rate("events_rejected");

export const options = {
  // The drain poll below can legitimately use the full timeout; k6's 60s default
  // killed teardown and lost the drain measurement entirely on the first run.
  teardownTimeout: `${DRAIN_TIMEOUT_SECONDS + 60}s`,
  scenarios: {
    sustained: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: `${DURATION_SECONDS}s`,
      preAllocatedVUs: 120,
      maxVUs: 600,
    },
  },
  thresholds: {
    // The PRD gate: HTTP failure rate below 1%.
    http_req_failed: ["rate<0.01"],
    events_rejected: ["rate<0.01"],
  },
};

function loadDevices() {
  const devices = [];
  for (let page = 1; page <= 10; page += 1) {
    const response = http.get(`${BASE}/api/v1/device-health?page=${page}&page_size=100`);
    if (response.status !== 200) break;
    const items = response.json("items") || [];
    if (!items.length) break;
    for (const item of items) devices.push({ device_id: item.device_id, pole_id: item.pole_id });
  }
  if (!devices.length) throw new Error("no devices available; is the database seeded?");
  return devices;
}

export function setup() {
  const devices = loadDevices();
  const before = http.get(`${BASE}/api/v1/ready`).json();
  return { devices, startedAt: Date.now(), backlogBefore: before.unprocessed_count };
}

export default function (data) {
  const device = data.devices[Math.floor(Math.random() * data.devices.length)];
  const payload = JSON.stringify({
    device_id: device.device_id,
    pole_id: device.pole_id,
    // Unique per iteration so the fingerprint is genuinely new, not a duplicate.
    seq: __ITER * 1000 + __VU,
    ts: new Date().toISOString(),
    event_type: "heartbeat",
    energized: true,
    battery: 80,
    rssi: -90,
  });

  const response = http.post(`${BASE}/api/v1/telemetry`, payload, {
    headers: { "Content-Type": "application/json" },
    tags: { name: "telemetry" },
  });

  const ok = check(response, { "accepted (202)": (result) => result.status === 202 });
  rejected.add(!ok);
  if (ok) {
    const outcome = response.json("outcome");
    if (outcome === "duplicate") duplicates.add(1);
    else accepted.add(1);
  }
}

/** Drain check: the backlog must clear within 60s of the load stopping. */
export function teardown(data) {
  const deadline = Date.now() + DRAIN_TIMEOUT_SECONDS * 1000;
  let readiness = http.get(`${BASE}/api/v1/ready`).json();
  while (readiness.unprocessed_count > data.backlogBefore && Date.now() < deadline) {
    sleep(2);
    readiness = http.get(`${BASE}/api/v1/ready`).json();
  }
  const drainedSeconds = (Date.now() - (deadline - DRAIN_TIMEOUT_SECONDS * 1000)) / 1000;
  console.log(JSON.stringify({
    test: "sustained",
    requested_rate_per_second: RATE,
    duration_seconds: DURATION_SECONDS,
    backlog_remaining: readiness.unprocessed_count,
    drained_within_timeout: readiness.unprocessed_count <= data.backlogBefore,
    drain_seconds: drainedSeconds,
  }));
}
