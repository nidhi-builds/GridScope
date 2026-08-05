# Deployment

Written for someone who has this repository and nothing else.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Engine | 24+ | Docker Desktop 4.30+ on Windows or macOS |
| Docker Compose | v2 | Bundled with Docker Desktop; `docker compose`, not `docker-compose` |
| Disk | ~3 GB | Images, the frontend build, and the PostgreSQL volume |
| RAM | 4 GB free | The seed builds 4,200 poles in one transaction |

Nothing else. No Python, no Node, no local PostgreSQL. Everything below runs in
containers.

Images are pinned: `postgres:18.3-alpine`, `python:3.13.7-slim`,
`node:22.14.0-alpine`.

## Run it locally

```bash
git clone https://github.com/nidhi-builds/GridScope.git
cd GridScope
docker compose up
```

That single command builds the frontend, builds the API image, starts
PostgreSQL, waits for it to be healthy, applies both Alembic migrations, seeds
the network, and serves the SPA and API on port 8000.

Add `-d` to run in the background. First build takes 3–5 minutes; subsequent
starts take about 20 seconds plus roughly 60 seconds of seeding on a fresh
volume.

## Verify it worked

```bash
docker compose logs --tail 5 web
```

Expect:

```
GridScope database ready: SeedSummary(substations=4, feeders=12, transformers=60, poles=4200, devices=3822)
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Then:

| Check | Command or URL | Expected |
|---|---|---|
| Liveness | <http://localhost:8000/api/v1/health> | `{"status":"ok"}` |
| Readiness | <http://localhost:8000/api/v1/ready> | `database`, `seed`, `worker` all `ready` |
| Operator console | <http://localhost:8000/operations> | Status bar, empty incident queue, map of Bengaluru |
| Demo view | <http://localhost:8000/simulator> | Scenario dropdown with 17 presets |
| API docs | <http://localhost:8000/docs> | Generated OpenAPI |

End-to-end smoke test — inject a fault and see a ticket:

```bash
curl -X POST http://localhost:8000/api/v1/simulator/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario_key":"known_span","seed":20260803}'

curl http://localhost:8000/api/v1/incidents
```

You should get exactly one incident with a `span` fault class, a PIN, navigation
coordinates and a confidence level. Reset afterwards with
`curl -X POST http://localhost:8000/api/v1/simulator/reset`.

## Environment variables

All have working defaults. `docker compose up` needs none of them set. Copy
`.env.example` to `.env` only if you want to override something.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `DATABASE_URL` | no | `postgresql+psycopg://gridscope:gridscope@db:5432/gridscope` | PostgreSQL connection. On a hosted platform, set this to the managed database URL. Must use the `postgresql+psycopg://` scheme, not `postgres://` |
| `APP_ENV` | no | `development` | Environment label |
| `LOG_LEVEL` | no | `INFO` | Python log level |
| `SEED` | no | `true` | Seed on startup if the database is empty. Idempotent — safe to leave on |
| `GEMINI_API_KEY` | no | empty | Enables AI explanations. **Without it the system runs normally** and uses the deterministic fallback |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Model for explanations |
| `WORKER_BATCH_SIZE` | no | `100` | Inbox events claimed per batch |
| `POLL_INTERVAL_MS` | no | `3000` | Worker idle poll, and the UI refresh interval |
| `DB_POOL_SIZE` | no | `10` | SQLAlchemy pool. Keep `(pool + overflow) × processes` under PostgreSQL `max_connections` |
| `DB_MAX_OVERFLOW` | no | `20` | Additional connections above the pool |
| `REQUEST_THREAD_LIMIT` | no | `80` | anyio threadpool for synchronous route handlers |

**Never commit a real `GEMINI_API_KEY`.** `.env` is gitignored; `.env.example`
holds names and safe defaults only.

## Deploying to a hosted platform

The same image runs unchanged. Requirements:

1. **One web service** built from this repository's `Dockerfile`. Health check
   path `/api/v1/health`.
2. **One managed PostgreSQL database.** Put its connection string in
   `DATABASE_URL`, rewriting the scheme to `postgresql+psycopg://`.
3. **Start command** identical to local, so migrations and seeding happen the
   same way:
   `sh -c "python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"`
4. **Exactly one Uvicorn process.** No `--workers`. The inbox worker and the
   schedule poller run inside the process and must have a single owner;
   duplicating them would double-process the inbox.
5. Confirm `/api/v1/ready` returns `seed: ready` and `worker: ready` before
   declaring success.

