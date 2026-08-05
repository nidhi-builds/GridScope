# Decisions

Newest first. Each entry: what was chosen, what was rejected, and why.

---

## Report the sustained-ingest miss rather than chase it

**Chosen.** Publish 70.4 requests/second against a 500 requests/second target,
with the cause identified and the evidence committed.

**Rejected.** Collapsing the four ORM queries per request into raw SQL
(plausibly 2–3×), and splitting the inbox worker into its own container so the
API could run multiple Uvicorn processes (closest to correct, roughly 4×).

**Why.** Both were real options with time costs, and the second changes the
deployment shape that the rest of the submission depends on. The measurement is
honest and the ceiling is explained; a number nobody can account for would be
worth less than a miss that is fully diagnosed. Normal steady-state demand for
3,822 devices on a 15-minute heartbeat is about 4 messages/second, so the system
runs roughly 16× above ordinary load and falls short only of the worst-case
burst. Nothing is lost at the ceiling — messages queue, drain to zero, and report
no failures.

**Diagnosis, including what was wrong.** Three hypotheses were disproved before
the real one: raising the connection pool 15→60 and the threadpool 40→80 made it
*worse* (57→53 req/s); `pgbench` showed the database doing 899 tps, seventeen
times the application, killing the fsync theory; the enlarged pool then exceeded
PostgreSQL's `max_connections` and broke 22 tests. `docker stats` captured
*during* load — not after — showed the web process at 170–193% CPU and the
database at 77%, which is where the ~16 ms per request came from.

---

## Run background work off the event loop

**Chosen.** `asyncio.to_thread` for the inbox worker and the schedule poller.

**Rejected.** Leaving them as they were.

**Why.** `run_worker` was declared `async` but called blocking database work
directly, freezing every in-flight request for the length of each batch, every
three seconds. This was a production defect, not a test artefact. Fixing it also
raised throughput 53.5→60.9 req/s.

---

## Drain the inbox continuously while batches stay full

**Chosen.** Loop straight into the next batch when the last came back full; fall
back to the 3-second poll only when the inbox empties.

**Rejected.** Raising `WORKER_BATCH_SIZE`, which moves the number without fixing
the shape.

**Why.** Sleeping the full poll interval regardless of backlog capped drain at
one batch per three seconds. After a 60-second load run, 11,161 events were still
unprocessed 60 seconds later. Now drains to zero.

---

## Never let inferred topology emit an exact span

**Chosen.** Geographic inference produces a tree with a per-edge confidence
bucket. A bucket may emit an exact span only if its measured exact-span precision
reaches 90%. No bucket does, so inferred topology always reports a corridor.

**Rejected.** Emitting the most likely span with a confidence caveat.

**Why.** This is the assignment's central difficulty — 60% of transformers have
no recorded pole ordering — and the failure modes are not symmetric. A wrong
exact span sends a crew to the wrong pole with false certainty. A corridor sends
them to the right street with an honest search area. Measured: corridor
containment 43/43, zero false exact spans.

---

## Silence is never darkness

**Chosen.** Only a `power_lost` event with `energized = false` produces
`confirmed_dark`. A lapsed heartbeat produces `unknown_silent`, which is an
absence of information.

**Rejected.** Treating heartbeat timeout as evidence of outage.

**Why.** 8% of devices run firmware 1.2 and go terminally silent on power loss,
4% are independently offline, and batteries die. Inferring darkness from silence
would generate a false ticket for every dead battery, which is exactly the
failure the department already has with phone calls. The cost is real: a fault
affecting only firmware-1.2 poles is undetectable, and the system reports that
scenario as `unobservable by design` rather than as a miss.

---

## One ticket per fault, via dark-root reduction

**Chosen.** Reduce dark poles to those with no dark ancestor, then walk upstream
from each to the nearest live pole.

**Rejected.** Clustering by geography or by transformer.

**Why.** It is the physically correct answer on a radial network and it makes
simultaneous faults fall out for free — three faults on three branches produce
three dark roots and three tickets, with no special case. Clustering would need
tuning and would merge genuinely separate faults.

---

## Settle for 30 seconds before opening a ticket

**Chosen.** A 30-second settle window, 45-second hard deadline, 120-second
candidate expiry.

**Rejected.** Opening a ticket on the first dark event.

**Why.** A real fault arrives as a scatter of messages over seconds. Deciding on
the first produces one ticket per pole. The cost is up to 45 seconds of detection
latency, which is well inside the 120-second target.

---

## Restoration verified by telemetry, never by a button

**Chosen.** `report_resolved` is a claim. The ticket closes only after
restoration telemetry plus a 30-second stability window, and is rejected with a
typed `409` if scope poles are still dark.

**Rejected.** Closing on operator confirmation.

**Why.** The brief calls this out specifically. A crew reporting a fix before it
holds is the most common way outage systems lie about themselves.

---

## AI explains, it does not decide

**Chosen.** Gemini 2.5 Flash writes an English and Kannada explanation of an
already-decided incident, with the decided facts sent as a `protected` block that
the model must echo back unchanged. Any mismatch discards the response.

**Rejected.** An LLM anywhere in the localization path.

