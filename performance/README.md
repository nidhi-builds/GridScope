# GridScope performance and correctness evidence

Every number in `results/` is produced by the commands below against the same
Docker image a reviewer runs. Nothing here is hand-written. If a target is
missed, the raw result stays in place and the miss is reported with its actual
value — assertions are never relaxed to make a run pass.

## Prerequisites

The stack must already be running, seeded, and healthy:

```powershell
docker compose up -d
docker compose logs --tail 5 web   # expect: Uvicorn running on http://0.0.0.0:8000
```

The runners below live in the opt-in `tools` profile. A plain `docker compose up`
still starts only `db` and `web`.

## The five targets

| Target | Gate | Produced by | Result file |
|---|---|---|---|
| Fault to visible incident | p95 < 120s | `measure_detection.py`, Playwright | `detection.json`, `lifecycle.json` |
| Repair to verified closure | p95 < 120s | `measure_detection.py`, Playwright | `detection.json`, `lifecycle.json` |
| Incident list response | p95 < 2s | `ui-load.spec.ts` | `ui-load.json` |
| Sustained ingest | >=500 req/s for 60s, <1% failures | `sustained.js` | `sustained.json` |
| Burst ingest | 5,000 events / 10s, no unique loss, drain <60s | `burst.js` | `burst.json` |

Accuracy gates — exact-span precision >=95%, inferred precision by bucket,
corridor containment >=95%, and zero false tickets on noise-only runs — come
from `measure_accuracy.py` into `accuracy.json`.

## Commands

```powershell
# Browser workflow, negative cases, and UI latency
# First run also downloads Chromium into a cached volume, so allow a few minutes.
docker compose --profile tools run --rm browser-test

# Sustained and burst ingest
docker compose --profile tools run --rm k6 run /tests/sustained.js --summary-export /results/sustained.json
docker compose --profile tools run --rm k6 run /tests/burst.js --summary-export /results/burst.json

# Repeatable detection, restoration, and accuracy campaigns
docker compose --profile tools run --rm measure /app/scripts/measure_detection.py --runs 100 --output /app/performance/results/detection.json
docker compose --profile tools run --rm measure /app/scripts/measure_accuracy.py --runs 100 --output /app/performance/results/accuracy.json

# Submission gate
docker compose --profile tools run --rm measure /app/scripts/verify_submission.py --base-url http://web:8000
```

The measurement campaigns reset the simulator between runs, so run them when no
one is watching the console — they deliberately churn incident state.

## Reading a failed run

- `http_req_failed` above 1% on `sustained.js` means ingest, not the worker, is
  the bottleneck. Compare `http_req_duration` against database CPU.
- A non-zero `backlog_remaining` in the teardown log means the worker did not
  drain within 60s. The accepted events are still durable; the gate that failed
  is drain time, and the two must be reported separately.
- `unexpected_outcome` above zero on `burst.js` means an event was neither
  accepted nor recognised as a duplicate. That is a correctness failure and
  outranks any latency number.
- A missed p95 in `detection.json` should be reported with the distribution, not
  just the percentile — a long tail and a uniform shift have different causes.
