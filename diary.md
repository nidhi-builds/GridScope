# GridScope Diary

Short, chronological project record. Repeated discussion is summarized once.
Use only the tags that apply: `[request]`, `[question]`, `[sources]`,
`[decision]`, `[output]`, `[verification]`, `[finalized]`, `[follow-up]`.
Chronology follows the conversation order; exact clock times are recorded only
when supported by a file timestamp or another traceable source. Read this file
at the start of each project session and update it after material questions,
decisions, design changes, implementation milestones, or verification results.

## 2026-08-01

> Reconstructed from workspace artifacts. The original conversation is not
> available, so this records only what can be supported.

- [sources] `solution_notes.txt` was created at 23:23. It is empty.
- [output] Project workspace and notes were started for the GridScope
  assignment. No substantive decision survives in the file.

## 2026-08-02

> Reconstructed from the original PRD artifact and its creation timestamp.

- [sources] The first `PRD.md` was created at 22:06. Its later content was
  superseded by the final PRD.
- [request] Define the initial solution for the electricity-fault assignment.
- [decision] Center the product on pole telemetry ingest, graph-based fault
  localization, one ticket per physical boundary, telemetry-verified closure,
  an operator console, and a simulator.
- [question] How should the system handle incomplete topology, sensor failures,
  scheduled outages, duplicate/late messages, and missing devices?
- [follow-up] Validate the draft against the complete assignment and pressure
  test these messy-data cases before execution.

## 2026-08-03

### Claude PRD review

- [sources] `PRD-claude.md` was created at 10:40. It expands the earlier PRD
  with topology inference, calibration, confidence, firmware behavior,
  scheduled-outage handling, simulator cases, AI scope, and performance goals.
- [request] Compare Claude's PRD with the assignment, identify loopholes,
  validate performance, select the stack, and create a final execution PRD.
- [sources] `assignment/00-candidate-brief.md` through
  `assignment/05-faq.md`, the earlier PRD, Claude PRD, and official technical
  documentation for FastAPI, PostgreSQL, Vite, k6, Render, React Leaflet, and
  OpenAI.
- [output] Identified corrections: silence cannot mean darkness; scheduled
  outages cannot create fault tickets; stale retries cannot rewind state;
  topology inference must degrade honestly; PIN fallback and physical
  observability limits must be explicit; restoration cannot wait for a
  15-minute heartbeat.

### Final PRD decisions

- [question] Optimize for the stated 15-20 hour assignment budget? Answer:
  yes.
- [decision] Use a modular monolith: FastAPI, PostgreSQL durable inbox,
  React/TypeScript/Vite, Leaflet, NetworkX, polling, pytest, Playwright, k6,
  Docker Compose, and one public Docker deployment. Do not add Redis, Kafka,
  Celery, microservices, or WebSockets.
- [decision] Use registry topology where present. Infer missing topology from
  geography, calibrate it against hidden truth, and fall back to a corridor or
  DT-level result when an exact span is unsupported.
- [decision] Use an optional AI explanation/translation only after deterministic
  incident creation. AI cannot alter localization or ticket state.
- [output] Produced the final [PRD.md](PRD.md) covering architecture, API, data
  model, UI, simulator, deployment, performance, documentation, and delivery.
- [verification] PRD review passed: 27 explicit coverage checks; no placeholders,
  duplicate headings, encoding issues, stale numbering, or Markdown-fence errors.

### Reliability revision

- [request] Deepen the design around one-shot capacitor messages, heartbeats,
  uninstrumented poles, 4% offline devices, six-hour retries, clock skew,
  unreliable scheduled outages, and missing topology.
- [decision] Keep the solution small: one internal candidate record, evidence
  tiers, a 30-second settle window capped at 45 seconds, a 180-second real-time
  event-age rule, corridor fallback, schedule-scope matching, and calibration
  gates. No new service or dependency.
- [output] Added messy-data cascades, controls, residual limits, simulator
  proofs, and accuracy/false-ticket gates to [PRD.md](PRD.md).
- [verification] Final PRD check passed 27/27 coverage checks, including all
  five assignment performance targets.
- [finalized] `PRD.md` is the execution source of truth.

### Diary setup