**Why.** A graph traversal is deterministic, instant, free and explainable; a
language model is none of those. The real friction is that the output is dense
and the crew lead may not read English comfortably. Translation and phrasing are
what these models are genuinely good at. Every failure path falls back to a
deterministic template. The deployed instance carries its own key, set as an
environment variable and never committed, so a reviewer needs no key of their
own. Running locally without one is fully supported and exercises the fallback.

---

## Topology as explicit edges with provenance

**Chosen.** A `topology_edges` table with `source` = `registry` / `inferred` /
`hidden_truth` and a `calibration_bucket`.

**Rejected.** A `parent_id` column on each pole.

**Why.** Inferred and registry edges must coexist and be distinguishable at query
time, because confidence depends on which was used. Hypotheses change as evidence
arrives. And the hidden ground truth needed for evaluation lives in the same
table under a different `source`, so the simulator needs no parallel schema.

---

## Poll every three seconds instead of WebSocket push

**Chosen.** Visibility-aware polling that preserves the last good data on a
transient failure.

**Rejected.** WebSocket push.

**Why.** Simple, survives reconnection, and behaves correctly behind proxies with
no upgrade handling. **This is the decision most likely to be wrong.** On a
feeder-scale event an operator would notice the lag, and it is the first UI thing
I would change.

---

## Assumptions made where the brief was ambiguous

- **"Affected count" means poles, not customers.** No customer-per-pole data
  exists, so a customer count would be invented. The count is flagged
  `estimated` whenever the topology beneath it was inferred.
- **PIN codes come from pole records where present**, and are reported with
  provenance (`registry` / `estimated` / unavailable). 3% of poles have no PIN
  and the UI says so rather than guessing.
- **A planned outage matches on scope and window**, with a 40-minute end grace.
  An overrun becomes a real ticket, flagged as an overrun, because at some point
  planned work that has not ended is an outage.
- **Kannada is the second language**, on the assumption of a Karnataka
  distribution utility, inferred from the Bengaluru geography in the brief.
- **One Uvicorn process** is treated as an architectural constraint, because the
  inbox worker and schedule poller run in-process and must have a single owner.

---

## Known fragile, currently wrong, or cut

- **Planned-outage matching is seed-sensitive, and this is the most serious
  known defect.** Across 100 noise-only runs, `planned_outage` opened 11 fault
  tickets. Every other noise scenario — device death, offline baseline, reboot
  replay, transport noise, firmware-1.2 silence — opened zero. Matching holds on
  the default seed and in the browser suite, but fails when the simulator selects
  a different transformer, which suggests the failure is in scope matching
  between the scheduled outage and the observed fault rather than in the timing
  window. Found in the final measurement pass, with insufficient time to
  diagnose properly. Reported rather than hidden because firing on scheduled load
  shedding is exactly the failure the brief singles out.
- **`feeder_fault` produced no incident on 10 of 10 non-default seeds** in the
  same campaign, while passing on the canonical seed in the backend suite. Likely
  the same class of seed sensitivity — a feeder whose DTs do not reach the 60%
  quorum with that seed's device coverage — but unconfirmed.
- **Simulator reset races the worker.** Reset deletes across seven tables while
  the worker may commit a new ticket event mid-delete. Mitigated with a bounded
  retry and a `503`; the correct fix is `ON DELETE CASCADE` on the incident
  foreign keys, which is a migration I chose not to run this close to the
  deadline.
- **Backend tests are not isolated from database state.** Some wrap themselves in
  a rolled-back transaction; others do not. Running the load tests then `pytest`
  produces failures that vanish after `docker compose down -v`. Documented in
  `DEPLOYMENT.md`. The fix is to put every test in a rollback fixture.
- **`openapi.json` in the repository is stale** — 12 routes, no simulator paths.
  The live `/openapi.json` is generated and correct; the committed snapshot has
  not been regenerated since Task 9.
- **Per-device duplicate rate is not available.** Duplicates are rejected at
  ingest by fingerprint and never persisted, so there is no honest per-device
  figure. The device-health view states this rather than inventing one.
- **Ingest ceiling of ~70 req/s**, as above.
- **Cut deliberately**: authentication, crew routing, analytics, historical
  trend views, WebSocket push, and any customer-facing surface. All were
  explicitly out of scope in the brief and would have come out of localization
  time.

---

## With two more weeks

0. **Fix planned-outage seed sensitivity first.** It is the only defect here that
   produces a wrong answer an operator would act on, and firing on scheduled work
   is the failure mode the brief calls out by name. Everything below is
   secondary to it.
1. **Split the inbox worker into its own service** so the API can run multiple
   Uvicorn processes, then re-measure sustained ingest. This is the single
   largest known gap.
2. **`ON DELETE CASCADE` on incident foreign keys**, removing the reset race
   properly rather than retrying around it.
3. **Calibrate inference against real utility topology**, not synthetic truth.
   The 90% precision bar is right in principle; whether any bucket clears it on
   real data is unknown, and that determines whether exact spans are ever
   possible on the 60%.
4. **WebSocket push** for the operator console, keeping polling as the fallback.
5. **Test isolation**, so correctness and load suites can run in any order.
6. **Per-device delivery statistics**, including a persisted duplicate counter,
   so device health can show a genuine duplicate rate.
