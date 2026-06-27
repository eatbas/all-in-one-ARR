# Implementation Plan

Port the **Bandwidth-Controllarr** download-priority controller from
`../ern-nas/media-helper-stack/bandwidth-controllarr/` into this application as a
first-class feature: a new **Bandwidth-Controllarr** entry in the left menu, a
live status/control page, and a backend module that — on a short interval —
pauses SABnzbd while qBittorrent has active torrents and resumes it when the
torrents go idle, while also exposing the source tool's Prometheus-compatible
`/metrics` endpoint.

## Objective

Reproduce the source tool's full behaviour inside this app's existing
architecture (FastAPI auto-loading module + React/TS feature page), reusing the
already-managed qBittorrent and SABnzbd service connections rather than adding
new credentials.

User-visible result — a new **Bandwidth-Controllarr** page (left menu) that:

1. **Shows live status** of both download clients side by side — qBittorrent
   (download speed, active downloads, queue size) and SABnzbd (the same, plus a
   **PAUSED/RESUMED** state badge), with a system-status banner and the
   timestamp of the last control check. Auto-refreshes.
2. **Master enable/disable switch** — when **on** ("control"), the engine pauses
   SABnzbd whenever qBittorrent has active torrents and resumes it when none
   remain; when **off** ("monitoring only"), it never pauses and resumes SABnzbd
   if it had previously paused it, so disabling restores Usenet downloads.
3. **Configurable check interval** (seconds) for the control loop.
4. **Prometheus metrics link** to `/metrics`, matching the source dashboard's
   monitoring affordance.

Operational result — a Prometheus exporter at **`GET /metrics`** that exposes
the same Bandwidth-Controllarr gauges as the source tool, so existing scrapes
can move from the standalone service to this app without changing metric names.

Behaviour ported verbatim from the source decision logic:

- `not enabled`  → status "Monitoring only"; if SABnzbd is paused, **resume** it.
- `has_torrents` → status "Active torrents — SABnzbd paused"; if not paused, **pause**.
- otherwise      → status "No active torrents"; if paused, **resume**.

**Reused, not rebuilt (resolved during planning):**

- **Connections & test buttons.** qBittorrent and SABnzbd are already managed
  services (`core/service_registry.py`), each with URL + API key, a **Test
  connection** button (`POST /api/services/{name}/test`), and live clients on
  `ctx.qbittorrent` / `ctx.sabnzbd`. The Bandwidth page links to **Settings** for
  connection config instead of duplicating credential forms (the source tool's
  in-page URL/test modal is intentionally dropped — this app centralises
  connections in Settings).
- **Prometheus `/metrics`.** In scope. The source mounts
  `prometheus_client.make_asgi_app()` at `/metrics` and updates gauges in the
  scheduler loop. This app will add the same exporter path and source-compatible
  gauge names, backed by the integrated control loop rather than a separate
  service.

## Current state

Resolved planning target: working tree on `main` (clean at planning time). No
branch ref supplied; the plan is written against the current `main`.

Stack (verified from the repo):

- **Backend:** FastAPI 0.118+, Python 3.11+, async `httpx` clients, raw
  `sqlite3` (no ORM), APScheduler 4 (pre-release) behind
  `backend/core/scheduler.py`, single Uvicorn worker. Modules auto-load from
  `backend/modules/<name>/` via `core/registry.py` calling each module's
  `setup(scheduler, app, ctx)`.
- **Metrics:** no Prometheus dependency exists yet in this repo. The source
  tool uses unpinned `prometheus-client`; current PyPI latest checked during
  planning is `0.25.0`. Context7 docs for the official Python client confirm
  `make_asgi_app()` for ASGI/FastAPI mounting and `Gauge(...).set(...)` for
  gauge updates; because no version is pinned in either repo, use
  `prometheus-client>=0.25,<1.0` unless lockfile resolution requires a narrower
  compatible version.
- **Frontend:** React 19 + TypeScript + Tailwind 4 (Vite), React Router 7,
  TanStack Query, Radix UI primitives, `sonner` toasts, native `fetch`.
