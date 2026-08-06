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

## Draw the whole network, not just the selected ticket

**Chosen.** A new read-only `GET /api/v1/network/poles` publishing every pole with
its current `pole_evidence_state` class, plus transformers and recorded wiring.
The map renders it as a base layer under the incident overlays.

**Rejected.** Leaving the map blank until a ticket is clicked, and separately,
fetching every queued incident's geometry as a substitute for real network state.

**Why.** The data already existed — `pole_evidence_state` has carried a per-pole
live/dark/silent/uninstrumented class since Task 5 — and was only ever read one
incident at a time. An operator opening the console saw an empty basemap, which
says nothing about whether the grid is healthy or whether the system is working.
The endpoint is additive: no schema, no write path and no existing route changed.

The colouring keeps `unknown_silent` and `uninstrumented` visually distinct.
Collapsing them would undo the system's central rule at the last step: a pole
that should be reporting and is not is a different fact from a pole that has no
sensor, and neither is evidence of an outage. A test asserts they never share a
label or a colour.

Poles render on a canvas layer rather than as SVG nodes; a few thousand DOM
circles makes panning unusable.

---

## Selection belongs in the URL, not in component state

**Chosen.** `?incident=<id>` as the single source of truth for what is selected,
with client-side routing via `pushState`.

**Rejected.** Keeping selection in React state and persisting it to
`sessionStorage`, as the simulator originally did for its run.

**Why.** Every route was a plain `<a href>`, so each tab switch was a full page
load that destroyed the queue, the filters, the map geometry cache, the poll and
the selection. The simulator already carried a `sessionStorage` workaround with
the comment *"navigation is a full page load"* — treating the symptom. Putting
selection in the URL also made an existing dead feature work: `RunComparison` had
always emitted `/operations?incident=...` links and nothing had ever read the
parameter.

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

  This bit during the final session and is worth recording precisely, because it
  shows the defect is sharper than "some tests are order-dependent". A new test
  for the network endpoint inserted one `Pole` row and mutated two
  `pole_evidence_state` rows, using the existing `session` fixture. Those writes
  escaped the rollback and broke **eight** unrelated tests across the
  correlation, workflow, simulator, ingestion and worker-replay suites — all of
  which passed when run on their own. The tests were rewritten to be read-only,
  which fixed it. But a test suite where writing a row through the documented
  fixture silently corrupts later tests is a trap for the next person, and the
  `SAWarning: transaction already deassociated from connection` emitted alongside
  it is the visible symptom.

- **Three crashes came from unguarded reads of API payloads.**
  `detail.boundary.geometry`, `data.incidents.items` in the status bar, and the
  same path in the operations provider. Each unmounted the entire console —
  queue, map and status bar together — on a partial or malformed response. All
  three are now guarded and a root error boundary catches the general case, but
  the pattern says the frontend trusts response shapes it does not validate. The
  real fix is parsing responses at the client boundary instead of casting them.

- **The incident detail panel fetched once and then went stale.** It did not
  refetch as the ticket progressed, so an operator watching the panel would never
  see the telemetry-verified closure it explicitly promises would happen. Fixed
  by keying the fetch on the incident's `updated_at` from the polled queue.
  Notably, the browser suite did not catch this: it asserted closure against the
  queue row rather than the panel.

- **The live network map is unmeasured.** `ui-load.json` was recorded before the
  map drew anything beyond the selected incident. The queue still paints before
  the network layer resolves, and the network polls on its own 15-second cycle,
  so the published 0.09s p95 is probably still honest — but it has not been
  re-measured, and it should be before that number is quoted again.

- **A newly seeded deployment shows a grey map, which reads as broken.** No pole
  is green until it has reported, and scenarios only emit telemetry for the
  devices they involve. This is correct behaviour — inventing a green pole would
  be exactly the sin the system refuses elsewhere — but it is a poor first
  impression. A count strip now states the numbers explicitly. The proper fix is
  a baseline heartbeat per online device at seed time, which shifts the
  `noise_baseline` scenario's expectations and was not worth changing this late.
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

