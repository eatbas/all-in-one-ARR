# All-in-One ARR

A small, self-hosted service that keeps a **Trakt list in sync with Seer**
and — the key part — optionally **removes an item from the Trakt list once
Seer reports it available** (off by default; removes the list entry and
known Seer request, never the media files in Radarr/Sonarr). It uses
**official REST APIs only** (no scraping).

This is the plugin **core** plus the first module, **`list_syncarr`**. Future
modules (`bandwidtharr`, `deletearr`, `neutarr`) drop into `backend/modules/` and
auto-load — see [Adding a module](#adding-a-module).

## How it works

1. Poll the configured Trakt list every `SYNC_INTERVAL_MIN` minutes and mirror
   each item into SQLite (storing **both** TMDB and TVDB ids).
2. For each item not already handled, check Seer; if it is not already
   requested/available, create a request.
3. (Your existing Seer → Radarr/Sonarr → download/import flow runs.)
4. On a later poll, once Seer reports the item **Available** (downloaded
   and ready to serve) and **if auto-remove when available is enabled**, remove
   it from the Trakt list in the same pass. The Trakt list entry and known
   Seer request are removed — the media files in Radarr/Sonarr are never
   touched. Auto-remove is **off by default**, so removal is manual unless you switch it on
   (**List-Syncarr → Settings**).
5. Removal can also be triggered manually from the dashboard at any time: the
   per-item delete control on a poster, or **Delete availables**
   (**List-Syncarr → Lists**), which removes every tracked item Seer now
   reports as *Available*. Removed items stay recorded and can be shown in the
   list with the **Show removed** toggle.

## Architecture

```
backend/
  core/
    config.py        # typed env config (pydantic-settings), secret masking
    db.py            # SQLite schema + helpers (WAL, thread-safe)
    scheduler.py     # APScheduler 4 wrapper (interval + cron)
    webhooks.py      # single /webhook router; modules register handlers
    registry.py      # discovers & loads modules, calls setup()
    context.py       # AppContext shared with modules
    api.py           # dashboard JSON endpoints (/api/*)
    app.py           # FastAPI factory + lifespan wiring + SPA serving
    clients/
      trakt.py       # device auth, token refresh, list read/remove
      seer.py        # status check, create request
      arr_client.py  # outbound Radarr/Sonarr connection test
  modules/
    list_syncarr/    # the first module: poll/request, availability-driven removal, reconcile
  main.py            # entrypoint: `uvicorn main:app --app-dir backend`
  pyproject.toml     # packaging + pytest + coverage config
  tests/             # backend test suite (100% coverage)
frontend/            # React + TypeScript + Tailwind (Vite) dashboard
  src/
    features/        # one folder per feature: dashboard, list-syncarr, settings
    shared/          # cross-cutting UI primitives, layout, API client, hooks, utils
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
| `SEER_URL` | – | Base URL of Seer (seeds the store; settable in the UI) |
| `SEER_API_KEY` | – | Seer API key (seeds the store; settable in the UI) |
| `SONARR_URL` | – | Base URL of Sonarr (seeds the store; settable in the UI) |
| `SONARR_API_KEY` | – | Sonarr API key (seeds the store; settable in the UI) |
| `RADARR_URL` | – | Base URL of Radarr (seeds the store; settable in the UI) |
| `RADARR_API_KEY` | – | Radarr API key (seeds the store; settable in the UI) |
| `TMDB_API_KEY` | – | TMDB v3 API key or v4 read-access token (seeds the store; settable in the UI) |
| `OMDB_API_KEY` | – | OMDb API key (seeds the store; settable in the UI) |
| `SABNZBD_URL` | – | Base URL of SABnzbd (seeds the store; settable in the UI) |
| `SABNZBD_API_KEY` | – | SABnzbd API key (seeds the store; settable in the UI) |
| `QBITTORRENT_URL` | – | Base URL of the qBittorrent WebUI (seeds the store; settable in the UI) |
| `QBITTORRENT_API_KEY` | – | qBittorrent WebUI API key, requires qBittorrent ≥ 5.2.0 (seeds the store; settable in the UI) |
| `SYNC_INTERVAL_MIN` | `15` | Poll interval in minutes (seeds the store; settable in the UI) |
| `AUTO_REMOVE_WHEN_AVAILABLE` | `false` | Auto-remove items from their Trakt list once available in Seer (seeds the store; settable in the UI). The legacy `AUTO_REMOVE_ON_IMPORT` name is still accepted. |
| `WEBHOOK_PORT` | `3223` | Port the service listens on |
| `TZ` | `Europe/Istanbul` | Timezone for the scheduler |
| `LOG_LEVEL` | `INFO` | Log level |
| `DB_PATH` | `data/aio-arr.db` | SQLite path (persist via volume) |
| `TOKEN_STORE_PATH` | `data/trakt_tokens.json` | Trakt token store (persist via volume) |
| `SETTINGS_STORE_PATH` | `data/app_settings.json` | UI-managed Trakt settings (persist via volume) |
| `POSTER_CACHE_PATH` | `data/posters` | On-disk poster thumbnail cache (persist via volume) |

The Trakt credentials and list selection are **seeded** from these variables on
first start and then managed from the dashboard **Settings** page; the resolved
state is persisted to `SETTINGS_STORE_PATH` (chmod `0600`, inside the gitignored
`data/` volume). Trakt credentials are therefore optional in `.env`.

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

### Settings page (recommended)

The dashboard **Settings** page is organised into tabs —
**General**, **Database**, **Trakt**, **Seer**, **Sonarr**, **Radarr**, **TMDB**,
**OMDb**, **SABnzbd**, **qBittorrent** — and manages every connection without
touching `.env`. All values are persisted server-side in `SETTINGS_STORE_PATH`.

**General tab** (the default): the status-check interval and the
**light/dark/system** theme control (which mirrors the header).

**Database tab:** shows the on-disk size of the SQLite database (main file plus
WAL/SHM sidecars) and the poster cache, plus row counts for tracked items,
activity entries, and synced lists. It also provides danger-zone actions to
**clear the activity log**, **clear synced items & sync state**, or **clear the
poster cache**. Credentials, Trakt tokens, and tracked-list configuration are
never deleted; clearing items only removes the mirrored rows — the next poll
rebuilds them. SQLite does not shrink the database file immediately after a
delete, so the reported size may not drop right away.

Notifications (toasts) appear **bottom-right** with a close (×) button and a bar
that drains over their ~3-second lifetime.

**Trakt tab:**

- **Credentials** – enter/update the Trakt client id and secret (the secret is
  stored server-side and never shown again). The connected account is always
  addressed as `me`.
- **Connect** – runs the device-auth flow from the browser: it shows the
  `trakt.tv/activate` code and polls until it reads **Connected**.
- **Test connection** – verifies the saved token against the Trakt account.
- **Your Trakt lists** – discovers every list on your account; tick the ones to
  sync (TV, Movies, Anime …).
- **Add by Trakt URL** – paste a list URL such as
  `https://trakt.tv/users/me/lists/anime` to add it. (Removal only works for
  lists your connected account owns.)

