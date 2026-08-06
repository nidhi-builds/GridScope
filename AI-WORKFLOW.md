# AI Workflow

How this was actually built.

## Tools, and what each did

| Tool | Used for |
|---|---|
| **OpenAI Codex (GPT-5.6)** | Tasks 1–12: schema and seed, topology inference and calibration, telemetry ingestion, evidence tiers, localization and classification, incident workflow and restoration, operational APIs, the simulator, the AI explanation feature, and the operator console |
| **Claude (Opus)** | Tasks 13–14 and the final hardening pass: the simulator and health UI, the end-to-end and load test suites, the measurement runners, the performance investigation, the live network map, client-side routing, and these documents |
| **Superpowers** (`executing-plans`, SDD) | The execution harness: turned each plan task into a brief, a patch, a review diff and a report, and carried context across a mid-project model switch |
| **Ponytail** | A standing constraint on change size — small, direct, no speculative abstractions |
| **Graphify** | A local code-knowledge graph for navigating the codebase without re-reading files |

Model routing was decided per task in advance and recorded in
`Model_wise_implementation.md` — higher-reasoning settings for the algorithmic
work (topology inference, evidence, localization, restoration), lower for
scaffolding and UI. The point was to spend reasoning where correctness was
hardest, not uniformly.

Every task followed the same loop: write the smallest useful failing test first,
implement, verify, record the result in `diary.md`, commit, push. `diary.md` is
the unedited working log — decisions, failures and verification in the order they
happened, including the wrong turns.

## The two skills that shaped the work

**Superpowers — `executing-plans` and spec-driven development.** This is the
harness the whole build ran inside. Rather than handing a model a task and taking
whatever came back, each task in
`2026-08-03-gridscope-implementation.md` was expanded into a brief, implemented as
a patch, reviewed as a diff, and closed with a written report. Those artefacts are
in `.superpowers/sdd/` — roughly four files per task, kept for every one of the
fourteen.

Three things it bought that a plain prompt loop does not:

- **A review step that is not the author.** The patch and the review are separate
  passes over the same change. Several of the rewrites in the section below —
  including the dark-root grouping bug — were caught at review, before the code
  reached a commit.
- **Survivable model handoff.** This project changed models mid-stream, from Codex
  at Task 12 to Claude at Task 13. The brief-and-report trail meant the second
  model could reconstruct intent from artefacts instead of guessing from source.
  That handoff is normally where an AI-built project loses the plot.
- **Resumability.** Every session started by reading the plan, the diary and the
  last task report. There was no session that began by re-deriving what the
  project was.

**Ponytail — minimal changes.** Stated at the top of every session: *small,
direct, no speculative abstractions.* Left alone, models produce factories, base
classes, config layers and helper modules nobody asked for, and each one is
individually defensible. The compounding cost is a codebase too large to hold in
mind — which matters enormously when the reviewer has to explain code a model
wrote. Repeating this constraint every session is the reason the application is
about 5,100 lines rather than three times that, and the reason the localization
logic is readable end to end in one sitting.

The two work against each other in a useful way. Superpowers adds process and
wants to generate artefacts; Ponytail keeps the artefacts from becoming the
product. Structure on the workflow, restraint on the code.

## What was delegated, and where the line was

**Delegated wholesale:** boilerplate and mechanical translation. SQLAlchemy model
definitions, Alembic migrations, Pydantic schemas, React component scaffolding,
CSS, the Docker and Compose setup, k6 script structure, and the repetitive parts
of test fixtures.

**Specified first, then rejected and re-specified until right:** anything where
being wrong is invisible. The typing was still the model's; the rule it was
implementing was not.

- The **dark-root reduction**. The first generated version grouped dark poles by
  transformer, which merges genuinely separate faults. The rule that actually
  works — a dark pole with no dark ancestor is a separate fault — came from
  reasoning about the radial topology, not from a model.
- The **silence-is-not-darkness rule**. Every early draft treated a lapsed
  heartbeat as evidence of an outage. It is the single most consequential rule in
  the system and it has to be stated explicitly, because the "obvious"
  implementation gets it backwards.
- The **90% calibration bar** for inferred topology. A model will happily emit a
  best-guess span with a confidence caveat. Deciding that an inferred exact span
  is worse than an honest corridor is a product judgement about which failure a
  crew can survive.
- The **confidence formula**, particularly including downstream coverage.
  Generated versions scored on contradiction alone; missing information degrades
  confidence too.

The line: models were trusted with *how* to express something and never with
*what* is true about the electrical network. Anything that decides whether a crew
gets dispatched was reasoned through first, then handed over to be written.

## Four times the AI was confidently wrong

### 1. Four wrong bottleneck diagnoses in a row

Sustained ingest measured 57 req/s against a 500 target. I proposed, in order:
the anyio threadpool, then fsync-bound commits, then connection-pool sizing.

- Raising the pool 15→60 and the threadpool 40→80 made it **worse**, 57.4→53.5.
- `pgbench` returned **899 tps** — the database was seventeen times faster than
  the application, killing the storage theory.
- The enlarged pool then exceeded PostgreSQL's `max_connections` and **broke 22
  tests**.

What caught it: measurement, not reasoning. `docker stats` captured *during* the
load run — the first attempt was taken after it finished and read 0.25% CPU,
which sent the analysis down a blind alley — showed the web process at 170–193%
CPU. That gave the real answer: ~16 ms of CPU per request in one Python process.

