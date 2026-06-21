# Build prompt: All-in-One ARR (core + traktsync module)

Build a self-hosted service that keeps a Trakt list in sync with Jellyseerr, and — the key part — **removes an item from the Trakt list once it has been downloaded and imported** by Radarr/Sonarr. This must NOT scrape any websites; use official REST APIs only. Existing tools (ListSync) are unstable specifically because they scrape, so API-first is a hard requirement.

This is the first piece of a larger "all-in-one ARR" that I'll extend later with my own modules (bandwidtharr, deletearr, neutarr), so build a small plugin core and implement `traktsync` as the first module that plugs into it.

## Stack & constraints

- Python 3.11, FastAPI + Uvicorn, APScheduler for jobs, SQLite for state, `httpx` for API calls.
- Runs in Docker; ship a `Dockerfile` and `docker-compose.yml`. I run an existing *arr stack locally on the same network.
- Config via environment variables (and a `.env.example`). No secrets in code.
- Everything must support a **DRY_RUN mode** (default ON) that logs what it *would* do — request in Jellyseerr, remove from Trakt — without actually doing it. I want to verify the loop before it starts deleting from my Trakt list.
- Structured logging (one line per action, include ids). Clear startup log of resolved config (mask secrets).

## Architecture (plugin core + modules)

```
aio-arr/
  core/
    config.py            # load env, validate, expose typed settings
    db.py                # sqlite schema + helpers
    scheduler.py         # APScheduler instance shared by all modules
    webhooks.py          # single FastAPI router; modules register handlers
    registry.py          # discovers & loads modules, calls setup()
    clients/
      trakt.py           # device auth, token refresh, read list, remove items
      jellyseerr.py      # status check, create request
      arr.py             # (light) helpers if needed
  modules/
    traktsync/           # IMPLEMENT THIS ONE NOW
      __init__.py        # exposes setup(scheduler, app, ctx)
  main.py                # FastAPI app: mounts webhooks, loads modules, starts scheduler
```

Each module exposes one entrypoint:
```python
def setup(scheduler, app, ctx) -> None:
    # register scheduled jobs and/or webhook handlers
```
`ctx` carries the shared clients (trakt, jellyseerr), the db, and config. Adding a future module = drop a folder in `modules/` and it auto-loads via `registry.py`. Don't build the other modules — just leave the structure ready.

## The sync loop (what traktsync does)

1. **Poll the Trakt list** on an interval (default 15 min). Store/refresh each item in SQLite.
2. For each item, **check Jellyseerr status**; if it's not already requested/available, **create a request**.
3–4. (My existing Jellyseerr → Radarr/Sonarr → download/import handles this — out of scope.)
5. **Receive an On-Import webhook** from Radarr/Sonarr → look the item up in SQLite by tmdb/tvdb id.
6. **Remove that item from the Trakt list.**

Also add a **nightly reconciliation job**: poll Jellyseerr for items whose status is now Available (5) and remove any that the webhook missed. The webhook is the primary trigger; reconciliation is the safety net.

## Data model (SQLite)

Table `items`:
- `trakt_id` (int), `type` ('movie'|'show'), `title`, `year`
- `tmdb` (int, nullable), `tvdb` (int, nullable), `imdb` (str, nullable)
- `list_id` (the Trakt list this came from)
- `jellyseerr_request_id` (nullable), `status` ('synced'|'requested'|'available'|'removed')
- `created_at`, `updated_at`

Store **both tmdb and tvdb** at sync time so reverse lookup from either Radarr (tmdb) or Sonarr (tvdb) is trivial.

## API details (use these exact endpoints — don't guess)

**Trakt** — headers on every call: `trakt-api-version: 2`, `trakt-api-key: {client_id}`; add `Authorization: Bearer {access_token}` for writes.

- Device auth (headless, run once, then persist tokens to a mounted volume and auto-refresh):
  - `POST https://api.trakt.tv/oauth/device/code` `{ client_id }` → user_code + verification_url; print these clearly to the logs so I can authorize in a browser.
  - Poll `POST https://api.trakt.tv/oauth/device/token` `{ code, client_id, client_secret }` → access_token, refresh_token, expires_in.
  - Refresh via `POST https://api.trakt.tv/oauth/token` `{ refresh_token, client_id, client_secret, grant_type: "refresh_token", redirect_uri: "urn:ietf:wg:oauth:2.0:oob" }`. Refresh proactively before expiry.
