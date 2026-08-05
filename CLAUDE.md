# GridScope Handoff

## Current state

- Branch: `main`; Task 11 is complete in the pending commit.
- Last committed task: Task 10 (`fb0edfa`), with follow-up formatting commit
  `f51c60e`.
- Tasks 1-10 are pushed. Task 11 adds the `/operations` workspace and is ready
  to commit/push after this handoff file.
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

- Task 12 is the incident-detail workflow; Task 13 is simulator UI.
- User requested Terra high for Task 12 and Terra medium for Task 13, with
  careful credit use. Prefer Ponytail-minimal changes and focused TDD.