Free tiers that suspend on idle are acceptable — say so in the README so a
reviewer waits through the cold start rather than assuming the service is down.

## Troubleshooting

Every entry below was hit while building this, not imagined.

### `ImportError: cannot import name 'engine' from 'app.db' (unknown location)`

**Symptom.** The `web` container crash-loops immediately. `docker compose ps`
shows it restarting while `db` stays healthy.

**Cause.** A stale cached image that lost `app/db/__init__.py`, so Python treats
the directory as a namespace package. `docker compose up` reuses images and does
not rebuild.

**Fix.** `docker compose up -d --build`. If it survives that, `docker compose
build --no-cache web`.

**Why it hid for so long:** the backend test command bind-mounts `backend/` over
the image, so tests exercised fresh source while the image stayed broken. Rebuild
before any measurement or deployment run.

### Port 8000 already in use

**Symptom.** `Bind for 0.0.0.0:8000 failed: port is already allocated`.

**Fix.** Stop the other process, or map a different host port in `compose.yaml`:
`"8080:8000"`. The container port must stay 8000 — the health check targets it.

### `psycopg.OperationalError: FATAL: sorry, too many clients already`

**Symptom.** Many test errors at setup, or 500s under load. Everything worked
before you opened a second connection to the same database.

**Cause.** PostgreSQL's default `max_connections` is 100. Each process holds up
to `DB_POOL_SIZE + DB_MAX_OVERFLOW` connections. Two processes at 60 each
exceeds it.

**Fix.** Keep `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × concurrent processes` under
100, or raise `max_connections` on the database. The defaults here are sized so
the app plus a test runner both fit.

### Backend tests fail after running the load tests

**Symptom.** 8–22 failures in `test_correlation.py`, `test_worker_replay.py`,
`test_service.py`, `test_ingestion.py`. They pass on a fresh database.

**Cause.** Several backend tests assume a near-clean database. The load tests
persist tens of thousands of events, which the worker turns into evidence states
and candidates.

**Fix.** Reset between them:

```bash
docker compose down -v
docker compose up -d --build
```

Run correctness tests **before** load tests. This is a known limitation, not a
bug in the code under test.

### Frontend tests fail with a Rollup native binary error

**Symptom.** `Cannot find module @rollup/rollup-linux-x64-musl` when running
frontend tests with the host `node_modules` mounted.

**Cause.** `npm install` on Windows or macOS fetches a platform-specific
optional binary that does not match Linux inside the container.

**Fix.** Use the `tools` profile, which installs inside the container:
`docker compose --profile tools run --rm frontend-test`. Never mount host
`node_modules` into a Linux container.

### `POST /api/v1/simulator/reset` returns 500 or 503

**Symptom.** Intermittent, only under repeated automated resets.

**Cause.** The inbox worker can commit a ticket event for an incident between
reset's child delete and its parent delete, violating a foreign key.

**Fix.** Already mitigated — reset retries up to three times and returns `503`
with a clear message if it still loses. Retry the call. The proper fix is
`ON DELETE CASCADE` on the incident foreign keys; see `DECISIONS.md`.

### The public URL hangs on first load

**Symptom.** A free-tier deployment takes 30–60 seconds to answer after idling.

**Cause.** Container suspension, plus seeding if the database volume was
recycled.

**Fix.** Wait. Poll `/api/v1/ready` rather than the SPA — it returns `503` with a
readiness breakdown until seed and worker are both up.

### Seed appears to hang

**Symptom.** No log output for 30–60 seconds after `Running upgrade 0001 -> 0002`.

**Cause.** The seed writes 4,200 poles and 3,822 devices in one transaction.

**Fix.** Wait for the `SeedSummary` line. If it exceeds three minutes, the
database is likely under-resourced — raise memory or CPU.

### Ingest is slower than expected

**Symptom.** Sustained load plateaus around 70 requests/second with multi-second
latencies and zero errors.

**Cause.** Expected and documented. One Python process spends roughly 16 ms of
CPU per message. Nothing is lost; requests queue and the backlog drains.

**Fix.** None applied. See `DECISIONS.md` for the two routes considered.

## Reset to a clean state

Delete everything including the database volume:

```bash
docker compose down -v
docker compose up -d --build
```

Deterministic, so the rebuilt network is identical every time.

To clear only simulator activity while keeping the seed:

```bash
curl -X POST http://localhost:8000/api/v1/simulator/reset
```

Stop without destroying data:

```bash
docker compose down
```
