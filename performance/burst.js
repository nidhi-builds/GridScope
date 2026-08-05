import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

/**
 * Burst tolerance: exactly 5,000 mixed-device events over 10 seconds, including
 * deliberate exact duplicates. Every unique event must persist and the backlog
 * must drain within 60 seconds. Duplicates must be rejected by fingerprint
 * rather than stored twice.
 */
const BASE = __ENV.GRIDSCOPE_BASE_URL || "http://web:8000";
const TOTAL_EVENTS = Number(__ENV.TOTAL_EVENTS || 5000);
const DURATION_SECONDS = Number(__ENV.DURATION_SECONDS || 10);
const DUPLICATE_EVERY = Number(__ENV.DUPLICATE_EVERY || 10);
const DRAIN_TIMEOUT_SECONDS = Number(__ENV.DRAIN_TIMEOUT_SECONDS || 60);

const uniqueAccepted = new Counter("unique_accepted");
const duplicateRejected = new Counter("duplicate_rejected");
const unexpected = new Counter("unexpected_outcome");

export const options = {
  scenarios: {
    burst: {
      executor: "shared-iterations",
      vus: 100,
      iterations: TOTAL_EVENTS,
      maxDuration: `${DURATION_SECONDS + 20}s`,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    unexpected_outcome: ["count==0"],
  },
};

export function setup() {
  const devices = [];
  for (let page = 1; page <= 10; page += 1) {
    const response = http.get(`${BASE}/api/v1/device-health?page=${page}&page_size=100`);
    if (response.status !== 200) break;
    const items = response.json("items") || [];
    if (!items.length) break;
    for (const item of items) devices.push({ device_id: item.device_id, pole_id: item.pole_id });
  }
  if (!devices.length) throw new Error("no devices available; is the database seeded?");
  const readiness = http.get(`${BASE}/api/v1/ready`).json();
  return { devices, backlogBefore: readiness.unprocessed_count, epoch: Date.now() };
}

export default function (data) {
  const index = __ITER * 100 + __VU;
  const device = data.devices[index % data.devices.length];
  // Every DUPLICATE_EVERY-th event repeats the previous fingerprint exactly.
  const isDuplicate = index % DUPLICATE_EVERY === 0 && index > 0;
  const sequence = isDuplicate ? index - 1 : index;

  const payload = JSON.stringify({
    device_id: device.device_id,
    pole_id: device.pole_id,
    seq: sequence,
    // Fixed per sequence so a duplicate is byte-identical, not merely similar.
    ts: new Date(data.epoch + sequence * 1000).toISOString(),
    event_type: "heartbeat",
    energized: true,
    battery: 75,
    rssi: -95,
  });

  const response = http.post(`${BASE}/api/v1/telemetry`, payload, {
    headers: { "Content-Type": "application/json" },
    tags: { name: "telemetry-burst" },
  });

  check(response, { "accepted (202)": (result) => result.status === 202 });
  if (response.status !== 202) {
    unexpected.add(1);
    return;
  }
  const outcome = response.json("outcome");
  if (outcome === "accepted" || outcome === "quarantined") uniqueAccepted.add(1);
  else if (outcome === "duplicate") duplicateRejected.add(1);
  else unexpected.add(1);
}

export function teardown(data) {
  const startedAt = Date.now();
  const deadline = startedAt + DRAIN_TIMEOUT_SECONDS * 1000;
  let readiness = http.get(`${BASE}/api/v1/ready`).json();
  while (readiness.unprocessed_count > data.backlogBefore && Date.now() < deadline) {
    sleep(2);
    readiness = http.get(`${BASE}/api/v1/ready`).json();
  }
  console.log(JSON.stringify({
    test: "burst",
    total_events: TOTAL_EVENTS,
    duplicate_every: DUPLICATE_EVERY,
    backlog_remaining: readiness.unprocessed_count,
    drain_seconds: (Date.now() - startedAt) / 1000,
    drained_within_timeout: readiness.unprocessed_count <= data.backlogBefore,
  }));
}