- [request] Maintain a low-noise project diary from 1 August onward.
- [output] Created this root [diary.md](diary.md), then simplified it into a
  turnwise timeline and reconstructed 1-2 August only from traceable artifacts.
- [finalized] This diary is the ongoing record for material project work.

### Unified functionality

- [question] Is there one coherent rule across `power_lost`, heartbeats,
  topology, scheduled outages, offline devices, missing devices, and
  restoration evidence; exactly when does the system create or avoid a fault
  ticket?
- [decision] Use one evidence rule: ticket only when current, valid,
  topology-consistent direct dark evidence is corroborated and no stronger
  non-fault explanation fits. Silence, battery, and RSSI are context, not
  outage proof. Do not require every downstream device to report.
- [output] Added the unified decision rule and its intentional ambiguity limits
  to `PRD.md` Section 8.5. Existing Tier-2, schedule, localization, and
  restoration controls remain the detailed implementation of that rule.
- [question] Does the system coherently check all sources, and exactly when is
  a fault detected or rejected? Answer: validate stream identity/order/age;
  interpret direct live/dark telemetry; group it by receive-time and topology;
  check schedule scope and timing; test device-failure, stale-replay, and fresh
  live contradictions; then return the narrowest supported span, corridor, DT,
  feeder, anomaly, planned operation, or no ticket.
- [decision] Promote only Tier-2 evidence: two topology-consistent direct-dark
  reports, one direct-dark report plus a post-onset adjacent live parent, or a
  qualified DT/feeder quorum. A matching observed schedule becomes a planned
  operation. A lone packet, silence, stale retry, device mismatch, isolated
  sensor behavior, or fully unobservable scope does not create a fault ticket.
- [decision] Restoration does not require every downstream device. Require
  fresh restoration at the boundary and representative previously dark
  branches, no fresh dark contradiction, and 30 seconds of stability. Missing,
  silent, uninstrumented, and baseline-offline devices lower confidence.
- [finalized] The PRD now states both fault-promotion and no-ticket conditions
  in one place without expanding the system design.

### Performance validation

- [question] Is the complete stack designed to meet all performance targets?
  Answer: yes by design, but compliance is claimed only after measurement.
- [decision] Budget detection as 30 seconds settling, at most 5 seconds worker
  backlog, and at most 3 seconds UI polling; budget restoration as events within
  20 seconds, 30 seconds stability, and at most 3 seconds UI polling.
- [verification] Required execution gates remain: fault and restoration p95
  below 120 seconds, sustained 500 messages/second, 5,000 messages in 10 seconds
  without accepted-event loss, incident-list p95 below 2 seconds, known exact
  precision at least 95%, inferred exact precision at least 90% or degradation,
  corridor containment at least 95%, and zero required noise-case fault tickets.

### Implementation planning

- [request] Move from the finalized PRD to the implementation plan.
- [sources] Cross-checked `PRD.md` against all assignment documents, especially
  acceptance gates G1-G6, the evaluation weights, required simulator behavior,
  five performance targets, and five root documents.
- [decision] Use one execution plan for the integrated modular monolith, divided
  into 15 independently testable tasks with test-first steps and incremental
  commits. Prioritize topology, evidence, localization, and simulator truth
  before UI polish.
- [output] Created
  `docs/superpowers/plans/2026-08-03-gridscope-implementation.md` with the file
  map, stable interfaces, commands, expected results, deployment, documentation,
  demo, and final submission gates.
- [finalized] Implementation must not be called complete until clean-clone,
  scenario, accuracy, performance, public-deployment, and video evidence exist.

### Execution handoff

- [question] Which model should execute each implementation task?
- [sources] Current OpenAI model guidance for the GPT-5.6 family.
- [decision] Default to GPT-5.6 Sol with high reasoning for execution. Use Sol
  for Tasks 2-7, 9, and 11-14; use `xhigh` only for difficult Task-14 diagnosis.
  GPT-5.6 Terra at medium/high is acceptable for mechanical Tasks 1, 8, 10,
  and 15 when cost matters. Reserve GPT-5.6 Luna for the deployed optional
  explanation/translation feature, not core implementation.