Ordered by what a wrong answer costs, not by what is interesting to build. The
ranking principle throughout: a defect that sends a crew to the wrong place, or
sends one when it should not, outranks any amount of throughput.

### Week one — correctness

**1. Fix planned-outage seed sensitivity.** The only defect that produces a wrong
answer an operator would act on, and firing during scheduled load shedding is the
failure the brief names directly. The evidence points at scope matching rather
than the time window: matching holds when the simulator picks the canonical
transformer and fails when it picks another, across 11 false tickets in 100
noise-only runs. The first day goes to a reproduction harness that sweeps seeds
and records which transformer each failure chose, because the current evidence is
a count without a mechanism — and the performance investigation already taught
this project that three plausible hypotheses can all be wrong. Only then the fix.

**2. Diagnose `feeder_fault` silence on non-default seeds.** Zero incidents on
10 of 10 non-canonical seeds while passing on the default. The working theory is
a feeder whose transformers miss the 60% quorum under that seed's device
coverage, which would make it a *correct* refusal wearing the costume of a bug.
That distinction matters enormously and is currently unknown. If the quorum is
right, the scenario should report `unobservable by design`, exactly as
firmware-1.2 silence already does, rather than looking like a miss.

**3. Test isolation, with a rollback fixture around every test.** Promoted from
sixth place because it stopped being a tidiness issue. In the final session a
test that wrote one row through the documented fixture silently broke eight
unrelated tests, and the failures looked exactly like a pre-existing defect.
A suite that punishes correct usage is worse than no suite: it teaches the next
person to distrust red, which is how a real regression gets waved through.

**4. Parse API responses at the client boundary.** Three separate crashes came
from reading fields off payloads the frontend casts but never validates, and each
one unmounted the whole console. A schema check at the fetch boundary — returning
a typed error the UI already knows how to display — removes the entire class,
rather than adding a guard per field as each one is discovered in production.

### Week two — scale, then polish

**5. Split the inbox worker into its own service**, letting the API run multiple
Uvicorn processes, then re-measure. The largest known gap, and the diagnosis is
already complete: ~16 ms of CPU per request in a single process, with the
database seventeen times faster than the application. Expected roughly 4×, which
clears 200 req/s and is honest about not reaching 500 without further work.
Deliberately second to correctness: the system already runs 16× above ordinary
steady-state demand, so this buys headroom for a worst case, not for Tuesday.

**6. `ON DELETE CASCADE` on incident foreign keys**, removing the simulator reset
race properly instead of retrying around it with a bounded `503`.

**7. Re-measure everything the map changed.** `ui-load.json` predates the network
layer. The number is probably still honest — the queue paints before the network
resolves — but "probably" is not what the rest of this document trades in.

**8. Calibrate inference against real utility topology.** The 90% exact-span bar
is right in principle; whether any confidence bucket clears it on real data is
unknown, and that single measurement decides whether exact spans are ever
possible on the 60% of transformers with no recorded ordering. Synthetic ground
truth cannot answer it. This is the highest-value item on the list for the
product and the lowest-certainty for the schedule, which is why it sits here
rather than in week one.

**9. Baseline heartbeats at seed time**, so a fresh deployment shows a live
network instead of a grey one. Cosmetic, but it is the first thing anyone sees.

**10. WebSocket push** for the console, keeping polling as the fallback. Detection
is already 4.85s p95 against a 120s target, so this improves feel, not capability.

**11. Per-device delivery statistics**, including a persisted duplicate counter,
so device health can show a real duplicate rate instead of explaining why it
cannot.

### What would not be built

Authentication, crew routing, analytics and historical trends stay cut. Each is a
week that does not go into localization, and localization on unrecorded topology
is the part of this problem that is actually hard. A prettier console that sends
crews to the wrong pole is worth less than a plain one that does not.