- **Coverage gates (hard constraint):**
  - Backend: `cd backend && pytest` runs with `--cov-fail-under=100`.
  - Frontend: `npm run test:cov` enforces `thresholds: { 100: true }`.
  - **Every new backend and frontend line must be covered by tests or the build
    fails.** This is the dominant cost driver of this plan.

Relevant existing code (all verified by reading the files):

- `backend/core/clients/qbittorrent.py` — `QbittorrentClient`. Has `__init__`,
  `update_credentials`, `test_connection` (Bearer-auth against
  `/api/v2/app/version`), `aclose`. **No stats method** — must be added.
- `backend/core/clients/sabnzbd.py` — `SabnzbdClient`. Has `__init__`,
  `update_credentials`, `test_connection` (`mode=queue`), `aclose`. **No
  stats/pause/resume** — must be added.
- `backend/core/scheduler.py` — `SchedulerService.add_interval(func, *, minutes,
  id)` / `reschedule_interval(...)`. **Minutes only**; the control loop needs
  **second-level** intervals — wrapper must be extended.
- `backend/core/settings_store.py` — `SettingsStore`, thread-safe JSON store.
  Pattern to mirror exactly: `auto_remove_when_available` (bool getter/setter +
  persisted in `_save_locked` payload + included in `masked()`) and
  `status_check_interval_seconds` (int with a `VALID_*` frozenset + normaliser).
- `backend/core/service_registry.py` — declares `qbittorrent` and `sabnzbd`
  services already; no change needed here.
- `backend/core/context.py` — `AppContext` already carries `qbittorrent`,
  `sabnzbd`, `scheduler`, `settings_store`, `db`. Module callables are added as
  optional fields (`sync_now`, `remove_available`, …); follow that pattern.
- `backend/core/app.py` — `create_app()` registers **all routers up front**
  (`create_api_router`, `create_trakt_router`, `create_services_router`,
  webhooks) **before** `_mount_frontend(app)` mounts the SPA catch-all at `/`.
  `lifespan` starts the scheduler, then `registry.load_modules(...)`. **A module
  cannot add a FastAPI router during lifespan** — it would be appended after the
  `/` StaticFiles mount and shadowed. The Bandwidth router therefore lives in a
  core router file included in `create_app()` (the established pattern for
  `trakt_api.py` / `services_api.py`), while the module owns the loop + state.
  The `/metrics` ASGI app must also be mounted in `create_app()` before the SPA
  catch-all.
- `backend/modules/list_syncarr/__init__.py` — the reference module: a
  module-level `_CONTEXT` (APScheduler 4 needs top-level importable job
  callables, not closures), a top-level `poll_job()` resolving that context,
  `register_context(ctx)`, and an async `setup()` that schedules the job and sets
  `ctx.*` callables. **Bandwidth-Controllarr follows this shape exactly.**
- `backend/core/config.py` — `Settings(BaseSettings)`; `AUTO_REMOVE_WHEN_AVAILABLE`
  and `SYNC_INTERVAL_MIN` are seeded into the store via `load_or_seed(...)`.
- Frontend: `shared/layout/nav-config.tsx` (`NAV_ITEMS`), `App.tsx` (route
  table), `shared/lib/api.ts` (typed `fetch` wrapper), `shared/lib/queries.ts`
  (TanStack hooks + `queryKeys`), `features/list-syncarr/ListSyncarr.tsx`
  (tabbed page + localStorage active-tab), `features/list-syncarr/tabs/
  ListSettings.tsx` (Switch + Select + mutation hooks — the exact control
  pattern to mirror). UI primitives present: `switch`, `select`, `card`, `tabs`,
  `badge`, `button` — **no new shadcn component needed.**
- Source metrics implementation: `../ern-nas/media-helper-stack/
  bandwidth-controllarr/src/main.py` mounts `make_asgi_app()` at `/metrics`;
  `src/scheduler.py` defines gauges `bw_qbit_active_count`,
  `bw_qbit_speed_mbps`, `bw_qbit_queue_size`, `bw_sab_active_count`,
  `bw_sab_paused`, `bw_sab_speed_mbps`, `bw_sab_queue_size`, and
  `bw_check_status`, updating them on each scheduler iteration and setting
  zeros when stats are unavailable.

## Assumptions and constraints