The lesson is in the ordering. Two commands, `pgbench` and `docker stats`, should
have come *before* any configuration change. Three of the four hypotheses were
plausible, internally consistent, and wrong.

### 2. A green test that tested nothing

The burst load test reported a clean pass: 5,000 events, zero unexpected
outcomes. It was silently testing nothing. The script picked the device from the
iteration index but set the duplicate's sequence to `index - 1`, so every
"duplicate" went out on a *different device* and the fingerprint never collided.
The duplicate-rejection path — a core correctness claim — was never exercised.

Caught by reading the metrics rather than the verdict: the `duplicate_rejected`
counter was absent from the output entirely. After the fix: 4,502 unique + 498
duplicates = 5,000 exactly.

A passing assertion that never executes is more dangerous than a failing one, so
the fix added a threshold requiring `duplicate_rejected > 0`. The test now fails
loudly if the path goes untested again.

### 3. Accuracy scored at 36% by a measurement bug

The accuracy campaign reported exact-span precision of 0.36 against a 95% gate —
which would have looked like a serious localization failure.

It was my scoring code. Sixteen of twenty-five scored runs were `tier_one` and
`real_fault_during_schedule`, scenarios that publish no `target_edge` in their
effect evidence. My code read the truth as `None` and counted "unknown" as
"wrong". The one scenario that does publish ground truth, `known_span`, hit
**9 out of 9**.

Caught by inspecting the raw JSON rather than the summary line. Unscorable runs
are now excluded and reported separately.

The pattern across all three: the AI-written *measurement* was less reliable than
the AI-written *system*. Every wrong number in this project came from the
instrument, not the thing being measured.

### 4. Eight tests broken by a test, then nearly blamed on a known bug

A new test for the network endpoint inserted one row and mutated two others
through the documented `session` fixture. Eight unrelated tests failed across
five suites. The obvious reading was the isolation defect already written up in
this repository — the failures matched its description exactly, and accepting
that explanation would have shipped a contaminating test.

What caught it was refusing the convenient answer: run the failing suites alone
on a clean database first. They passed, which located the fault in the new test
rather than in the old defect. The tests were rewritten to be read-only.

The lesson is about documented weaknesses specifically. A known issue in a
`DECISIONS.md` is a ready-made excuse for any failure that resembles it, and the
cost of a wrong attribution is that a real defect gets filed as a familiar one
and never fixed.

## Four real bugs the tests found

Written up because they show what the test suites bought, and three of them were
shipping:

1. **Simulator reset crashed** after any completed incident. `reset_runs` was
   written in Task 9 and clears six tables that reference incidents;
   `ai_explanations` was added in Task 10 and nobody went back. Found on the
   first Playwright run.
2. **The "API unavailable" screen was unreachable code.** The polling hook set
   `loading: !current.data` on failure, so a cold start with a dead backend had
   no data, stayed in `loading` forever, and showed "Loading…" permanently. In a
   control room that is the difference between "wait" and "call someone".
3. **The API froze every three seconds.** `run_worker` was declared `async` but
   called blocking database work directly on the event loop.
4. **The inbox drained too slowly**, leaving 11,161 events stranded 60 seconds
   after a load run.

None would have been caught by the tests that existed before Task 14. The
end-to-end and load suites paid for themselves on their first run.

## How much is AI-generated

**100% of the lines**, and close to **0% of the decisions that matter**.

About 5,100 lines of application code and 3,800 lines of tests. Not one line was
typed by hand. But the architecture, the failure-mode analysis, the
localization rules, the confidence design, and every judgement about which
failure mode is survivable were specified first and then implemented — and the
generated version was rejected and rewritten whenever it took the easy path.

The commit history shows the shape of it: one commit per completed task through
Task 14, then a run of `fix:` commits as the test suites — and a final review
pass over the operator console — found real defects.

## Prompts and practices that worked

**A written plan before any code.** `PRD.md` and a task-by-task implementation
plan with explicit interfaces, file lists and verification commands per task.
Every session started by reading the plan and the diary. Without this, model
handoffs lose the thread completely — and this project changed models mid-stream.

**"Write the smallest useful failing test first, for real behaviour."** The
qualifier does the work. Without "real behaviour" you get tests that assert a
function was called. The tests in `backend/tests/detection/` assert that a known
fault in a known topology produces the expected span, which is the only assertion
that matters.

**"Ponytail-style minimal changes: small, direct, no speculative abstractions."**
Repeated every session — see the skills section above for why this one mattered
more than any other single instruction.

**"Report the actual value and the bottleneck without weakening the
assertion."** Written into the plan before any measurement existed. It is why the
70 req/s miss is in the README rather than quietly rounded away — the instruction
was in place before there was anything inconvenient to report.

**Demanding evidence before acting on a diagnosis.** The turning point in the
performance investigation was refusing to change more configuration and running
`pgbench` and `docker stats` instead. Stated as a rule: *if the last three fixes
did not move the number, stop fixing and start measuring.*

## Where this leaves the review call

Every file in this repository can be explained, including the parts a model
wrote, because each was verified against a test that asserts real behaviour
before it was committed. The places to press hardest are the ones I would press:
`detection/localization.py` (the dark-root reduction and the exact-span
condition), `detection/confidence.py` (why coverage is in the formula), and
`topology/inference.py` (what the alternative margin means and why 90%).