- [request] Begin implementation from the approved 15-task plan.
- [decision] Commit after each reviewed 2-3 task checkpoint, not after every
  task: Tasks 1-3, 4-6, 7-9, 10-12, and 13-15. Individual task test gates
  remain mandatory before the group commit.
- [follow-up] Start Task 1 using the selected execution workflow. Record only
  major implementation choices, deviations, failures, measurements, and
  finalized outcomes here; do not repeat routine command-level activity.

## 2026-08-04

- [request] Resume the approved implementation plan directly on `main` with
  ponytail-minimal code, strict TDD, subagent-driven execution, task-level
  reviews, grouped commits, and ongoing diary updates. Do not create a branch
  or worktree and do not delete anything from the old assignment folder.
- [sources] Re-read `PRD.md`, `diary.md`, and
  `2026-08-03-gridscope-implementation.md`; checked repository status and
  history. `main` and `origin/main` both point to `0ae99fa`, and no
  implementation task has started.
- [decision] The latest commit instruction supersedes every earlier cadence:
  create and push one commit directly to `main` after each completed and
  reviewed task. Because Tasks 1 and 2 began under grouped-checkpoint rules,
  reconstruct separate Task 1 and Task 2 commits after Task 2 review, then use
  one commit and push per Task 3-6. Routine commit approval is not requested.
- [decision] The user supplied and finalized `Model_wise_implementation.md`:
  Terra medium for Tasks 1, 10, and 15; Terra high for Task 8; Sol high for
  Tasks 2-7, 9, and 11-13; and Sol for Task 14, escalating to `xhigh` only
  when a failure is difficult.
- [follow-up] Execute Task 1 from the approved plan and retain task evidence in
  the plan-scoped SDD ledger.
- [output] Task 1 produced the pinned FastAPI/SQLAlchemy and React/Vite
  foundation, Docker multi-stage build, default `db`/`web` Compose stack,
  opt-in frontend-test profile, health/readiness routes, and static frontend.
- [verification] Task 1 review found the implementation spec-compliant and
  approved with no Critical or Important issues. Fresh controller checks
  passed: backend health tests 2/2, live health JSON, frontend HTTP 200, and
  the tools-profile Vitest command. npm's two reported transitive
  vulnerabilities remain a deferred review item pending package/severity and
  reachability evidence.
- [finalized] Task 1 is complete and awaits reconstruction as its own commit
  after Task 2's review, due the later per-task commit instruction.
- [request] Limit the current execution session to Tasks 1-6. Stop after Task
  6 is reviewed, freshly verified, recorded, and included in the Tasks 5-6
  grouped commit; leave Tasks 7-15 for a later session.
- [request] After Task 6, stop the Docker containers if they are no longer
  needed. Preserve the database volume and images; do not use `down -v` for
  this final shutdown.
- [decision] The user overrode the prior model routing for the active session:
  every new implementation, fix, and review subagent through Task 6 uses
  GPT-5.6 Terra with `high` reasoning.
- [decision] Refine the model policy: retain Terra high by default. GPT-5.6
  Sol is reserved for genuinely important tasks and requires explicit user
  approval before dispatch.
- [output] Task 2 added the complete initial PostgreSQL schema, Alembic
  migration, deterministic hidden-truth network generator, corrupted exported
  registry, and advisory-lock-protected idempotent migration/seed startup.
- [decision] Replace Task 1's `app/db.py` module with the planned `app/db/`
  package while preserving the existing engine/session imports, allowing the
  schema models to live under `app/db/models/` without duplicate database
  modules.
- [verification] Task 2's initial review found four Important issues. Two fix
  rounds corrected the high-end pole-count allocator and added genuine
  empty-database idempotency, complete schema-definition, and battery/RSSI
  contract coverage. Scoped re-review marked all findings addressed with no
  new breakage. Fresh controller verification passed 16/16 backend tests and
  confirmed 4,200 persisted poles.
- [finalized] Task 2 is complete and ready for its own commit and push after
  reconstructing the earlier Task 1 commit required by the latest cadence.
- [output] Task 3 added registry validation, DT-scoped graph access, sparse
  geographic MST inference, calibration metrics/gating, and seed integration
  for inferred topology.