- Read list items: `GET /users/{user}/lists/{list_id}/items/movies,shows` (also support the watchlist via `GET /sync/watchlist/movies,shows`). Each item returns `ids: { trakt, slug, imdb, tmdb, tvdb }`.
- Remove items: `POST /users/{user}/lists/{list_id}/items/remove` with body `{ "movies": [{ "ids": { "tmdb": <id> } }], "shows": [...] }` (watchlist: `POST /sync/watchlist/remove`).

**Jellyseerr** — header `X-Api-Key: {key}`:
- Status: `GET /api/v1/movie/{tmdbId}` or `GET /api/v1/tv/{tmdbId}` → `mediaInfo.status` (1=Unknown, 2=Pending, 3=Processing, 4=Partially Available, 5=Available; `mediaInfo` null = not in system).
- Request: `POST /api/v1/request` `{ "mediaType": "movie"|"tv", "mediaId": <tmdbId>, "seasons": "all" }` (seasons only for tv).

**Radarr/Sonarr webhook** — I'll add a Webhook connection pointing at this service's `/webhook/arr` endpoint, On Import enabled.
- On the import event (Radarr/Sonarr send `eventType: "Download"` for completed import), extract `movie.tmdbId` (Radarr) or `series.tvdbId` (Sonarr).
- **Important:** webhook field names vary by version, so on first receipt log the full raw JSON payload before parsing, and parse defensively. Don't assume — confirm the shape from the logged payload.

## Config (env vars → `.env.example`)

```
TRAKT_CLIENT_ID=
TRAKT_CLIENT_SECRET=
TRAKT_USER=                 # your trakt username (or 'me')
TRAKT_LIST_ID=              # slug or numeric id; or 'watchlist'
JELLYSEERR_URL=http://192.168.0.x:5055
JELLYSEERR_API_KEY=
SYNC_INTERVAL_MIN=15
WEBHOOK_PORT=3223
DRY_RUN=true
TZ=Europe/Istanbul
LOG_LEVEL=INFO
```

## Simple UI

A single-page dashboard served by the same FastAPI app at `/`. Keep it lightweight — **one `index.html` with vanilla JS + `fetch` and minimal CSS, no React/Node build step**. It should show:

- **Header bar:** service name, Trakt auth status (Connected / Needs auth), and a prominent **DRY_RUN badge** (orange when ON, so it's obvious nothing is being removed for real yet).
- **Stat cards:** counts by status — Synced, Requested, Available, Removed.
- **Controls:** a "Sync now" button (triggers an immediate poll) and a DRY_RUN on/off toggle.
- **Items table:** Title, Year, Type, Status, Last updated. Filtering by status is a nice-to-have, not required.
- **Activity feed:** the last ~50 actions (e.g. "requested X", "removed Y from Trakt"), newest first.

Back it with small JSON endpoints: `GET /api/status`, `GET /api/items`, `GET /api/activity`, `POST /api/sync`, `POST /api/settings/dry-run`. The page polls these every ~10s to refresh (no websockets needed). Minimal styling, dark-mode friendly.

## Deliverables

- The repo structure above, runnable end to end.
- The dashboard (`index.html` + the `/api/*` endpoints above), served by the same app.
- `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md` (setup incl. the one-time Trakt device-auth step and how to add the Radarr/Sonarr webhook).
- A simple `GET /health` endpoint and a `GET /status` that returns counts by item status from SQLite.
- Token store persisted to a Docker volume so I don't re-auth on restart.
- Basic tests for: Trakt list parsing, tmdb/tvdb mapping, and the remove-on-webhook lookup (mock the HTTP clients).

## How to proceed

Scaffold the core first, then `traktsync`. Keep DRY_RUN as the default and make sure the first run only *logs* requests and removals. Ask me before introducing any extra dependency or changing the endpoints above. Build incrementally and tell me how to run each stage as you go.