- **Default OFF.** The master switch defaults to disabled ("monitoring only").
  The source defaults to enabled, but this app's convention is that actions
  changing external state are opt-in (`auto_remove_when_available` defaults
  `False`). Pausing a user's SABnzbd downloads is such an action. Seedable via a
  new env var so a deployment can opt in. **Decision; revisit only on request.**
- **Reuse existing clients/connections.** No new env credentials; qBittorrent
  and SABnzbd connections come from the existing service store.
- **Module behaviour in `modules/bandwidth_controllarr/`; HTTP endpoints in a
  core router `core/bandwidth_api.py`** (justified above — SPA mount ordering).
  This mirrors `list_syncarr` (logic in module, endpoints in core).
- **No new global mutable singletons beyond the established module-level
  `_CONTEXT`/state pattern** already used by `list_syncarr` (documented
  APScheduler-4 constraint). Live control state (status string, last-run
  timestamp, last-known SAB paused flag) is a small module-level object read by
  the request handler and written by the control job; both run in the **same
  single-threaded event loop** (scheduler is in-process async, single worker), so
  no lock is required. State that must survive restart (`enabled`,
  `check_interval_seconds`) lives in `SettingsStore`.
- **Idempotent control.** Each tick checks the current SAB paused state before
  issuing pause/resume, so overlapping/coalesced ticks are harmless. Activity is
  logged via `ctx.db.add_activity` **only on an actual pause/resume transition**,
  never every tick (honours the "avoid low-signal polling noise" guidance).
- **Prometheus parity.** Preserve the source metric names exactly and avoid
  labels for the first implementation; this keeps the scrape surface stable and
  avoids unnecessary cardinality. Metrics are process-local, matching the
  single-worker assumption. qBittorrent/SABnzbd unavailable states set their
  gauges to zero; `bw_check_status` is `1` after a completed control tick and
  `0` after an unexpected control-loop exception.
- **100% coverage** on both ends is mandatory; every new file ships with tests in
  the same phase.
- **British English** throughout comments/docs. **No commits** (planning skill;
  `apply-plan` will execute).

## Progress tracker

- **Overall status:** Automated verification complete; manual end-to-end pending
- **Current phase:** Phase 3 (automated complete, manual e2e pending)
- **Last updated:** Phase 3 automated verification complete
- **Phases:** 0 Foundations · 1 Backend clients + control loop + API · 2 Frontend
  page + menu · 3 Docs + full verification

---

## Phase 0: Foundations (config, settings store, scheduler seconds, dependency)

**Goal:** Add the persistent settings and the second-level scheduler capability
the control loop depends on, with tests, before any feature wiring. Establish a
green baseline.

**Likely files:**

- `backend/pyproject.toml` (add `prometheus-client`)
- `backend/core/scheduler.py` (extend `add_interval` / `reschedule_interval`)
- `backend/core/settings_store.py` (new bandwidth fields + getters/setters)
- `backend/core/config.py` (new env settings)
- `backend/core/app.py` (`build_context` → pass new seeds to `load_or_seed`)
- `.env.example` (document new vars)
- `backend/tests/` (scheduler + settings-store tests)

**Checklist:**

- [x] Establish baseline: run `cd backend && pytest` and `cd frontend && npm run
      test:cov` + `npm run build`; record that they pass before changes.
- [x] `pyproject.toml`: add runtime dependency
      `prometheus-client>=0.25,<1.0`. Since neither this repo nor the source
      service pins a version, document that the plan uses current official
      Python-client docs and latest PyPI stable checked during planning.
- [x] `scheduler.py`: extend `add_interval` to
      `add_interval(func, *, minutes: int = 0, seconds: int = 0, id: str)` and
      pass both to `IntervalTrigger(minutes=minutes, seconds=seconds)`; same for
      `reschedule_interval`. Preserve the existing `minutes=`-only call sites
      (`list_syncarr`) unchanged. Guard against `minutes == 0 and seconds == 0`.
- [x] `config.py`: add `BANDWIDTH_CONTROL_ENABLED: bool = False` and
      `BANDWIDTH_CHECK_INTERVAL_SEC: int = 15` to `Settings`; include both in any
      `masked()` output if other scalars are listed there.
