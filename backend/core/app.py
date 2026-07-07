"""FastAPI application factory and lifespan wiring.

``main.py`` is a thin entrypoint; all wiring lives here so it can be exercised
by the test suite. The lifespan builds the shared context, starts the
scheduler, kicks off Trakt device auth when needed, loads modules, mounts the
API/webhook routers and finally serves the built React SPA.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from core import registry
from core.api import create_api_router
from core.app_metrics import observe_scheduler_job
from core.bandwidth_api import create_bandwidth_router
from core.clients.arr_client import ArrClient
from core.clients.omdb import OmdbClient
from core.clients.qbittorrent import QbittorrentClient
from core.clients.sabnzbd import SabnzbdClient
from core.clients.seer import SeerClient
from core.clients.tmdb import TmdbClient
from core.clients.trakt import TraktClient
from core.config import Settings
from core.context import AppContext
from core.db import Database
from core.deletarr_api import create_deletarr_router
from core.findarr_api import create_findarr_router
from core.logging import configure_logging, get_logger
from core.posters import PosterCache
from core.scheduler import SchedulerService
from core.services_api import create_services_router
from core.settings_store import SettingsStore
from core.status_checker import StatusChecker
from core.trakt_api import create_trakt_router
from core.trakt_auth import cancel_device_auth, start_device_auth
from core.trending_api import create_trending_router
from core.trending_sync import start_trending_sync
from core.webhooks import WebhookRegistry

# Location of the built frontend bundle (overridable in tests).
FRONTEND_DIST = Path("frontend/dist")

# The browser caches posters for this many days (Cache-Control: max-age=604800 in
# core.api). A churn TTL at or below this window can evict a poster the browser is
# still serving from its own cache, forcing a needless re-fetch, so a TTL this low
# is warned about at start-up.
_BROWSER_POSTER_CACHE_DAYS = 7

_log = get_logger("app")


def build_context(settings: Settings) -> AppContext:
    """Construct all shared services and wire them into an :class:`AppContext`."""
    database = Database(settings.DB_PATH)
    database.init_db()

    settings_store = SettingsStore(settings.SETTINGS_STORE_PATH)
    settings_store.load_or_seed(
        client_id=settings.TRAKT_CLIENT_ID,
        client_secret=settings.TRAKT_CLIENT_SECRET,
        services=settings.service_seeds,
        status_check_interval_seconds=settings.STATUS_CHECK_INTERVAL_SECONDS,
        sync_interval_minutes=settings.SYNC_INTERVAL_MIN,
        auto_remove_when_available=settings.AUTO_REMOVE_WHEN_AVAILABLE,
        bandwidth_control_enabled=settings.BANDWIDTH_CONTROL_ENABLED,
        bandwidth_check_interval_seconds=settings.BANDWIDTH_CHECK_INTERVAL_SEC,
        trending_sync_interval_minutes=settings.TRENDING_SYNC_INTERVAL_MIN,
        deletarr_movies_path=settings.DELETARR_MOVIES_PATH,
        deletarr_tv_path=settings.DELETARR_TV_PATH,
        deletarr_use_arr_source=settings.DELETARR_USE_ARR_SOURCE,
    )
    client_id, client_secret = settings_store.trakt_credentials()

    trakt = TraktClient(
        client_id=client_id,
        client_secret=client_secret,
        token_store_path=settings.TOKEN_STORE_PATH,
    )
    trakt.load_tokens()

    seer_url, seer_key = settings_store.service_connection("seer")
    seer = SeerClient(base_url=seer_url, api_key=seer_key)
    sonarr_url, sonarr_key = settings_store.service_connection("sonarr")
    sonarr = ArrClient(name="sonarr", base_url=sonarr_url, api_key=sonarr_key)
    radarr_url, radarr_key = settings_store.service_connection("radarr")
    radarr = ArrClient(name="radarr", base_url=radarr_url, api_key=radarr_key)

    tmdb = TmdbClient(api_key=settings_store.service_fields("tmdb")["api_key"])
    omdb = OmdbClient(api_key=settings_store.service_fields("omdb")["api_key"])
    sab_fields = settings_store.service_fields("sabnzbd")
    sabnzbd = SabnzbdClient(base_url=sab_fields["url"], api_key=sab_fields["api_key"])
    qbit_fields = settings_store.service_fields("qbittorrent")
    qbittorrent = QbittorrentClient(
        base_url=qbit_fields["url"], api_key=qbit_fields["api_key"]
    )

    ctx = AppContext(
        settings=settings,
        db=database,
        trakt=trakt,
        seer=seer,
        sonarr=sonarr,
        radarr=radarr,
        tmdb=tmdb,
        omdb=omdb,
        sabnzbd=sabnzbd,
        qbittorrent=qbittorrent,
        scheduler=SchedulerService(),
        webhooks=WebhookRegistry(),
        settings_store=settings_store,
    )
    ctx.status_checker = StatusChecker(ctx)
    ctx.poster_cache = PosterCache(
        cache_dir=settings.POSTER_CACHE_PATH, tmdb=tmdb, omdb=omdb
    )
    return ctx


async def _maybe_start_device_auth(ctx: AppContext) -> None:
    """Kick off Trakt device auth at start-up when creds exist but no token does.

    The flow runs through the shared :data:`AppContext.trakt_auth` session so the
    dashboard surfaces the same code/URL. Failures never crash start-up.
    """
    client_id, _ = ctx.settings_store.trakt_credentials()
    if not client_id or ctx.trakt.is_authenticated():
        return
    try:
        await start_device_auth(ctx)
    except Exception as exc:  # never crash startup on auth issues
        _log.exception("Trakt device auth failed to start: %s", exc)


@dataclass
class _PosterChurnConfig:
    """Cache + eviction bounds for the scheduled poster-churn job.

    APScheduler 4 cannot serialise a reference to a nested function, so the
    scheduled job must be the module-level :func:`_poster_churn_job`, which reads
    the active cache and bounds from this holder (populated by
    :func:`_start_poster_churn`). This mirrors the module-level job pattern used
    across ``backend/modules/*`` (e.g. ``bandwidth_controllarr.control_job``).
    """

    cache: PosterCache | None = None
    ttl_seconds: int = 0
    max_bytes: int = 0


_poster_churn = _PosterChurnConfig()


async def _poster_churn_job() -> None:
    """Scheduled entrypoint: evict aged/oversized posters in a worker thread.

    Filesystem work runs off the event loop via :func:`asyncio.to_thread`.
    """

    async def evict_posters() -> None:
        cache = _poster_churn.cache
        if cache is None:  # pragma: no cover - cache is set before scheduling
            return
        await asyncio.to_thread(
            cache.evict,
            max_age_seconds=_poster_churn.ttl_seconds,
            max_total_bytes=_poster_churn.max_bytes,
        )

    await observe_scheduler_job("poster_cache_churn", evict_posters)


async def _start_poster_churn(ctx: AppContext, settings: Settings) -> None:
    """Schedule the periodic poster-cache eviction (age + size bounded).

    Records the cache and settings-derived bounds on :data:`_poster_churn` so the
    module-level :func:`_poster_churn_job` can run them, then schedules that job.
    Skipped when no poster cache is configured.
    """
    if ctx.poster_cache is None:
        return
    if 0 < settings.POSTER_CACHE_TTL_DAYS <= _BROWSER_POSTER_CACHE_DAYS:
        _log.warning(
            "POSTER_CACHE_TTL_DAYS=%d is within the %d-day browser poster cache; "
            "actively-viewed posters may be evicted and re-fetched — use a larger TTL.",
            settings.POSTER_CACHE_TTL_DAYS,
            _BROWSER_POSTER_CACHE_DAYS,
        )
    _poster_churn.cache = ctx.poster_cache
    _poster_churn.ttl_seconds = settings.POSTER_CACHE_TTL_DAYS * 86_400
    _poster_churn.max_bytes = settings.POSTER_CACHE_MAX_MB * 1024 * 1024

    await ctx.scheduler.add_interval(
        _poster_churn_job,
        minutes=settings.POSTER_CACHE_CHURN_INTERVAL_MIN,
        id="poster_cache_churn",
    )


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA at ``/`` if present; otherwise serve a placeholder."""
    if FRONTEND_DIST.is_dir():
        index_file = FRONTEND_DIST / "index.html"

        @app.get("/", response_class=HTMLResponse)
        @app.get("/trending", response_class=HTMLResponse)
        @app.get("/list-syncarr", response_class=HTMLResponse)
        @app.get("/bandwidth-controllarr", response_class=HTMLResponse)
        @app.get("/findarr", response_class=HTMLResponse)
        @app.get("/deletarr", response_class=HTMLResponse)
        @app.get("/settings", response_class=HTMLResponse)
        async def _spa_entry() -> FileResponse:
            return FileResponse(index_file)

        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
        _log.info("serving frontend from %s", FRONTEND_DIST)
    else:
        _log.warning(
            "frontend bundle not found at %s; serving placeholder", FRONTEND_DIST
        )

        @app.get("/", response_class=HTMLResponse)
        async def _placeholder() -> str:
            return (
                "<h1>All-in-One ARR</h1>"
                "<p>The dashboard has not been built. Run "
                "<code>cd frontend &amp;&amp; npm run build</code>.</p>"
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown (resource lifecycle only).

    Routes are registered in :func:`create_app`; the lifespan starts the
    scheduler, kicks off device auth when needed, loads modules, and tears the
    resources down on exit.
    """
    ctx: AppContext = app.state.ctx
    _log.info("starting aio-arr with config: %s", app.state.settings.masked())

    await ctx.scheduler.start()
    await ctx.status_checker.start()

    await _maybe_start_device_auth(ctx)

    await registry.load_modules(ctx.scheduler, app, ctx)

    await _start_poster_churn(ctx, app.state.settings)

    await start_trending_sync(ctx)

    try:
        yield
    finally:
        cancel_device_auth(ctx)
        await ctx.status_checker.stop()
        await ctx.scheduler.stop()
        await ctx.trakt.aclose()
        await ctx.seer.aclose()
        await ctx.sonarr.aclose()
        await ctx.radarr.aclose()
        await ctx.tmdb.aclose()
        await ctx.omdb.aclose()
        await ctx.sabnzbd.aclose()
        await ctx.qbittorrent.aclose()
        ctx.db.close()


def create_app() -> FastAPI:
    """Build the FastAPI application: config, context, routes and lifespan."""
    settings = Settings()
    configure_logging(settings.LOG_LEVEL)
    ctx = build_context(settings)

    app = FastAPI(title="All-in-One ARR", lifespan=lifespan)
    app.state.ctx = ctx
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    async def status(request: Request) -> dict[str, int]:
        return request.app.state.ctx.db.counts_by_status()

    # Register all routes up front; the webhook handlers are populated by the
    # modules during the lifespan, but requests only arrive after startup.
    app.include_router(create_api_router(ctx))
    app.include_router(create_trakt_router(ctx))
    app.include_router(create_services_router(ctx))
    app.include_router(create_bandwidth_router(ctx))
    app.include_router(create_findarr_router(ctx))
    app.include_router(create_deletarr_router(ctx))
    app.include_router(create_trending_router(ctx))
    app.include_router(ctx.webhooks.router)

    # Prometheus metrics are mounted before the SPA catch-all so they are
    # served directly instead of being swallowed by the React router fallback.
    app.mount("/metrics", make_asgi_app())
    _mount_frontend(app)

    return app
