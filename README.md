# GridScope

Live fault localization for radial LT distribution networks.

Pole-mounted devices report power loss. GridScope turns thousands of those
messages into **one ticket per fault**, pointed at the span of line that actually
failed — not one alert per dark pole, and not an alert every time a sensor
battery dies.

It is built for a 2 a.m. control room: the operator sees what failed, where to
send a crew, how confident the system is, and why.

**Live:** <https://gridscope-zulr.onrender.com>

## Run it

Requires Docker only.

```bash
git clone https://github.com/nidhi-builds/GridScope.git
cd GridScope
docker compose up
```

Then open <http://localhost:8000>.

First start builds the frontend, applies migrations, and seeds a deterministic
network of 4 substations, 12 feeders, 60 distribution transformers, 4,200 poles
and 3,822 devices. Expect **90–120 seconds** before the app answers. Nothing else
to configure — no manual migration step, no `.env` to edit.

## See it work

Open **`/simulator`** — the clearly-labelled Demo view — pick `Exact
known-topology span fault`, and press **Start scenario**.

One incident appears in the operations queue with a located span, a PIN code, an
affected-pole count and a confidence level. Press **Repair fault**, then
acknowledge, assign and report the repair in the incident panel. The ticket
closes on restoration telemetry, not on your click.

The generated incident is a link. Clicking it opens that ticket in place, so the
fault can be repaired and the ticket worked without leaving the demo view.

## The operations map

The map draws the network, not just the ticket you clicked.

- **Every pole, in its current state.** Green has power, red is confirmed dark,
  grey has a device but is not reporting, amber has an unreliable sensor, hollow
  has no sensor at all. Hover any pole for its code and state.
- **Grey and hollow are different facts, deliberately.** Grey is a pole that
  *should* be reporting and is not; hollow is a pole that never can. Neither is
  evidence of an outage. This is the same rule that stops a dead battery from
  raising a ticket, made visible.
- **Every queued incident is drawn**, filtered in step with the queue. Filter the
  list and the map follows.
- **Clicking a ticket zooms to it** — first to the incident's own location, then
  onto the exact span or search corridor once its geometry loads.

Selection survives everything: switching tabs, reloading, or sharing the URL.

The equivalent single command:

```bash
curl -X POST http://localhost:8000/api/v1/simulator/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario_key":"known_span","seed":20260803}'
```

Seventeen deterministic scenarios are available, including three simultaneous
branch faults, a dead device with power still on, a matched planned outage,
firmware-1.2 terminal silence, and duplicate/out-of-order/stale delivery.

## Live deployment

<https://gridscope-zulr.onrender.com> — the demo video link is in the submission
email.

The deployment runs on a free tier that **cold-starts**. If the first request
hangs, give it up to 60 seconds rather than assuming it is down. Readiness is
reported at `/api/v1/ready`.

A ticket can be linked to directly — selection lives in the URL:

```
https://gridscope-zulr.onrender.com/operations?incident=<incident-id>
```

**The map may be mostly grey on a freshly deployed instance, and that is
correct.** A pole is only drawn green once it has *reported* power. Until
telemetry arrives, poles are either grey (has a device, has not reported) or
hollow (no device at all) — never green and never red. Start a scenario on
`/simulator` to see the network come alive.

## Documentation

| File | What is in it |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Data flow, schema, the localization algorithm, noise handling, API surface, UI reasoning, the AI feature |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Prerequisites, exact commands, every environment variable, verification, troubleshooting, clean reset |
| [`DECISIONS.md`](DECISIONS.md) | What was chosen and rejected, assumptions, what is fragile, what two more weeks would buy |
| [`AI-WORKFLOW.md`](AI-WORKFLOW.md) | How this was built with AI, where the AI was wrong, and how that was caught |
| [`diary.md`](diary.md) | Working log: decisions, failures and verification, in order |
| [`performance/README.md`](performance/README.md) | How every measured number was produced, and how to reproduce it |

## Measured, not claimed

Every figure below comes from a committed raw result in
[`performance/results/`](performance/results/). Reproduction commands are in
[`performance/README.md`](performance/README.md).

| Target | Gate | Measured |
|---|---|---|
| Fault to visible incident, p95 | < 120s | 4.85s (90 runs; p50 0.83s, p99 9.23s) |
| Repair to telemetry-verified closure, p95 | < 120s | 1.90s (53 runs) |
| Full browser lifecycle, injection to closed ticket | < 120s | 35.2s |
| Incident list, p95 | < 2s | 0.09s |
| Exact-span precision on known topology | ≥ 95% | 100% (10/10) |
| Corridor contains the real fault | ≥ 95% | 100% (45/45) |
| Inferred topology emitting a false exact span | none | none |
| Burst of 5,000 events including duplicates | no unique loss | 4,502 stored + 498 duplicates rejected = 5,000 |
| False tickets from noise-only scenarios | zero | **11 — missed, all from planned outages on non-default seeds** |
| Sustained ingest | 500 req/s | **70.4 req/s — missed** |

Two misses, both stated rather than smoothed over.

**False tickets.** Dead devices, offline baselines, reboot replays, transport
noise and firmware-1.2 silence produced **zero** tickets across 100 runs. All 11
came from `planned_outage`, and only on seeds other than the default: schedule
matching holds on the canonical seed and on the browser suite, but is
seed-sensitive when the simulator picks a different transformer. That is a real
defect, found late, and not fixed. See `DECISIONS.md`.

**Sustained ingest.** A single Python process spends roughly 16 ms of CPU per
message and saturates two cores at about 70 messages/second. Nothing is lost
under load — messages queue, drain completely, and report zero failures. Normal
steady-state demand for 3,822 devices on a 15-minute heartbeat is about
4 messages/second, so the system runs roughly 16× above ordinary load and falls
short only of the worst-case burst target. `DECISIONS.md` covers the two routes
to fixing it and why neither was taken before the deadline.

## Tests

```bash
docker compose exec web pytest backend/tests -q         # backend, including localization
docker compose --profile tools run --rm frontend-test   # frontend component tests
docker compose --profile tools run --rm browser-test    # end-to-end browser specs
```

The tests that matter most are on localization. `backend/tests/detection/` and
`backend/tests/simulator/test_service.py` assert that a known fault in a known
topology produces the expected span, that inferred topology degrades to a
corridor instead of guessing, and that noise-only scenarios open zero tickets.

Run the backend suite **before** the load tests, or reset the database in
between — several backend tests assume a near-clean database. This is a known
limitation, recorded in `DECISIONS.md`.