- [x] `settings_store.py`: add a `VALID_BANDWIDTH_INTERVALS` frozenset (e.g.
      `{10, 15, 30, 60}`) and `_normalise_bandwidth_interval`; add private fields
      `_bandwidth_control_enabled: bool` and `_bandwidth_check_interval_seconds:
      int`; getters `bandwidth_control_enabled()` /
      `bandwidth_check_interval_seconds()`; setters
      `update_bandwidth_control_enabled(bool)` /
      `update_bandwidth_check_interval(int)`; persist both in `_save_locked`
      payload; read them in `_load_locked` (tolerate absence → defaults); seed
      them in `load_or_seed`; surface both in `masked()`.
- [x] `app.py` `build_context`: pass `bandwidth_control_enabled=settings.
      BANDWIDTH_CONTROL_ENABLED` and `bandwidth_check_interval_seconds=settings.
      BANDWIDTH_CHECK_INTERVAL_SEC` into `settings_store.load_or_seed(...)`.
- [x] `.env.example`: add `BANDWIDTH_CONTROL_ENABLED` and
      `BANDWIDTH_CHECK_INTERVAL_SEC` with comments and defaults.
- [x] Tests: scheduler `seconds=` path (interval set, reschedule replaces);
      settings-store seed/load/persist/normalise/masked for the new fields,
      including the migration case where an older JSON store lacks the keys.

**Verification:** `cd backend && pytest` stays at 100% coverage with the new
branches covered; `python -c "import prometheus_client"` succeeds after
dependency installation.

**Notes:** Phase 0 complete. Added `prometheus-client>=0.25,<1.0` dependency; extended `SchedulerService.add_interval` / `reschedule_interval` to accept `seconds=`; added `BANDWIDTH_CONTROL_ENABLED` and `BANDWIDTH_CHECK_INTERVAL_SEC` env settings; extended `SettingsStore` with bandwidth getters/setters/persistence/masking and migration for older stores lacking the keys; wired seeds through `build_context`; updated `.env.example`; added scheduler and settings-store tests.

---

## Phase 1: Backend — client methods, control module, API router

**Goal:** Implement the stat/pause/resume client methods, the control loop
module, and the core HTTP router, all wired and fully tested.

**Likely files:**

- `backend/core/clients/qbittorrent.py` (add `get_stats`)
- `backend/core/clients/sabnzbd.py` (add `get_stats`, `pause`, `resume`)
- `backend/core/bandwidth_metrics.py` (new: source-compatible Prometheus gauges
  + update helper)
- `backend/modules/bandwidth_controllarr/__init__.py` (new: `setup`, `_CONTEXT`,
  `control_job`, live-state object, control callables)
- `backend/modules/bandwidth_controllarr/control.py` (new: decision logic +
  stat-gathering helper, kept ≤ ~80 lines, complexity < 10)
- `backend/core/bandwidth_api.py` (new: `create_bandwidth_router(ctx)`)
- `backend/core/context.py` (add optional bandwidth callables/state to
  `AppContext`)
- `backend/core/app.py` (`create_app` → `app.include_router(create_bandwidth_
  router(ctx))` and `app.mount("/metrics", make_asgi_app())` **before**
  `_mount_frontend`)
- `backend/tests/` (client, control-logic, module-setup, and router tests)

**Checklist:**