- [decision] Use virtual transformer roots in memory while persisting only
  pole-to-pole topology edges. For invalid registry components, retain the full
  hidden-truth edge set as `hidden_truth`, mark it invisible, and record
  `calibration_bucket=registry_quarantined`; this keeps truth and quarantine
  provenance independently auditable without changing the schema.
- [verification] Task 3 review found bounded-fallback, registry-root,
  quarantine, and coverage defects. Two TDD fix rounds resolved them. Final
  scoped review was clean; fresh controller checks passed 15 topology tests
  and 32 backend tests.
- [finalized] Task 3 is ready for its individual commit and push.
- [output] Task 4 added a minimal durable telemetry intake path: canonical
  fingerprinted append, active-assignment quarantine, per-device boot/sequence
  ordering, batch replay with row-level retry isolation, API routes, and a
  lifespan-managed worker.
- [decision] Keep Task 4 limited to immutable inbox and stream-state effects;
  evidence and incident effects remain for their planned later tasks. Within an
  active epoch, sequence order wins over device-clock jitter, while pre-boot
  retries and stale boots are audit-only.
- [failure] The poison-row regression initially exposed a stale ORM identity
  after the retry SQL update. The database state changed but the loaded event
  remained `pending`; synchronize the update session so callers and later work
  see `retry` consistently.
- [verification] TDD began with the telemetry package absent (expected import
  failures). Final Docker verification passed `pytest backend/tests/telemetry
  -q` (8 passed) and `pytest backend/tests -q` (40 passed); an unknown-device
  HTTP POST returned 404 without acknowledgement.
- [finalized] Task 4 implementation is complete and left unstaged for
  independent task-level review and controller-owned commit/push.
- [review-fix] Task 4 review found that ordering all unprocessed rows by
  `received_at` lets an older poison retry consume every `limit=1` batch, and
  that the original replay test never crossed a committed intake/session
  boundary.
- [decision] Preserve the existing schema and give `pending` rows durable
  priority over `retry` rows in the claim query. Retries still drain once
  current pending work is exhausted, while a malformed oldest row cannot starve
  later valid telemetry. Use committed intake and two fresh worker sessions for
  restart-equivalent exactly-once coverage; cleanup removes its temporary
  durable rows after the assertion.
- [verification] The new `limit=1` regression failed before the ordering change
  (second batch reprocessed the poison row), then passed. Fresh Docker checks
  passed worker replay tests 3/3, telemetry tests 9/9, and the full backend
  suite 41/41.
- [finalized] Task 4 review fixes are complete and remain unstaged for
  re-review and controller-owned commit/push.
- [output] Task 5 adds deterministic pole evidence transitions and DT-scoped
  Tier-1 candidates. Current `power_lost` is direct dark evidence; live events
  are direct live evidence; heartbeat expiry becomes `unknown_silent` only.
  Candidates settle for 30 seconds, cap corroboration at 45 seconds, and turn
  uncorroborated reports into a device-health outcome at 120 seconds.
- [decision] Reuse the Task 2 persistence schema. Persist the database's
  existing `device_suspect` state vocabulary while exposing `device_issue` as
  the candidate classification, avoiding a speculative migration before Task 6
  owns localization and classification.
- [failure] The first replay regression cleanup deleted telemetry before its
  new evidence FK, leaving one local test heartbeat row after rollback. The
  test now deletes only evidence sourced by its temporary event first; the
  already-created known test row, linked evidence, and stream state were
  removed explicitly before the final regression.
- [failure] Final inspection found that evidence restoration reused the
  database update timestamp as a pre-fault heartbeat time. A focused replay
  regression failed with the current wall-clock value; persist and restore the
  accepted event timestamp in evidence JSON instead.
- [verification] TDD first failed with missing detection modules, then caught
  the default heartbeat-freshness edge case and the worker's initially absent
  domain effect. Fresh Docker verification passed evidence, candidate, and
  telemetry checks: 17 passed; the full backend suite passed 49 tests.
- [review-fix] Task 5 review found that Tier-2 correlation could decide before
  the settle window, late live evidence could alter the fixed window, persisted
  heartbeat evidence never expired, and device issues left direct-dark evidence
  consumable by later localization.
