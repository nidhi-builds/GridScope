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