- [x] `qbittorrent.py`: add `async def get_stats(self) -> dict` returning
      `{online, speed_mbps, active_downloads, queue_size}`. GET
      `/api/v2/transfer/info` (→ `dl_info_speed` bytes/s ÷ 1e6, rounded) and
      `/api/v2/torrents/info` with the existing `Authorization: Bearer` +
      `Referer` headers; count states `downloading, stalledDL, forcedDL, metaDL,
      allocating` as active and `queuedDL` as queued. Return
      `{online: False, …zeros}` on any `httpx.HTTPError`, non-200, or parse
      error — never raise (mirror `test_connection`'s defensive style). Skip when
      the API key is blank.
- [x] `sabnzbd.py`: add `async def get_stats(self) -> dict` returning
      `{online, speed_mbps, active_downloads, queue_size, paused}` via
      `mode=queue` (parse the `"1.2 M"` / `"500 K"` speed string to MB/s; count
      `slots` with `status == "Downloading"`; read `paused`). Add `async def
      pause(self)` (`mode=pause`) and `async def resume(self)` (`mode=resume`),
      each returning a bool ok and never raising. Reuse the `apikey`/`output=json`
      query pattern.
- [x] `context.py`: add optional fields to `AppContext` —
      `bandwidth_status: Callable[[], Awaitable[dict]] | None = None` and
      `bandwidth_update_settings: Callable[..., Awaitable[dict]] | None = None`
      (single entry point applying `enabled`/`check_interval_seconds`, reschedules
      the loop on interval change, returns the new settings).
- [x] `core/bandwidth_metrics.py`: define exactly the source gauge names:
      `bw_qbit_active_count`, `bw_qbit_speed_mbps`, `bw_qbit_queue_size`,
      `bw_sab_active_count`, `bw_sab_paused`, `bw_sab_speed_mbps`,
      `bw_sab_queue_size`, and `bw_check_status`. Add a small
      `update_bandwidth_metrics(qb_stats, sab_stats, *, check_ok: bool)` helper
      that accepts the same stat dictionaries returned by the clients, writes
      zeros for offline/failed clients, converts `paused` to `1`/`0`, and keeps
      metric-writing logic out of the control decision function.
- [x] `modules/bandwidth_controllarr/control.py`: pure-ish helpers —
      `gather_status(ctx) -> dict` (calls both clients' `get_stats`, merges the
      live control state: enabled, status string, last-run ISO timestamp,
      interval) and `apply_control(ctx) -> None` (the ported decision logic;
      issues pause/resume only on a state change; updates the live-state object;
      logs a one-line activity entry on each actual transition; calls
      `update_bandwidth_metrics(..., check_ok=True)` after successful stat
      gathering/control and `update_bandwidth_metrics(..., check_ok=False)` if an
      unexpected exception is caught before re-raising or recording an error
      state).
- [x] `modules/bandwidth_controllarr/__init__.py`: module-level `_CONTEXT` +
      `_STATE` (dataclass: `enabled` mirror, `status`, `last_run_at`,
      `sab_paused`), `register_context`, `_require_context`, top-level
      `async def control_job()` → `apply_control(_require_context())`, and
      `async def setup(scheduler, app, ctx)` that: seeds `_STATE.enabled` from
      `ctx.settings_store.bandwidth_control_enabled()`; schedules `control_job`
      via `scheduler.add_interval(..., seconds=ctx.settings_store.
      bandwidth_check_interval_seconds(), id="bandwidth_control")`; sets
      `ctx.bandwidth_status = lambda: gather_status(ctx)` and
      `ctx.bandwidth_update_settings = <closure applying settings + reschedule>`.
- [x] `core/bandwidth_api.py`: `create_bandwidth_router(ctx)` with
      `prefix="/api/bandwidth"` and Pydantic response/request models —
      `GET /api/bandwidth/status` → `ctx.bandwidth_status()`;
      `PUT /api/bandwidth/settings` (`{enabled?: bool, check_interval_seconds?:
      int}`) → `ctx.bandwidth_update_settings(...)` then return updated state.
      Validate the interval against the store's allowed set (reject others with
      422/400 consistent with existing endpoints).
- [x] `app.py`: `app.include_router(create_bandwidth_router(ctx))` immediately
      after `create_services_router`; `app.mount("/metrics", make_asgi_app())`
      after API routers and **before** `_mount_frontend(app)`. The source service
      mounts the Prometheus ASGI app directly at `/metrics`; follow that pattern
      so the route is not shadowed by the SPA catch-all.
- [x] Tests (mock `httpx` exactly as the existing client tests do): qBittorrent
      `get_stats` success + all failure branches; SABnzbd `get_stats` (speed
      parsing M/K/raw) + `pause`/`resume`; `apply_control` for the three branches
      ×(already-in-target-state vs needs-change), incl. the disable-resumes path
      and the activity-log-on-transition assertion; `gather_status` merge;
      metrics update helper (all gauges set from stats, offline zeros,
      `bw_check_status` success/failure); `setup` wiring (job scheduled with
      `seconds=`, callables set); router endpoints (status shape, settings PUT
      applies + reschedules + validates); assembled app exposes `/metrics` before
      the SPA mount and includes the `bw_*` gauge names in the response.