- [decision] Keep timing derived from the candidate's immutable first receive
  time: do no topology correlation before +30 seconds and consider live support
  only through +45 seconds. The production loop supplies wall-clock time for
  expiry/evaluation; the batch helper accepts an optional time to keep replay
  tests deterministic. Device-health outcomes retain the event source and prior
  provenance in JSON metadata while converting direct dark state to the schema-
  valid `device_suspect` value.
- [verification] New tests first failed for early dark/live promotion, late
  live-child/parent correlation, absent durable heartbeat expiry, and dark
  evidence left after isolated/live-child device issues. Fresh Docker checks
  passed detection plus telemetry tests 23/23 and the full backend suite 55/55.

### 2026-08-04

- [output] Task 6 adds pure deterministic localization, scope classification,
  schedule matching/cache, navigation/PIN resolution, and categorical
  confidence. Tier-2 candidates now expose their supported boundaries for the
  later incident workflow without creating incidents themselves.
- [decision] Keep the new domain layer intentionally in-memory and duck-typed:
  Tasks 2-5 already provide the database schema and evidence state, while Task
  7 owns incident persistence. Exact inferred spans require an explicit
  calibrated gate; otherwise an adjacent boundary remains a corridor.
- [decision] Schedule cache keeps versioned successful snapshots, marks the
  retained snapshot stale on feed failure, and never changes its outage timing
  window. A stale but still-applicable snapshot only lowers confidence.
- [failure] Rebuilding the web image failed because Docker Desktop could not
  resolve Docker Hub's Python image metadata. The existing required container
  remained available, so current Task 6 sources were copied into it solely for
  Python-path verification; no image, database, or volume was changed.
- [verification] TDD began with five missing Task 6 module import failures;
  the candidate integration then failed as expected before it exposed a
  boundary, and the schedule snapshot test failed before snapshot support was
  added. Final current-source Docker checks passed detection 19/19 and the full
  backend suite 65/65; `git diff --check` passed.
- [finalized] Task 6 implementation is complete and left unstaged for
  independent task-level review and controller-owned commit/push.

### 2026-08-04

- [review-fix] Task 6 review found that candidate localization silently
  defaulted to registry topology, schedule polling used an empty mock, scope
  matching was too broad, DT classification ignored live contradictions,
  confidence trusted an arbitrary inferred flag, and higher-scope navigation
  was not asset-aware.
- [decision] Carry graph topology source into localization and require measured
  inferred precision >=90% for an exact inferred span. Task 3 does not persist
  that measured report on edges, so database-backed inferred candidates remain
  conservatively corridor-only until one is supplied. Poll Task 2
  `scheduled_outages` rows; classify and match only equivalent DT/feeder scope.
- [decision] A DT requires at least two directly observable, dark first-level
  branches with no fresh live branch; a single branch remains span/ambiguous.
  Feeder navigation is the centroid of its transformer assets, while DT uses
  its registry coordinate and still resolves PIN from member poles.
- [verification] New red tests caught all six review findings, including the
  real transformer `feeder_id` centroid field. Final exact Docker checks passed
  `pytest backend/tests/detection -q` 28/28 and `pytest backend/tests -q`
  74/74; `git diff --check` passed. Docker Hub DNS still prevented an image
  rebuild, so the source was safely copied into the existing web container and
  installed editable only for verification.
- [finalized] Task 6 review fixes are complete and remain unstaged for
  independent re-review and controller-owned commit/push.

### 2026-08-04

- [review-fix] Follow-up review found that operational candidate evaluation
  bypassed the lifespan-owned schedule cache, feeder quorum could not be
  reached across DT candidates, branch coverage treated late live telemetry as
  contradictory, and feeder PIN fallback skipped member-pole registry PINs.
- [decision] The worker passes the current cache snapshot through every batch;
  an empty stale snapshot is used before the first fetch so the operational path
  never bypasses cache semantics. Direct `evaluate_candidate` calls retain the
  database fallback for focused tests. Feeder coverage aggregates prior
  DT-qualified actionable candidates on the same feeder; it becomes reachable
  on the normal next worker pass without inventing cross-DT state.
