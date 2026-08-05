# GridScope Handoff

## Current state

- Branch: `main`; Task 11 is complete in commit `6631a8a` and pushed.
- Last committed task: Task 11 (`6631a8a`).
- Tasks 1-12 are pushed after the Task 12 commit below.
- Do not create a branch/worktree. Never delete or modify `assignment/` without
  explicit approval. Keep `diary.md` updated for material decisions, failures,
  and verification.

## Task 11 delivered

- Default React workspace at `/operations`: status/backlog states, sortable and
  filterable incident queue, responsive Leaflet map, and accessible controls.
- Polling is visibility-aware, abortable, and retains last good data on a
  transient failure.
- The map fetches only selected-incident GeoJSON. Old geometry cannot render
  after selection changes.
- The planned filter uses only the real `planned_operations.incident_id` link;
  no scope heuristic was invented.
- FastAPI static serving now returns the SPA for browser routes such as
  `/operations`, but keeps `/api` and `/api/...` missing paths as 404s.

## Verification

- Clean disposable frontend container: `tests/operations.test.tsx` — **8 passed**.
- Clean disposable frontend container: `npm run build` — **passed**.
- Backend on `gridscope_default`: `test_static_frontend.py` and
  `test_operations.py` — **6 passed**.
- `git diff --check` — **passed**.
- The first raw backend Docker run could not resolve `db`; use
  `--network gridscope_default` for database tests.
- Windows-mounted `frontend/node_modules` can contain the wrong native Rollup
  binary. Use a clean disposable Linux container (copy source excluding
  `node_modules`, then `npm ci`) for frontend verification.

## Environment notes

- Docker Desktop may be off; start it before tests. Keep it running while UI
  work continues.
- Docker image source can be stale because local BuildKit is unreliable. For
  backend source tests mount `backend` at `/app/backend` and set
  `PYTHONPATH=/app/backend`.
- `graphify update .` is required after code edits by `AGENTS.md`. It last hit
  a Windows file lock (`WinError 5`); retry after the editor releases it. Do not
  stage `graphify-out/` unless explicitly asked.
- Keep the following pre-existing untracked files out of commits unless asked:
  `.codex/`, `2026-08-03-gridscope-implementation.md`, `AGENTS.md`,
  `PRD-claude.md`, and `graphify-out/`.

## Next work

- Task 12 is complete: selected detail, ticket actions with typed rejection,
  immediate workspace refresh, evidence/hypothesis provenance, and bounded
  English/Kannada explanation tabs. Final focused tests pass `4/4`, clean Vite
  build and `git diff --check` pass, and an independent release review is READY.
- Task 13 is next; use Terra medium as requested.
- User requested Terra medium for Task 13, with
  careful credit use. Prefer Ponytail-minimal changes and focused TDD.
