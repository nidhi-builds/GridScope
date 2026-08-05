# GridScope Claude Handoff

## Start here

- Repo: `C:\Users\NIDHI\OneDrive\Desktop\My Projects\GridScope`
- Remote: `https://github.com/nidhi-builds/GridScope.git`
- Branch: `main`; do not create a branch or worktree.
- Latest pushed commit: `1feefa5 feat: add incident detail ticket workflow`.
- Completed work: Tasks 1-13 are implemented. Task 13 is committed locally and
  awaits a backend test run and push on the Windows host.
- Next task: Task 14.

Read these before editing:

1. `PRD.md`
2. `diary.md`
3. `2026-08-03-gridscope-implementation.md`
4. `AGENTS.md`
5. `ARCHITECTURE.md` if the task touches cross-service behavior

## User rules

- Use Ponytail-style minimal changes: small, direct, no speculative abstractions.
- Use the Superpowers `executing-plans` skill when resuming task execution, if
  available. Read its `SKILL.md` before acting.
- Use focused TDD. Add the smallest useful failing test first for real behavior.
- Commit and push after each completed task.
- Keep `diary.md` updated for major decisions, failures, and verification.
- Do not delete or modify `assignment/` without explicit approval.
- Do not use GPT-5.6 Sol without user approval.
- User requested Terra medium for Task 13; use higher reasoning only when needed.

## Do not stage unless asked

These are expected local/untracked items and should stay out of commits:

- `.codex/`
- `2026-08-03-gridscope-implementation.md`
- `AGENTS.md`
- `PRD-claude.md`
- `graphify-out/`

## Graphify

- `graphify-out/` exists and AGENTS.md says to use graphify for codebase questions.
- For codebase questions, run `graphify query "<question>"` first.
- Use `graphify path "<A>" "<B>"` for relationship checks and `graphify explain "<concept>"` for focused concepts.
- After code edits, run `graphify update .`.
- Known issue: `graphify update .` has repeatedly failed with Windows `[WinError 5] Access denied` file locks. If it fails, document it in `diary.md` and continue. Do not stage `graphify-out/`.

## Testing notes

- Docker may be needed for backend/database tests. Start Docker Desktop if required.
- Backend DB tests usually need the existing Docker network:

```powershell
docker run --rm --network gridscope_default -v 'C:\Users\NIDHI\OneDrive\Desktop\My Projects\GridScope\backend:/app/backend' -e PYTHONPATH=/app/backend gridscope-web pytest <tests>
```

- Frontend tests/build should avoid Windows-mounted `frontend/node_modules` because Rollup native binaries can mismatch. Use a clean disposable Linux container:

```powershell
docker run --rm -v 'C:\Users\NIDHI\OneDrive\Desktop\My Projects\GridScope\frontend:/src:ro' -w /work node:22.14.0-alpine sh -c "mkdir -p /work && tar --exclude=node_modules -C /src -cf - . | tar -C /work -xf - && npm ci && npm test -- --run <tests>"
```

For build, use the same pattern and replace the final command with `npm run build`.

## Task 11 summary

- Added default React `/operations` workspace.
- Added incident queue states, sorting, filtering, responsive Leaflet map, and accessible controls.
- Polling is visibility-aware, abortable, and preserves last good data on transient failure.
- Map fetches only selected-incident GeoJSON and clears stale geometry on selection changes.
- Planned filter uses real `planned_operations.incident_id`.
- FastAPI static serving now returns SPA routes while keeping missing `/api` routes as 404.
- Verification: operations frontend tests `8/8`, frontend build passed, backend static/operations tests `6/6`, `git diff --check` passed.

## Task 12 summary

- Added selected incident detail view in the operations workspace.
- Added typed incident-detail API client calls and ticket actions: acknowledge, assign, report resolved.
- Ticket action failures parse typed 409 envelopes and show operator-safe rejection text.
- Successful ticket actions immediately refresh the parent operations data.
- Detail view shows affected count provenance, location confidence reasons, boundary/path data, evidence details, topology source/calibration, schedule overlap, immutable hypothesis history, ticket history, and bounded AI explanation tabs.
- Verification: `frontend/tests/incident-detail.test.tsx` passed `4/4`, clean Vite build passed, `git diff --check` passed, independent release review was READY.

## Task 13 summary

- Added the `Demo` simulator view (`/simulator`) plus `/planned-operations`,
  `/device-health`, and `/system-health`.
- `App.tsx` routes on `window.location.pathname`; the icon rail now carries text
  labels. No router dependency was added.
- Simulator drives only public Task 9 endpoints: scenario presets, deterministic
  seed, start/repair/reset, expected-vs-actual, detection and restoration
  elapsed time, generated-event stream with delivery outcome, hidden ground
  truth confined to this route, and incident links labelled with the run ID.
- Unobservable scenarios render `Unobservable by design`, never mismatch text.
- Four additive read-only backend fields/routes: `readiness.ai`,
  `planned-operations.end_grace_minutes` and `source_updated_at`,
  `device-health.mismatch_events` and `stale_replay_events` (counted per page
  only), and `GET /simulator/runs/{id}/events` plus `incident_ids` on the run
  payload. No schema or write path changed.
- Per-device duplicate rate is deliberately not shown: duplicates are rejected
  at ingest by fingerprint and never persisted. The UI states this.
- Verification: new simulator tests `4/4`, health-page tests `5/5`, full
  frontend suite `21/21`, `tsc -b && vite build` passed. Backend pytest could
  not run (no Docker/PostgreSQL in the agent environment).

## Next work

Before Task 14, on the Windows host: run the backend suite with Docker up
(`test_readiness.py`, `test_operations.py`, simulator API tests), run
`graphify update .`, and push the Task 13 commit to `main`. Then continue with
Task 14 from `2026-08-03-gridscope-implementation.md`.

Pre-existing working-tree noise to leave alone: CRLF-only edits in
`.env.example`, `Dockerfile`, `Model_wise_implementation.md`,
`backend/app/config.py`, and `backend/tests/test_health.py`. `tests/operations.test.tsx`
also logs one pre-existing unhandled error (`detail.boundary` undefined) that
reproduces on `1feefa5`.