- [decision] DT branch coverage considers only candidate-window evidence
  received from onset through 45 seconds. Feeder PIN lookup limits candidates
  to poles belonging to transformer assets on that feeder before offline
  inference.
- [verification] Red tests exposed the feeder PIN fallback and an additional
  sibling-branch promotion gap; the latter was fixed so independent DT branches
  can become a candidate. Final exact Docker checks passed
  `pytest backend/tests/detection -q` 30/30 and `pytest backend/tests -q`
  78/78; `git diff --check` passed. The existing synced/editable web runtime
  was retained because Docker Hub DNS still prevents image rebuilding.
- [finalized] Task 6 follow-up fixes are complete and remain unstaged for
  independent re-review and controller-owned commit/push.

### 2026-08-04

- [review-fix] Final Task 6 review found feeder aggregation could combine
  otherwise qualified DT candidates from unrelated correlation windows.
- [decision] Filter durable same-feeder actionable DT candidates by the current
  candidate's immutable `first_received_at` through `+45s` hard deadline before
  applying feeder quorum. Earlier or later DT outages remain independent.
- [verification] A DB-backed regression created current, 46-second-old, and
  46-second-late DT candidates that previously met quorum; it failed before the
  timing input/filter and passed afterward. Exact Docker checks passed worker
  replay 11/11, detection 30/30, and full backend 79/79; `git diff --check`
  passed. Existing source-synced editable runtime remains necessary while
  Docker Hub DNS prevents image rebuild.
- [finalized] Task 6 feeder-window fix is complete and unstaged for focused
  re-review and controller-owned commit/push.

### 2026-08-04

- [output] Task 7 adds active-boundary incident correlation, immutable incident
  boundaries/evidence, audited ticket transitions, and telemetry-driven
  restoration verification.
- [decision] Reuse the existing incident tables and candidate worker path:
  promotion changes a candidate to `promoted` after an idempotent upsert, so
  replay cannot create duplicate active tickets or transition effects. Keep
  closed incidents immutable; a later matching boundary receives a new active
  incident through the partial unique correlation key.
- [failure] The first worker-promotion test exposed UUID values in a JSON
  candidate-span field. Persist the display representation as strings while
  retaining UUIDs for relational fields. The restoration worker test then
  exposed that `energized` lives in telemetry JSON rather than a model column;
  restoration now uses the same payload fallback as detection.
- [failure] A final full-suite run exposed an order-dependent promotion test:
  reused device streams made its fixed sequence stale. The test now selects a
  deterministic visible registry span whose two device streams are unused,
  preserving the real worker path without test-order coupling.
- [verification] TDD began with missing incident-module imports, then a
  candidate-promotion red test and a restoration-worker red test. Focused
  Docker checks passed incidents/detection/telemetry 55/55 and the complete
  backend suite 87/87; `git diff --check` passed.
- [finalized] Task 7 implementation is complete and left unstaged for
  independent review and controller-owned commit/push.

### 2026-08-04

- [review-fix] Task 7 review required durable restoration scope, feeder
  roll-up, protected system transitions, refinement history, and relapse
  linkage.
- [decision] Use existing `incident_evidence.evidence` for prior-dark branch
  scope and immutable `ticket_events` for queryable feeder supersession,
  location refinement, and relapse links. This preserves all historical rows
  and avoids a speculative migration. Only boot/power-restored events prove
  restoration; heartbeat does not. A missing/unknown boundary reporter lowers
  confidence if another direct restoration report remains, instead of blocking
  closure indefinitely.
- [verification] New regressions first failed for all five review findings and
  the unavailable-reporter edge. Exact Docker checks passed incidents,
  detection, and telemetry 61/61; full backend 93/93; `git diff --check`
  passed.
- [finalized] Task 7 review fixes are complete and remain unstaged for a fresh
  task-level re-review.

### 2026-08-04

- [review-fix] Final Task 7 review required stability from the final required
  reporter, boundary-scoped restoration contradictions, real worker feeder
  identity, and removal of the importable transition authority.
