# All-in-One ARR

A small, self-hosted service that keeps a **Trakt list in sync with Jellyseerr**
and — the key part — **removes an item from the Trakt list once Radarr/Sonarr
have imported it**. It uses **official REST APIs only** (no scraping).

This is the plugin **core** plus the first module, **`traktsync`**. Future
modules (`bandwidtharr`, `deletearr`, `neutarr`) drop into `backend/modules/` and
auto-load — see [Adding a module](#adding-a-module).

> **DRY_RUN is ON by default.** Until you turn it off, the service only *logs*
> what it would request in Jellyseerr and remove from Trakt. Verify the loop
> first, then flip DRY_RUN off.

## How it works

1. Poll the configured Trakt list every `SYNC_INTERVAL_MIN` minutes and mirror
   each item into SQLite (storing **both** TMDB and TVDB ids).
2. For each item not already handled, check Jellyseerr; if it is not already
   requested/available, create a request.
3. (Your existing Jellyseerr → Radarr/Sonarr → download/import flow runs.)
4. On the Radarr/Sonarr **On-Import** webhook, look the item up by TMDB
   (Radarr) or TVDB (Sonarr) and **remove it from the Trakt list**.
5. A **nightly reconciliation** job (03:00 local) removes anything the webhook
   missed by asking Jellyseerr which tracked items are now *Available*.

## Architecture

```
backend/
  core/
    config.py        # typed env config (pydantic-settings), secret masking
    db.py            # SQLite schema + helpers (WAL, thread-safe)
    scheduler.py     # APScheduler 4 wrapper (interval + cron)
    webhooks.py      # single /webhook router; modules register handlers
    registry.py      # discovers & loads modules, calls setup()
    context.py       # AppContext shared with modules + live DRY_RUN flag
    api.py           # dashboard JSON endpoints (/api/*)
    app.py           # FastAPI factory + lifespan wiring + SPA serving
    clients/
      trakt.py       # device auth, token refresh, list read/remove
      jellyseerr.py  # status check, create request
      arr.py         # defensive Radarr/Sonarr webhook parsing
  modules/
    traktsync/       # the first module: poll/request, webhook remove, reconcile
  main.py            # entrypoint: `uvicorn main:app --app-dir backend`
  pyproject.toml     # packaging + pytest + coverage config
  tests/             # backend test suite (100% coverage)
frontend/            # React + TypeScript + Tailwind (Vite) dashboard
Dockerfile, docker-compose.yml, .env.example   # project root
```

> **Note:** the brief sketched a `aio-arr/` project folder; since a hyphenated
> name is not an importable Python package, the backend is exposed as the
> `core/` and `modules/` packages inside `backend/`, and the run target is
> `main:app` (run from the repository root with `--app-dir backend`).

## Configuration

All configuration is via environment variables (see `.env.example`). Copy it:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `TRAKT_CLIENT_ID` | – | Trakt application client id (**required**) |
| `TRAKT_CLIENT_SECRET` | – | Trakt application client secret (**required**) |
| `TRAKT_USER` | `me` | Your Trakt username, or `me` |
| `TRAKT_LIST_ID` | `watchlist` | A list slug/id, or `watchlist` |
| `JELLYSEERR_URL` | – | Base URL of Jellyseerr (**required**) |
| `JELLYSEERR_API_KEY` | – | Jellyseerr API key (**required**) |
| `SYNC_INTERVAL_MIN` | `15` | Poll interval in minutes |
| `WEBHOOK_PORT` | `3223` | Port the service listens on |
| `DRY_RUN` | `true` | Log-only mode; no real requests/removals |
| `TZ` | `Europe/Istanbul` | Timezone for the scheduler |
| `LOG_LEVEL` | `INFO` | Log level |
| `DB_PATH` | `data/aio-arr.db` | SQLite path (persist via volume) |
| `TOKEN_STORE_PATH` | `data/trakt_tokens.json` | Trakt token store (persist via volume) |

Create the Trakt application at <https://trakt.tv/oauth/applications> to obtain
the client id/secret.

## Running with Docker (recommended)

```bash
cp .env.example .env   # then fill in the required values
docker compose up --build
```

The dashboard is then at <http://localhost:3223/>. The `./data` volume persists
the SQLite database and the Trakt token store across restarts.

### One-time Trakt device authorisation

On first start (no saved token) the logs print a code and URL:

```
Trakt authorisation required: visit https://trakt.tv/activate and enter code ABCD-1234
```

Open the URL, sign in, and enter the code. The token is saved to
`TOKEN_STORE_PATH` (inside the `data/` volume) and refreshed automatically, so
you will not need to re-authorise on restart. The dashboard header shows
**Connected** once it succeeds.

### Adding the Radarr/Sonarr webhook

In Radarr and Sonarr: **Settings → Connect → + → Webhook**

- **URL:** `http://<this-host>:3223/webhook/arr`
- **Method:** POST
- **Triggers:** enable **On Import** (a.k.a. *On File Import* / *On Download*)

On the first webhook received, the full raw JSON payload is logged so you can
confirm the shape; parsing is defensive across Radarr/Sonarr versions.

### Turning DRY_RUN off

While DRY_RUN is on, the service **persists no irreversible state**: it logs
`would_request` / `would_remove` to the activity feed but leaves items in their
`synced` state and never marks them `requested` or `removed`. This means you can
verify the loop and then simply switch DRY_RUN off — the next poll/webhook will
perform the real requests and removals; **no database reset is required**.

Once the logs show the loop doing the right thing, either flip the **DRY_RUN**
toggle in the dashboard (takes effect immediately, runtime-only) or set
`DRY_RUN=false` in `.env` and restart for a persistent change.

## Local development

Backend (run from the repository root so `.env`, `data/` and `frontend/dist`
resolve as they do in Docker):

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e "./backend[dev]"
uvicorn main:app --app-dir backend --reload --port 3223
```

Frontend (Vite dev server proxies `/api` and `/webhook` to port 3223):

```bash
cd frontend
npm install
npm run dev
```

For a production-style single-origin run, build the frontend first
(`cd frontend && npm run build`), then start the backend **from the repository
root** (as in the Backend block above) so it resolves the bundle:

```bash
uvicorn main:app --app-dir backend --port 3223
```

The FastAPI app then serves `frontend/dist` at `/`.

## Tests

The Python backend has **100% test coverage**, enforced in
`backend/pyproject.toml`:

```bash
pip install -e "./backend[dev]"
cd backend && pytest   # runs with --cov-fail-under=100
```

Coverage spans Trakt list parsing, the TMDB/TVDB reverse mapping, the
remove-on-webhook lookup (mocked HTTP clients, DRY_RUN assertions), and
reconciliation.

The React frontend also has **100% test coverage** (Vitest + React Testing
Library on jsdom), enforced via a `thresholds: { 100: true }` gate in
`frontend/vite.config.ts`:

```bash
cd frontend
npm install
npm run test       # vitest run
npm run test:cov   # the same run with the 100% coverage gate
```

Coverage spans the typed API client, the TanStack Query hooks, the theme
provider, the layout and topbar, both pages, the route table, and the vendored
UI primitives. The single carve-out is `src/main.tsx` (the DOM bootstrap),
excluded from the coverage denominator as the direct analogue of the backend's
excluded `if __name__ == "__main__"` block.

Build the frontend to type-check it:

```bash
cd frontend && npm run build
```

## Endpoints

- `GET /health` – liveness probe.
- `GET /status` – item counts by status.
- `GET /api/status` – dashboard status (dry_run, trakt_connected, counts).
- `GET /api/items[?status=]` – tracked items.
- `GET /api/activity` – recent activity feed.
- `POST /api/sync` – trigger an immediate poll.
- `POST /api/settings/dry-run` – `{ "enabled": bool }` toggle.
- `POST /webhook/arr` – Radarr/Sonarr On-Import webhook.

## Adding a module

1. Create `backend/modules/<name>/__init__.py` exposing
   `setup(scheduler, app, ctx)` (sync or async).
2. Use `ctx` for the shared clients, database and config; register scheduled
   jobs via `scheduler.add_interval` / `scheduler.add_cron`, and webhook
   handlers via `ctx.webhooks.register(subpath, handler)`.
3. Drop the folder in `backend/modules/` — `backend/core/registry.py` auto-loads
   it on start-up.

### Frontend: adding a menu or component

- Add a shadcn component: `cd frontend && npx shadcn@latest add <component>`.
- Add a menu/route: extend the nav config in
  `frontend/src/components/layout/nav-config.tsx` and add a route in
  `frontend/src/App.tsx`.

## Notes & limitations

- Single Uvicorn worker by design: the scheduler runs in-process and SQLite
  uses WAL with a process-level lock. Multi-worker deployment is out of scope.
- APScheduler 4 is pre-release; all scheduler usage is isolated behind
  `backend/core/scheduler.py` so a downgrade to 3.x is a one-file change.
