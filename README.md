# All-in-One ARR

A small, self-hosted service that keeps a **Trakt list in sync with Seer**
and — the key part — optionally **removes an item from the Trakt list once Seer
reports it available** — or partially available (off by default; deletes the Trakt
entry and the Seer request, never the media files in Radarr/Sonarr). It also includes
**Bandwidth-Controllarr**, which can pause **SABnzbd** while **qBittorrent**
has active torrents and resume it when the torrents go idle (off by default).
It also includes **Findarr**, which can trigger bounded missing-media and
quality-cutoff searches in **Sonarr 4+** and **Radarr 6+** (off by default).
It also includes **Deletarr**, which scans mounted media folders for junk files
and deletes only explicitly selected current scan results under the configured
library roots.
It uses **official REST APIs only** (no scraping).

This is the plugin **core** plus four modules, **`list_syncarr`**,
**`bandwidth_controllarr`**, **`findarr`**, and **`deletarr`**. Future modules
drop into `backend/modules/` and auto-load — see [Adding a module](#adding-a-module).

## How it works

1. Poll the configured Trakt list every `SYNC_INTERVAL_MIN` minutes and mirror
   each item into SQLite (storing **both** TMDB and TVDB ids).
2. For each item not already handled, check Seer; if it is not already
   requested/available, create a request.
3. (Your existing Seer → Radarr/Sonarr → download/import flow runs.)
4. On a later poll, once Seer reports the item **available** — or **partially
   available** (some episodes downloaded) — and **if auto-remove is enabled**, remove
   it from the Trakt list. Both the Trakt entry and the Seer request are deleted (the
   request id we stored, or one looked up from Seer when the request was made
   elsewhere); the media files in Radarr/Sonarr are never touched, so any in-progress
   download continues. A merely-requested item (pending/processing) is left on the
   list until it is at least partially available. Auto-remove is **off by default**,
   so removal is manual unless you switch it on (**List-Syncarr → Settings**).
5. Each poll also **refreshes the status of every tracked item against Seer** — even
   items that have since left their Trakt list — so a stored status never drifts: an
   item that became available while off-list is still relabelled (and auto-removed
   when enabled) instead of staying frozen.
6. Removal can also be triggered manually from the dashboard at any time: the
   per-item delete control on a poster, or **Delete availables**
   (**List-Syncarr → Lists**), which removes every tracked item Seer now
   reports as *Available*. (It sweeps only fully-available items; partially-available
   items are removed by the auto-remove poll when that is enabled.) Removed items stay
   recorded and can be shown in the list with the **Show removed** toggle.

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
    list_syncarr/         # poll/request, availability-driven removal, reconcile
    bandwidth_controllarr/  # pause SABnzbd while qBittorrent has active torrents
    findarr/              # bounded Sonarr/Radarr missing and upgrade searches
    deletarr/             # reviewed junk-file scans and validated deletion
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
| `AUTO_REMOVE_WHEN_AVAILABLE` | `false` | Auto-remove items from their Trakt list once Seer reports them available or partially available; deletes the Trakt entry and the Seer request, never the media files (seeds the store, settable in the UI). The legacy `AUTO_REMOVE_ON_IMPORT` name is still accepted. |
| `BANDWIDTH_CONTROL_ENABLED` | `false` | Enable the Bandwidth-Controllarr loop (seeds the store; toggleable in the UI). Off by default so SABnzbd is never paused without opt-in. |
| `BANDWIDTH_CHECK_INTERVAL_SEC` | `15` | How often Bandwidth-Controllarr polls qBittorrent and SABnzbd, in seconds (seeds the store; settable in the UI). |
| `DELETARR_MOVIES_PATH` | `/media/movies` | Movies library root for Deletarr scans and deletion validation (seeds the store on first run only; settable in the Deletarr Settings tab). |
| `DELETARR_TV_PATH` | `/media/tv` | TV library root for Deletarr scans and deletion validation (seeds the store on first run only; settable in the Deletarr Settings tab). |
| `DELETARR_USE_ARR_SOURCE` | `true` | Use Radarr/Sonarr as the source of truth for which files belong on disk (falls back to the heuristic scan when unreachable). Seeds the store on first run only; toggleable in the Deletarr Settings tab. |
| `WEBHOOK_PORT` | `3223` | Port the service listens on |
| `TZ` | `Europe/Istanbul` | Timezone for the scheduler |
| `LOG_LEVEL` | `INFO` | Log level |
| `DB_PATH` | `data/aio-arr.db` | SQLite path (persist via volume) |
| `TOKEN_STORE_PATH` | `data/trakt_tokens.json` | Trakt token store (persist via volume) |
| `SETTINGS_STORE_PATH` | `data/app_settings.json` | UI-managed Trakt settings (persist via volume) |
| `POSTER_CACHE_PATH` | `data/posters` | On-disk poster thumbnail cache (persist via volume) |
| `POSTER_CACHE_TTL_DAYS` | `30` | Evict posters not served within this many days (must exceed the 7-day browser cache; `0` disables) |
| `POSTER_CACHE_MAX_MB` | `256` | Hard cap on total poster-cache size; oldest evicted first (`0` disables) |
| `POSTER_CACHE_CHURN_INTERVAL_MIN` | `360` | How often the poster-cache eviction job runs |

The Trakt credentials and list selection are **seeded** from these variables on
first start and then managed from the dashboard **Settings** page; the resolved
state is persisted to `SETTINGS_STORE_PATH` (chmod `0600`, inside the gitignored
`data/` volume). Trakt credentials are therefore optional in `.env`.

Create the Trakt application at <https://trakt.tv/oauth/applications> to obtain
the client id/secret.

## Running with Docker (recommended)

Prebuilt multi-arch images (`linux/amd64` + `linux/arm64`) are published to
Docker Hub at [`erenatbas/aio-arr`](https://hub.docker.com/r/erenatbas/aio-arr),
so most users never build from source.

### Quick start — pull the image

```bash
mkdir aio-arr && cd aio-arr
curl -fsSLO https://raw.githubusercontent.com/eatbas/all-in-one-ARR/main/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/eatbas/all-in-one-ARR/main/.env.example -o .env
# edit .env — set at least TRAKT_CLIENT_ID / TRAKT_CLIENT_SECRET
docker compose up -d
```

The bundled `docker-compose.yml` references `erenatbas/aio-arr:latest`, so
`docker compose up -d` pulls the image; no local build is needed. The dashboard
is then at <http://localhost:3223/>, and the `./data` volume persists the SQLite
database and the Trakt token store across restarts. Pin a specific version with
`AIO_ARR_IMAGE=erenatbas/aio-arr:0.1.0 docker compose up -d`.

> **Prerequisite:** this quick start needs the published release — the
> `erenatbas/aio-arr` image on Docker Hub and these files on the `main` branch. If
> you cloned the repository instead, use **Build from source** below.

### Plain `docker run`

```bash
docker run -d --name aio-arr \
  -p 3223:3223 \
  --env-file .env \
  -v "$PWD/data:/app/data" \
  --restart unless-stopped \
  erenatbas/aio-arr:latest
```

### Build from source (developers)

```bash
cp .env.example .env   # then fill in the required values
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build
```

### Image tags

| Tag | Meaning |
| --- | --- |
| `latest` | Newest release — the latest `vX.Y.Z` tag |
| `X.Y.Z` (e.g. `0.1.0`) | Immutable release, published from the `vX.Y.Z` git tag |
| `X.Y` (e.g. `0.1`) | Latest patch of that minor release |

Every tag is a multi-arch manifest covering `linux/amd64` and `linux/arm64`, so
the same reference runs on x86-64 NAS boxes, ARM boards, and Apple Silicon.

### Deletarr media mounts

If you use **Deletarr** in Docker, mount your media libraries at the configured
container paths (defaults: `/media/movies` and `/media/tv`). Use read-write
mounts only when you intend to delete reviewed junk from the dashboard.

### Deploying on a NAS (Synology / QNAP / Portainer)

On a NAS the container runs as a fixed non-root user, so set `user:` to the
UID:GID that owns your `data` and media folders (find it with `id <nas-user>`).
Attach it to your existing media Docker network so the *arr services resolve by
container name. This single container replaces separate list-sync, Deletarr, and
bandwidth-control containers — all four modules share the one dashboard on 3223.

```yaml
services:
  aio-arr:
    image: erenatbas/aio-arr:latest
    container_name: aio-arr
    user: "1000:1000"                # UID:GID that owns ./data and the media dirs
    env_file: .env                   # TRAKT_* plus any other secrets
    environment:
      - TZ=Europe/Istanbul
      # Reach the *arr services by container name on your shared network:
      - SEER_URL=http://jellyseerr:5055
      - SONARR_URL=http://sonarr:8989
      - RADARR_URL=http://radarr:7878
    ports:
      - "3223:3223"
    volumes:
      - ./data:/app/data
      - /volume1/media/movies:/media/movies   # rw only if deleting junk
      - /volume1/media/tv:/media/tv
    networks:
      - media
    restart: unless-stopped

networks:
  media:
    external: true
```

Import this via Synology **Container Manager** / **Portainer**, or run
`docker compose up -d` over SSH. Everything else (service URLs, API keys) can also
be configured later from the dashboard **Settings** page instead of the
environment.

### Updating

```bash
docker compose pull && docker compose up -d
```

In Container Manager, re-pull the image and recreate the container. If you run
[Watchtower](https://containrrr.dev/watchtower/), label the service
`com.centurylinklabs.watchtower.enable=true` to update it automatically.

### How the images are built

Images are built and pushed automatically by GitHub Actions
(`.github/workflows/docker-publish.yml`) on every `vX.Y.Z` release tag; pushes to
`main` and pull requests run the checks but publish no image. Maintainers can
also publish a multi-arch image by hand:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t erenatbas/aio-arr:0.1.0 -t erenatbas/aio-arr:latest --push .
```

### Cutting a release

Maintainers publish a release with `scripts/release.sh`. It reads the current
version from the latest `vX.Y.Z` git tag, bumps it, updates the version in
`backend/pyproject.toml` and `frontend/package.json` (the sidebar footer shows the
latter), commits, creates an annotated `vX.Y.Z` tag, and pushes `main` plus the
tag. The tag push publishes `erenatbas/aio-arr:X.Y.Z` (+ `X.Y`) and refreshes
`:latest`. The workflow now runs **only** on `vX.Y.Z` tags; commits to `main` and
pull requests no longer trigger it. After the tagged image is published
successfully, the workflow also creates a GitHub Release with automatically
generated release notes.

```bash
bash scripts/release.sh          # patch: 1.6.0 -> 1.6.1 (default)
bash scripts/release.sh minor    # 1.6.0 -> 1.7.0
bash scripts/release.sh major    # 1.6.0 -> 2.0.0
bash scripts/release.sh --dry-run minor   # preview only; changes nothing
```

The release must be cut from a clean `main` (override with `RELEASE_BRANCH`). It
runs `scripts/check.sh` first — the full quality gate (Ruff lint + format, mypy,
Prettier, tests, and build) — and prompts before pushing (`-y` to skip).
`--skip-checks` only bypasses this *local* pre-flight; CI re-runs the same gates on
the pushed tag (before the image build), so a failing check still blocks the
Docker publish. Only
`vX.Y.Z` tags trigger the publish, so the `v` prefix is required; a mistaken tag can
be removed with `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`.

To backfill a GitHub Release for an existing tag, run the **Build and publish
Docker image** workflow manually in GitHub Actions and enter the tag (for example,
`v1.6.3`) in the required `release_tag` input. The workflow verifies that the tag
exists before creating the release, skips the checks and image build during a
backfill, and does nothing if that release already exists.

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
poster cache** (which removes **all** cached posters — both list and Trending —
in one action). Credentials, Trakt tokens, and tracked-list configuration are
never deleted; clearing items only removes the mirrored rows — the next poll
rebuilds them. SQLite does not shrink the database file immediately after a
delete, so the reported size may not drop right away.

Notifications (toasts) appear **bottom-right** with a close (×) button and a bar
that drains over their ~3-second lifetime.

**Trakt tab:**

- **Credentials** – the Trakt client id is shown in the input so you can edit it
  directly; the secret is stored server-side and never shown again. Changes
  autosave after you stop typing. The connected account is always addressed as
  `me`.
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
`/api/v3/system/status` for Sonarr/Radarr, and `mode=queue` for SABnzbd). The
base URL is shown in the input; the key is stored server-side and is never
returned in clear (the API only exposes whether a key is set). Edits autosave
after you stop typing.

**TMDB / OMDb tabs:** each takes only an **API key** (the base URL is the
service's fixed public endpoint) and offers a **Test connection** button. TMDB
accepts either a v3 API key or a v4 read-access token and is validated against
`/3/configuration`; OMDb is validated with a probe lookup. The key is stored
server-side and never returned in clear. Edits autosave after you stop typing.

**qBittorrent tab:** takes a **base URL** and a **WebUI API key** (generated in
qBittorrent's Web UI settings; requires qBittorrent ≥ 5.2.0) and offers a **Test
connection** button, which authenticates with an `Authorization: Bearer` header
and reads the application version. The base URL is shown in the input; the key
is stored server-side and never returned in clear (the API only exposes whether
a key is set). Edits autosave after you stop typing.

### Bandwidth-Controllarr page

The dashboard **Bandwidth-Controllarr** page (left menu) has two tabs:

- **Status** — live cards for qBittorrent and SABnzbd (download speed, active
downloads, queue size, and a **PAUSED/RESUMED** badge for SABnzbd), plus a
system-status banner that shows the last control check and turns red while
qBittorrent has active torrents. The page auto-refreshes every few seconds.
- **Settings** — the master **Enable bandwidth control** switch and a **Check
interval** selector (10, 15, 30, or 60 seconds). The switch is also available on
the Status tab for convenience. A link to the Prometheus metrics endpoint
(`/metrics`) is provided.

Connections are not configured on this page; configure **SABnzbd** and
**qBittorrent** in **Settings** first.

### Findarr page

The dashboard **Findarr** page (left menu) automates conservative search
commands for the already-configured **Sonarr** and **Radarr** connections:

- **Supported versions** — Sonarr `4+` and Radarr `6+`. Findarr checks
  `/api/v3/system/status` before sending search commands and reports older
  connected versions as unsupported.
- **Search modes** — missing media and quality-cutoff upgrades for Sonarr and
  Radarr.
- **Sonarr search granularity** — the **Missing search mode** and **Upgrade
  mode** selectors choose how Sonarr content is searched: **Episodes** (one
  `EpisodeSearch` per episode), **Seasons** (one `SeasonSearch` per season —
  season packs, recommended for torrent users), or **Shows** (one `SeriesSearch`
  per series, upgrading a whole show at once). In Seasons/Shows mode the
  per-cycle limit and the counters apply to seasons/series rather than episodes.
  Radarr has no season/show concept, so these selectors are Sonarr-only.
- **Safety boundaries** — Findarr only triggers native Arr search commands. It
  does not delete media files, remove Seer requests, alter download clients, or
  change Trakt lists.
- **Safe defaults** — the master switch is off by default. Per-cycle limits, an
  hourly command cap, monitored-only filtering, skip-future filtering, an
  optional queue-size guard, and a **sleep duration** (seconds to wait between
  successive Arr search commands, `0` to disable) bound the side effects.
- **State and history** — processed items are recorded so Findarr does not
  repeatedly search the same item, and provides an explicit reset control for
  processed state. The **History** tab lists recent Findarr actions —
  resolving full Sonarr series titles (for example `Avatar: The Last Airbender
  (2024) - S01E06 - Masks`) rather than "Unknown series" — with the operation,
  item id, instance, and how long ago, plus an instance filter, a search box, a
  row-count selector, and a **Clear** control that empties the history log
  (distinct from the processed-state reset; neither touches Arr libraries). Each
  history row captures its title at search time, so rows written before a title
  fix are **not** relabelled retroactively, and items already in processed state
  are skipped (no fresh row). To refresh titles after upgrading, reset processed
  state and run again, then optionally clear the old history.
- **Stateful management** — processed-media ids are cleared automatically after
  the **State reset (hours)** window (default `168` = 7 days) so items become
  eligible again ("re-look where we left off and renew"); the Settings tab shows
  the **Initial state created** time and the derived **State reset date**, and an
  **Emergency reset** clears the state immediately and restarts the window.
  Resets only clear Findarr's own bookkeeping — media and Arr libraries are never
  touched.
- **Status visibility** — once the wanted list is exhausted, Findarr correctly
  goes quiet until the reset window elapses, so the Status cards are built to
  make that legible rather than look broken. Each card's headline is the
  **all-time** searches/upgrades tally, which is reset-proof and never collapses
  to `0`; a **this window** sub-line shows how much of the last run's wanted set
  has been searched; a plain-language **activity** line states what the last run
  did (*Searched N*, *Caught up*, *Nothing wanted*, *Throttled*, or a connection
  error); and the panel header shows a **Next sweep** countdown to the reset.
  These figures reflect the most recent run, not a live Arr query.

Connections are not configured on this page; configure **Sonarr** and
**Radarr** in **Settings** first.

### Deletarr page

The dashboard **Deletarr** page (left menu) scans mounted media folders for
reviewed junk candidates and deletes only what you explicitly confirm:

- **Libraries** — Movies and TV Shows have separate scan tabs. Each tab shows the
  current configured root as read-only context.
- **Settings** — the Deletarr Settings tab edits the Movies and TV library roots
  and the **Use Radarr and Sonarr as the source of truth** toggle. The path
  defaults are `/media/movies` and `/media/tv`, seeded from `DELETARR_MOVIES_PATH`
  and `DELETARR_TV_PATH` on first run; the toggle is seeded from
  `DELETARR_USE_ARR_SOURCE` (default on). Later changes are persisted in the
  settings store.
- **Source of truth** — with the toggle on and Radarr (movies) / Sonarr (TV)
  connected, Deletarr fetches the managed inventory (each title's on-disk folder
  and the files the app tracks). Results explicitly separate junk files and folders
  from untracked media such as videos, loose files, and whole folders the library
  manager does not know about. The scan-mode banner shows *Verified against
  Radarr/Sonarr* in this mode. When the matching app is unconfigured or unreachable
  it falls back to the heuristic scan and the banner explains why.
- **Read-only scans** — scans inspect filenames, folders, and sizes only. The
  heuristic fallback flags common sidecars, metadata that does not match the
  protected video, junk folders, duplicate or misplaced movie videos, and
  unexpected TV season content. Both scan modes also surface empty directory trees
  conservatively, without treating unreadable or symlinked content as empty.
- **Reviewed deletion** — scan candidates start unselected and are rendered with
  checkboxes in collapsible movie or TV groups. Junk and untracked-media sections
  have independent **Select all** controls, and deletion requires an explicit
  confirmation showing the selected count and reclaimable size.
- **Server-side safety** — the backend deletes only paths present in the current
  scan results for that library, and it revalidates each resolved path remains
  under the configured movies or TV root. Missing files and rejected paths are
  reported as failures rather than aborting the whole request.
- **Container paths** — when running in Docker, the media paths must be mounted
  into the container at the same paths Deletarr is configured to scan.

### Trending page

The dashboard **Trending** page (left menu, directly below the Dashboard)
surfaces trending and popular **movies and TV shows** so you can add them to a
Trakt list without leaving the app. It is organised as **per-source tabs**:

- **Trakt / TMDB / Seer** — each tab shows that provider's own official
  trending/popular feed. A **Movies | Shows** toggle and a **Trending | Popular**
  toggle apply per tab. A **Hide available** switch filters out titles you already
  have — anything in Radarr/Sonarr (the green ones) or reported *Available* in Seer.
- **Open on the source** — each poster's **top-right** corner has a link to the
  title's dedicated page on its source: the Trakt page (by slug), the TMDB page,
  or — for Seer items — your configured Overseerr/Seer instance's media page.
- **IMDb rating overlay** — each card shows the title's **IMDb star and rating**
  in the poster's top-left corner, fetched on demand from **OMDb** (IMDb has no
  official trending API, so it is an enrichment overlay, not a source). Ratings
  are cached server-side with a 24-hour TTL and fetched lazily, so a grid does not
  exhaust the OMDb free-tier quota; a card simply omits the rating when none is
  available.
- **Library status (Seer tab)** — cards also show the item's Seer library status
  (Requested / Processing / Partial / Available) read from `mediaInfo`, so you can
  see what is already in your library. Items already mirrored in a tracked list
  show a **Tracked** badge on any tab.
- **Already in Sonarr/Radarr** — titles already present in **Radarr** (movies) or
  **Sonarr** (shows) are marked with a **thick green ring** and an **In library**
  badge on every tab. Movies match by TMDB id; shows match by TVDB id (or by TMDB
  id when Sonarr exposes one), so a show discovered on the TMDB/Seer tabs is matched
  when an id is resolvable. The Radarr/Sonarr libraries are listed at most once a
  minute (cached) and degrade silently when an Arr is unconfigured or unreachable.
- **Add to a Trakt list** — the **Add +** button in each poster's **bottom-right**
  corner adds the item to one of your **owned** synced lists and then triggers the
  **List-Syncarr** sync, which is what creates the Seer request through the normal
  pipeline (no separate request is made). Adding only targets lists your connected
  account owns (the watchlist and curated/official lists are excluded); if you have
  no owned list yet, add one in **Settings → List-Syncarr** first.

Connections are not configured on this page; configure **Trakt**, **TMDB**,
**Seer** and (for the rating overlay) **OMDb** in **Settings** first. A tab whose
source is unconfigured or unreachable simply shows an empty state rather than
breaking the page.

### Upgrading from the previous release

This release renames the connection service to **Seer** (environment variables
`SEER_URL`/`SEER_API_KEY`, database column `seer_request_id`). Upgrades are
handled automatically on startup: the database schema is migrated in place — the
`seer_request_id` column is added to an existing `items` table and any value
stored under the old `jellyseerr_request_id` column is carried forward — and the
settings file self-migrates. **No manual data wipe is required.**

Because the service itself was renamed, the Seer **URL and API key are not
carried over** from the old Jellyseerr entry; after upgrading, confirm or enter
them in **Settings → Seer** (or set `SEER_URL`/`SEER_API_KEY`). Fresh installs
are unaffected.

## Local development

Backend (run from the repository root so `.env`, `data/` and `frontend/dist`
resolve as they do in Docker):

```bash
python3.14 -m venv .venv && . .venv/bin/activate
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

## Code quality

Formatting, linting, and static typing are automated and enforced in CI:

| Area | Tool | Responsibility |
| --- | --- | --- |
| Backend | [Ruff](https://docs.astral.sh/ruff/) | Linting **and** formatting **and** import sorting — one tool in place of Black + isort + Flake8. |
| Backend | [mypy](https://mypy-lang.org/) | Static type checking of `core/` and `modules/`. |
| Frontend | [ESLint](https://eslint.org/) | Linting (TypeScript + React-hooks rules). |
| Frontend | [Prettier](https://prettier.io/) | Formatting. `eslint-config-prettier` switches off the ESLint rules Prettier owns so the two never conflict. |

Configuration lives in `backend/pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`),
`frontend/.prettierrc.json`, `frontend/.prettierignore`, and
`frontend/eslint.config.js`.

Run the checks the way CI does:

```bash
# Backend — from backend/, with the dev extras installed
ruff check .            # lint (add --fix to auto-fix)
ruff format --check .   # verify formatting (drop --check to write)
mypy                    # type check

# Frontend — from frontend/
npm run lint
npm run format:check    # verify formatting (npm run format to write)
npm run test:types
```

`bash scripts/check.sh` runs all of the above plus the test suites and build.

**Pre-commit hooks** (optional but recommended) run Ruff and Prettier before each
commit — see `.pre-commit-config.yaml`:

```bash
pip install pre-commit
pre-commit install
```

The whole tree was reformatted once when this toolchain was adopted. Record those
formatting-only commit SHAs in `.git-blame-ignore-revs`, then have `git blame`
skip them:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## Tests

Run the full local verification path from the repository root:

```bash
bash scripts/check.sh
```

This creates or reuses `.venv`, installs the backend with development extras,
runs the backend lint (Ruff), format check (Ruff) and type check (mypy) followed
by the coverage-gated test suite, regenerates the OpenAPI schema and frontend
types, checks that generated contract files are committed, then runs frontend
linting, the Prettier format check, type checking, tests, and the production
build.

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

The frontend API types are generated from FastAPI's OpenAPI schema. Regenerate
them after changing API request or response models:

```bash
.venv/bin/python scripts/export_openapi.py
cd frontend && npm run api:types
```

GitHub Actions runs the same backend and frontend gates before the Docker publish
job. Docker Hub login and image push are skipped on pull requests and run only
after both check jobs have passed.

## Endpoints

- `GET /health` – liveness probe.
- `GET /status` – item counts by status.
- `GET /api/status` – dashboard status (trakt_connected, counts).
- `GET /api/items[?status=&list=]` – tracked items, filterable by status and/or list.
- `GET /api/lists` – synced lists with item counts and last/next sync times.
- `GET /api/posters/{media_type}/{tmdb_id}[?imdb=]` – cached poster thumbnail
  (`media_type` is `movie` or `show`); resolved from TMDB, falling back to OMDb,
  and stored under `POSTER_CACHE_PATH` so each is fetched only once. The list and
  Trending pages share this one cache; a scheduled job evicts posters not served
  within `POSTER_CACHE_TTL_DAYS` and caps the cache at `POSTER_CACHE_MAX_MB`.
- `GET /api/activity` – recent meaningful app activity and sync outcomes from the last 15 days (a concise, human-friendly feed, not every read-only API call).
- `POST /api/sync` – trigger an immediate sync and wait for it to complete; returns `409` if a sync is already running.
- `GET /api/settings/trakt` – Trakt settings; the client id and URL/hint are
  returned in clear, the client secret is reduced to `client_secret_set`, and
  tracked lists are included.
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
- `POST /api/settings/database/clear-posters` – delete every cached poster
  thumbnail (list and Trending share one cache); returns refreshed stats. Stale
  posters are also evicted automatically by the scheduled churn job.
- `GET /api/bandwidth/status` – live Bandwidth-Controllarr state: enabled flag,
  control status, last-check timestamp, configured interval, and current
  qBittorrent/SABnzbd stats.
- `PUT /api/bandwidth/settings` – update `{ enabled?, check_interval_seconds? }`;
  persists the change, reschedules the control loop on interval change, and
  returns the updated state.
- `GET /api/deletarr/settings` – current Deletarr movies/TV library roots and the
  `use_arr_source` flag.
- `PUT /api/deletarr/settings` – update `{ movies_path?, tv_path?, use_arr_source? }`,
  persist them, and refresh the live Deletarr state.
- `GET /api/deletarr/status` – Deletarr settings plus per-library scan status,
  last scan timestamp, last error, scan mode (`arr`/`heuristic`), Arr availability,
  result count, and stats.
- `GET /api/deletarr/results?type=movies|tv` – current scan results for one
  Deletarr library, including the scan mode used.
- `POST /api/deletarr/scan` – run a read-only scan for `{ type }`; uses Radarr/Sonarr
  as the source of truth when connected, otherwise the heuristic scan. Returns `409`
  if another Deletarr operation is already running.
- `POST /api/deletarr/delete` – delete `{ type, paths }` after validating each
  path is a current scan result, resolves under that library root, and (for
  Arr-backed scans) is not a file the library manager now tracks.
- `GET /metrics` – Prometheus-compatible text exposition. Existing
  Bandwidth-Controllarr gauges are preserved (`bw_qbit_*`, `bw_sab_*`,
  `bw_check_status`), and application-wide `aio_arr_*` metrics cover sync runs,
  integration health, scheduled jobs, Findarr activity, and Deletarr scans /
  deletions.
- `GET /api/trending?source=&media=&category=[&window=]` – normalised trending or
  popular items for the Trending page. `source` is `trakt|tmdb|seer`, `media` is
  `movie|show`, `category` is `trending|popular`, and `window` (`day|week`, TMDB
  only) defaults to `week` — the endpoint still accepts it, but the UI no longer
  exposes a time-window control. A failing/unconfigured source degrades to `[]`.
- `GET /api/trending/rating?imdb=` *or* `?media=&tmdb=` – the IMDb rating overlay
  `{ imdb_rating, imdb_votes }` via OMDb (resolving the IMDb id from TMDB when only
  a TMDB id is given), served from a bounded 24-hour cache.
- `POST /api/trending/add` – add `{ media_type, owner_user, slug, tmdb?, imdb?,
  trakt?, tvdb?, title? }` to an owned Trakt list and trigger a sync; returns
  `{ status: "added" | "added_pending_sync" }`.

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
- **Prometheus metrics:** `/metrics` exposes the legacy `bw_*` Bandwidth-
  Controllarr gauges plus `aio_arr_sync_*`, `aio_arr_service_*`,
  `aio_arr_scheduler_*`, `aio_arr_findarr_*`, and `aio_arr_deletarr_*` families.
  Labels are deliberately bounded to stable values such as service, status, app,
  mode, library, trigger, and job id.
- **Bandwidth-Controllarr** is off by default. When enabled, it polls
  qBittorrent and SABnzbd every `BANDWIDTH_CHECK_INTERVAL_SEC` seconds; if
  qBittorrent has active torrents, SABnzbd is paused, and resumed once the
  torrents go idle. Disabling the switch resumes SABnzbd if it had been paused
  by the loop. All control state is persisted in `SETTINGS_STORE_PATH`; the
  Prometheus metrics at `/metrics` use the same gauge names as the standalone
  source tool.