- [decision] Compute the 30-second restoration window from the latest required
  boundary/branch boot-or-restored proof and query direct dark telemetry after
  that time. Restrict proof and contradiction state to the persisted incident
  boundary subtree and recorded dark branches; unrelated transformer branches
  cannot block a ticket. Derive feeder identity from the persisted transformer
  during candidate promotion. Keep verified/closed implementation private to
  restoration rather than expose a general system-transition function.
- [verification] New staggered-proof, mid-window-dark, unrelated-branch,
  real-worker-feeder, and capability tests passed. Exact Docker checks passed
  incidents/detection/telemetry 65/65 and full backend 97/97; `git diff
  --check` passed.
- [finalized] Task 7 final fixes are complete and left unstaged for final
  independent review.

### 2026-08-04

- [review-fix] Final Task 7 review required one feeder-scoped correlation key
  for real worker promotion and contradiction gating from credible evidence
  only.
- [decision] Feeder promotion now builds a feeder-only hypothesis from persisted
  transformer/feeder assets, with no DT/pole boundary identity. Restoration
  ignores raw quarantined, stale/audit-only, or retry messages: a contradiction
  must be the current `confirmed_dark` state sourced by a processed direct
  `power_lost` event.
- [verification] New worker-path feeder and raw-versus-processed dark tests
  first failed, then passed. Exact Docker checks passed
  incidents/detection/telemetry 66/66 and full backend 98/98; `git diff
  --check` passed.
- [finalized] Task 7 remaining review fixes are complete and left unstaged for
  re-review.

### 2026-08-04

- [output] Task 8 adds the non-simulator operational API: paginated incident,
  planned-operation, and device-health reads; selected-incident GeoJSON;
  ticket lifecycle actions; workflow readiness; typed API schemas; and a
  generated OpenAPI document.
- [decision] Keep read models as small SQLAlchemy query helpers over the
  existing Task 2-7 tables. The API reuses the established workflow transition
  service, so lifecycle validity and immutable ticket auditing have one owner.
  Readiness treats the in-process worker task, seeded poles, and inbox age as
  workflow dependencies while `/health` remains liveness-only.
- [failure] Docker BuildKit could not export a rebuilt image because a local
  parent snapshot was missing. The existing image started safely without a
  rebuild; syncing current source to its installed package path enabled the
  required test run without changing the persistent PostgreSQL volume. A first
  conflict response also contained raw datetimes; encoding the typed 409 body
  fixed the serialization failure.
- [verification] Contract tests began RED with five absent-route/readiness
  failures, then passed 6/6 after implementation. `python
  scripts/export_openapi.py` generated `openapi.json` with all implemented
  PRD Section 15 non-simulator paths. Full Docker backend regression passed
  104/104; `git diff --check` passed for tracked changes.
- [finalized] Task 8 is complete and left unstaged for independent review and
  controller-owned commit/push.

### 2026-08-04

- [review-fix] Task 8 review found list-read N+1 queries and leaked geometry,
  unbounded evidence/event N+1 reads, DT/feeder geometry reduced to a fallback
  point, and undocumented mutation failures.
- [decision] Keep the list compact and fetch inferred-topology flags in one
  aggregate query. Detail evidence is bounded to 100 rows with page metadata,
  class counts, and a single event join. DT/feeder GeoJSON exposes the actual
  selected transformer and pole assets. Mutation decorators explicitly declare
  the 404/409 typed error envelope already returned by the service.
- [failure] The first grouped evidence-count implementation attempted to cast a
  SQLAlchemy result directly to `dict`; materializing its rows fixed it.
- [verification] New regressions first failed for all four review findings.
  Docker API tests passed 10/10, full backend tests passed 108/108, and
  regenerated OpenAPI includes mutation 404/409 responses. The restarted web
  container serves readiness and the same OpenAPI contract; `git diff --check`
  passed.
- [finalized] Task 8 review fixes are complete and left unstaged for fresh
  independent re-review.

## Future Entry Format

### YYYY-MM-DD

- [request] What was asked.
- [question] Decision question and answer, if one was raised.
- [sources] Files, links, or data checked.
- [decision] What was chosen and why, if a choice was made.
- [output] What changed or was produced.
- [verification] What was checked and the result.
- [finalized] Final outcome, when the work is closed.
- [follow-up] Next material action, if work remains.