**Verification:** `cd backend && pytest` at 100%; manually hit
`GET /api/bandwidth/status`, `PUT /api/bandwidth/settings`, and `GET /metrics`
against a running backend (curl) and confirm SABnzbd pause/resume toggles with a
live qBittorrent download while the `bw_*` gauges change (see Phase 3 manual
steps).

**Notes:** Phase 1 complete. Implemented qBittorrent/SABnzbd stat/pause/resume client methods, source-compatible Prometheus gauges in `core/bandwidth_metrics.py`, the control decision logic in `modules/bandwidth_controllarr/control.py`, module setup/scheduler wiring in `modules/bandwidth_controllarr/__init__.py', the `/api/bandwidth` router in `core/bandwidth_api.py`, and wired the router and `/metrics` ASGI mount into `core/app.py`. Added comprehensive tests; full backend suite passes at 100% coverage. One pre-existing Windows SQLite WAL test was also fixed so the backend coverage gate is green.

---

## Phase 2: Frontend — menu entry, page, tabs, API client, hooks

**Goal:** Add the **Bandwidth-Controllarr** menu item, route, and a tabbed page
(**Status** + **Settings**) mirroring the List-Syncarr structure, fully tested.

**Likely files:**

- `frontend/src/shared/layout/nav-config.tsx` (add `NAV_ITEMS` entry)
- `frontend/src/App.tsx` (add route)
- `frontend/src/shared/lib/api.ts` (types + endpoint functions)
- `frontend/src/shared/lib/queries.ts` (`queryKeys` + hooks/mutations)
- `frontend/src/features/bandwidth-controllarr/BandwidthControllarr.tsx` (page)
- `frontend/src/features/bandwidth-controllarr/bandwidth-controllarr-tab.ts`
- `frontend/src/features/bandwidth-controllarr/tabs/Status.tsx`
- `frontend/src/features/bandwidth-controllarr/tabs/BandwidthSettings.tsx`
- `frontend/src/features/bandwidth-controllarr/components/client-card.tsx`
  (shared qBittorrent/SABnzbd stat card)
- matching `*.test.tsx` for every component/page above

**Checklist:**

- [x] `nav-config.tsx`: add `{ title: "Bandwidth-Controllarr", to:
      "/bandwidth-controllarr", icon: <a lucide icon, e.g. GaugeIcon>,
      description: "Pause Usenet while torrents download" }` (placement: after
      List-Syncarr, before Settings).
- [x] `App.tsx`: add `<Route path="/bandwidth-controllarr"
      element={<BandwidthControllarr />} />`.
- [x] `api.ts`: add `BandwidthClientStats`, `BandwidthStatus`,
      `BandwidthSettingsUpdate` types (mirroring backend models) and
      `getBandwidthStatus()` (GET) + `updateBandwidthSettings(body)` (PUT JSON).
- [x] `queries.ts`: add `queryKeys.bandwidthStatus`; `useBandwidthStatus()` with
      a page-appropriate `refetchInterval` (≈3 000 ms — faster than the 10 s
      default, matching the source's near-real-time feel); `useUpdateBandwidth
      Settings()` mutation invalidating `bandwidthStatus` and toasting via
      `sonner` on error (follow `useUpdateAutoRemoveWhenAvailable`).
- [x] `BandwidthControllarr.tsx`: tabbed page (Status default, Settings) with the
      localStorage active-tab pattern from `ListSyncarr.tsx`; `bandwidth-
      controllarr-tab.ts` holds the storage key + valid-tabs list.
- [x] `tabs/Status.tsx`: system-status banner (status text + colour badge:
      danger when torrents active, success otherwise + last-check time), the
      master **Switch** (`useUpdateBandwidthSettings({enabled})`, mirrors
      ListSettings' Switch), and two `client-card`s (qBittorrent + SABnzbd; the
      SABnzbd card shows the PAUSED/RESUMED badge). A short note links to
      **Settings** for connection config.
- [x] `tabs/BandwidthSettings.tsx`: a `Select` for the check interval (options =
      backend `VALID_BANDWIDTH_INTERVALS`) wired to `useUpdateBandwidthSettings
      ({check_interval_seconds})`, plus the same master enable Switch (so the
      control lives in both the obvious places, as in the source). Include an
      external-link button to `/metrics`, matching the source dashboard's
      Prometheus metrics link.
- [x] `components/client-card.tsx`: presentational card (props: label, online,
      speed, active, queue, optional paused) reused by both clients (DRY — avoids
      two near-identical card blocks).
- [x] Tests: page (tab switching + persistence), Status (renders both cards from
      mocked status, toggles enable, reflects paused/active badges), Settings
      (changes interval, toggles enable, renders `/metrics` link), client-card
      (online/offline + paused variants), and api/queries coverage via the
      existing mock-query harness. Cover loading/empty states to satisfy the
      100% gate.

**Verification:** `cd frontend && npm run test:cov` at 100%; `npm run build`
type-checks clean; `npm run dev` shows the new menu item and a working page
against the dev-proxied backend.

**Notes:** Phase 2 complete. Added the `Bandwidth-Controllarr` nav item, route,
page, TanStack Query hooks, API client functions, and presentational components,
all with matching tests. The Status and Settings tabs both expose the master
enable switch; the Status tab shows live qBittorrent/SABnzbd cards and the
control-state banner; the Settings tab lets users change the check interval and
open `/metrics`. Frontend coverage remains at 100%.

---

## Phase 3: Docs and full verification

**Goal:** Document the feature and prove the whole change end to end.

**Likely files:**

- `README.md` (new module section, endpoints, settings, page description)
- `.env.example` (already touched in Phase 0 — confirm)

**Checklist:**

- [x] `README.md`: add Bandwidth-Controllarr to the modules list and the menu
      description; document `GET /api/bandwidth/status` and `PUT
      /api/bandwidth/settings` under **Endpoints**; document `GET /metrics`, the
      source-compatible `bw_*` Prometheus gauges, the new env vars, and the
      default-OFF behaviour; note the deliberate omission of an in-page
      connection form — configured in Settings.
- [x] Update the architecture tree / "Adding a module" notes if they enumerate
      modules.
- [x] Full backend run: `cd backend && pytest` (100% coverage).
- [x] Full frontend run: `cd frontend && npm run test:cov` (100%) and
      `npm run build` (type-check).
- [ ] Manual end-to-end (documented in Verified results): start backend +
      frontend, configure qBittorrent/SABnzbd in Settings, enable control, start a
      torrent → confirm SABnzbd pauses and the page shows "Active torrents —
      paused"; finish/remove torrents → confirm resume; disable the switch →
      confirm resume; curl `/metrics` before and after the scenario and confirm
      the `bw_qbit_*`, `bw_sab_*`, and `bw_check_status` gauges reflect the
      observed state.

**Verification:** all three automated commands green; manual scenario pending.

**Notes:** Phase 3 automated verification complete. `README.md` documents the
feature, endpoints, metrics, env vars, and default-off behaviour; `.env.example`
already includes the new variables. Backend and frontend test suites both pass
at 100% coverage and the frontend production build type-checks cleanly. The live
end-to-end scenario (start a torrent, watch SABnzbd pause, then resume) was not
performed in this environment because no real qBittorrent/SABnzbd instances are
available; it should be run on the target deployment before merge.

---

## Verified results

Automated verification commands and their outputs.

- Baseline (pre-change):
  - `cd backend && pytest`: 349 passed, 1 failed (pre-existing Windows file-lock failure in `test_disk_size_bytes_handles_partial_sidecars`; coverage 99.91% because `core/db.py:310-311` not exercised on this run).
  - `cd frontend && npm run test:cov`: 258 passed, 100% coverage.
  - `cd frontend && npm run build`: passed (verified separately).
- Phase 0:
  - `cd backend && pytest tests/test_scheduler.py tests/test_settings_store.py tests/test_config.py tests/test_app.py`: 57 passed.
  - New foundation code (`scheduler.py`, `settings_store.py`, `config.py`) at 100% coverage in targeted runs; full-suite coverage is still blocked by the pre-existing Windows SQLite WAL test failure.
- Phase 1:
  - `cd backend && pytest`: 414 passed, 100% coverage.
  - Fixed pre-existing `tests/test_db.py::test_disk_size_bytes_handles_partial_sidecars` Windows file-lock failure by mocking `os.path.getsize` to raise `FileNotFoundError` for the WAL suffix instead of trying to unlink an open file.
- Phase 2:
  - `cd frontend && npm run test:cov`: 286 passed, 100% coverage (all new Bandwidth-Controllarr components, hooks, API client, and route covered).
  - `cd frontend && npm run build`: passed (Vite production build, type-check clean).
- Phase 3:
  - `cd backend && pytest`: 414 passed, 100% coverage.
  - `cd frontend && npm run test:cov`: 286 passed, 100% coverage.
  - `cd frontend && npm run build`: passed.
  - `README.md` updated with feature overview, configuration variables, page description, and endpoints.
  - `.env.example` already contains `BANDWIDTH_CONTROL_ENABLED=false` and `BANDWIDTH_CHECK_INTERVAL_SEC=15`.
  - Manual end-to-end scenario not executed in this environment (no live qBittorrent/SABnzbd instances); reserved for target deployment before merge.
- Post-review fixes (plan_review_codex.md):
  - `cd backend && pytest`: 433 passed, 100% coverage (after clearing stale `.coverage`/`__pycache__`).
  - `cd frontend && npm run test:cov`: 286 passed, 100% coverage (split into `queries.dashboard.test.tsx`, `queries.list-syncarr.test.tsx`, `queries.settings.test.tsx`, `queries.bandwidth.test.tsx`).
  - `cd frontend && npm run lint`: passed.
  - `cd frontend && npm run build`: passed.
  - Hardened `sabnzbd.get_stats()` and `qbittorrent.get_stats()` to return offline zeros for invalid-key, non-dict, non-list, and non-numeric response shapes.
  - Hardened `sabnzbd.test_connection()`, `pause()`, and `resume()` against non-dict JSON bodies.
  - `apply_control()` now updates the local SAB stats after a successful pause/resume so Prometheus metrics reflect the transition within the same tick.
  - `bandwidth_update_settings(enabled=False)` now runs the control decision immediately, restoring SABnzbd before the HTTP response returns.
  - Added test coverage for `bandwidth_update_settings(check_interval_seconds=...)` rescheduling the control job.
  - Restored `frontend/package-lock.json` to the baseline to remove unrelated native-package metadata churn.
  - Manual end-to-end scenario still pending (no live download clients in this environment).

## Risks

- **Coverage gate (highest cost).** 100% on both ends means every client failure
  branch, every control branch, every component state, and loading/empty paths
  need tests. Budget the bulk of effort here. The defensive "never raise, return
  zeros/false" client style makes the failure branches straightforward to cover.
- **APScheduler 4 second-level interval.** `IntervalTrigger(seconds=…)` is
  standard, but the pre-release scheduler is isolated behind `scheduler.py`;
  verify the job actually fires at the sub-minute cadence in a manual run (a
  short interval is easy to observe in logs).
- **SPA mount shadowing.** The Bandwidth router **must** be included before
  `_mount_frontend(app)` in `create_app()`; if added during lifespan it will be
  shadowed by the `/` StaticFiles mount (verified failure mode). Covered by an
  endpoint test that hits `/api/bandwidth/status` through the assembled app.
- **External-state side effect.** The control loop pauses a user's real SABnzbd
  queue. Mitigated by default-OFF, the resume-on-disable path, and idempotent
  per-tick checks. Manual verification (Phase 3) is mandatory before merge.
- **Request volume.** `GET /api/bandwidth/status` queries both clients live on
  each ~3 s poll. Acceptable for a single-user self-hosted tool; if it proves
  heavy, switch the endpoint to return the control loop's last-cached stats
  (noted as a fallback, not implemented by default).
- **Prometheus global registry collisions.** `prometheus_client.Gauge` registers
  names globally by default. Keep metric definitions in one importable module,
  import that module rather than recreating gauges in tests or setup code, and
  cover repeated app creation in tests so duplicate metric registration fails
  early if introduced.
- **Scope creep.** Keep an in-page connection form out (resolved above) unless
  the user asks for it.
```