**Seer / Sonarr / Radarr / SABnzbd tabs:** each takes a **base URL** and an
**API key** and offers a **Test connection** button. The test validates the key
against the service's own endpoint (`/api/v1/auth/me` for Seer,
`/api/v3/system/status` for Sonarr/Radarr, and `mode=queue` for SABnzbd). The key
is stored server-side and is never returned in clear (the API only exposes whether
a key is set).

**TMDB / OMDb tabs:** each takes only an **API key** (the base URL is the
service's fixed public endpoint) and offers a **Test connection** button. TMDB
accepts either a v3 API key or a v4 read-access token and is validated against
`/3/configuration`; OMDb is validated with a probe lookup. The key is stored
server-side and never returned in clear.

**qBittorrent tab:** takes a **base URL** and a **WebUI API key** (generated in
qBittorrent's Web UI settings; requires qBittorrent ≥ 5.2.0) and offers a **Test
connection** button, which authenticates with an `Authorization: Bearer` header
and reads the application version. The key is stored server-side and never
returned in clear (the API only exposes whether a key is set).

### Upgrading from the previous release

This release renames the connection service to **Seer** (environment variables
`SEER_URL`/`SEER_API_KEY`, database column `seer_request_id`). There are **no
migration shims**: databases and settings files created by the previous release
still use the old request-id column and service key. On upgrade, stop the
container and remove the `data/` volume (or at least `data/aio-arr.db` and
`data/app_settings.json`), then start fresh and re-enter the Seer URL and API
key in **Settings → Seer**. Fresh installs are unaffected.

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

Coverage spans Trakt list parsing, the TMDB/TVDB reverse mapping, and the Trakt
removal paths — sync availability-driven, manual, and reconcile — with mocked HTTP
clients.

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
provider, the layout and topbar, the feature pages (Dashboard, the List-Syncarr
tabs — Lists and Items — and Settings), the route table, and the vendored
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
- `GET /api/status` – dashboard status (trakt_connected, counts).
- `GET /api/items[?status=&list=]` – tracked items, filterable by status and/or list.
- `GET /api/lists` – synced lists with item counts and last/next sync times.
- `GET /api/posters/{media_type}/{tmdb_id}[?imdb=]` – cached poster thumbnail
  (`media_type` is `movie` or `show`); resolved from TMDB, falling back to OMDb,
  and stored under `POSTER_CACHE_PATH` so each is fetched only once.
- `GET /api/activity` – recent meaningful app activity and sync outcomes from the last 15 days (a concise, human-friendly feed, not every read-only API call).
- `POST /api/sync` – trigger an immediate sync and wait for it to complete; returns `409` if a sync is already running.
- `GET /api/settings/trakt` – masked Trakt settings (credentials, user, lists).
- `PUT /api/settings/trakt` – update Trakt client id/secret/user.
- `POST /api/trakt/auth/start` – begin device authorisation; returns the code/URL.
- `GET /api/trakt/auth/status` – poll device-auth progress.
- `POST /api/trakt/test` – verify the saved Trakt token.
- `GET /api/trakt/lists` – discover the account's lists with selection state.
- `POST /api/trakt/lists` – add a list by `{ "url": … }` or `{ owner_user, slug }`.
- `DELETE /api/trakt/lists/{owner_user}/{slug}` – stop syncing a list.
- `GET /api/settings/services` – masked connection state for every service
  (seer, sonarr, radarr, tmdb, omdb, sabnzbd, qbittorrent); each emits only
  its own fields, with secrets reduced to `<field>_set` booleans.
- `PUT /api/settings/services/{name}` – update a service's fields
  `{ url?, api_key? }` (only the fields it declares apply).
- `POST /api/services/{name}/test` – test a service connection.
- `GET /api/settings/database` – storage overview: DB size, poster cache size,
  and row counts for `items`, `activity`, and `list_state`.
- `POST /api/settings/database/clear-activity` – empty the activity log and
  return refreshed stats.
- `POST /api/settings/database/clear-items` – delete every tracked item and list
  sync state, preserving tracked-list configuration; returns refreshed stats.
- `POST /api/settings/database/clear-posters` – delete cached poster thumbnails;
  returns refreshed stats.

## Adding a module

1. Create `backend/modules/<name>/__init__.py` exposing
   `setup(scheduler, app, ctx)` (sync or async).
2. Use `ctx` for the shared clients, database and config; register scheduled
   jobs via `scheduler.add_interval` / `scheduler.add_cron`, and webhook
   handlers via `ctx.webhooks.register(subpath, handler)`.
3. Call `ctx.db.add_activity(action, detail)` for meaningful user-visible state
   changes and failures, using concise human-friendly text. Avoid secrets, raw
   credential values, full API response dumps, and low-signal polling noise.
4. Drop the folder in `backend/modules/` — `backend/core/registry.py` auto-loads
   it on start-up.

### Frontend: adding a menu or component

- Add a shadcn component: `cd frontend && npx shadcn@latest add <component>`.
- Add a menu/route: extend the nav config in
  `frontend/src/shared/layout/nav-config.tsx` and add a route in
  `frontend/src/App.tsx` (feature pages live under `frontend/src/features/<name>/`).

## Notes & limitations

- The dashboard **List-Syncarr → Lists** tab is collapsible: each synced list
  shows its item count, a relative *last synced* time and a *next sync*
  countdown, and expands to a poster grid of its items (title + request/
  availability status). Posters are resolved from TMDB (falling back to OMDb)
  and cached on disk under `POSTER_CACHE_PATH`, so each is downloaded only once.
  The *next sync* time is derived from the last poll plus `SYNC_INTERVAL_MIN`
  (an approximation, since the pre-release APScheduler wrapper does not expose a
  next-fire time).
- The dashboard **List-Syncarr → Settings** tab manages sync behaviour: the
  **sync interval** (how often Trakt is polled) and the **remove from Trakt when
  available** toggle (off by default — when off, items leave a Trakt list only via
  the manual delete controls in the **Lists** tab). Both are persisted server-side
  and applied live.
- Single Uvicorn worker by design: the scheduler runs in-process and SQLite
  uses WAL with a process-level lock. Multi-worker deployment is out of scope.
- APScheduler 4 is pre-release; all scheduler usage is isolated behind
  `backend/core/scheduler.py` so a downgrade to 3.x is a one-file change.
