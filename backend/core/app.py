"""FastAPI application factory and lifespan wiring.

``main.py`` is a thin entrypoint; all wiring lives here so it can be exercised
by the test suite. The lifespan builds the shared context, starts the
scheduler, kicks off Trakt device auth when needed, loads modules, mounts the
API/webhook routers and finally serves the built React SPA.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from core import registry
from core.api import create_api_router
from core.clients.arr_client import ArrClient
from core.clients.jellyseerr import JellyseerrClient
from core.clients.omdb import OmdbClient
from core.clients.qbittorrent import QbittorrentClient
from core.clients.sabnzbd import SabnzbdClient
from core.clients.tmdb import TmdbClient
from core.clients.trakt import TraktClient
from core.config import Settings
from core.context import AppContext, DryRunFlag
from core.db import Database
from core.logging import configure_logging, get_logger
from core.posters import PosterCache
from core.scheduler import SchedulerService
from core.services_api import create_services_router
from core.settings_store import SettingsStore
from core.status_checker import StatusChecker
from core.trakt_api import create_trakt_router
from core.trakt_auth import cancel_device_auth, start_device_auth
from core.webhooks import WebhookRegistry

# Location of the built frontend bundle (overridable in tests).
FRONTEND_DIST = Path("frontend/dist")

_log = get_logger("app")


def build_context(settings: Settings) -> AppContext:
    """Construct all shared services and wire them into an :class:`AppContext`."""
    flag = DryRunFlag(settings.DRY_RUN)

    database = Database(settings.DB_PATH)
    database.init_db()

    settings_store = SettingsStore(settings.SETTINGS_STORE_PATH)
    settings_store.load_or_seed(
        client_id=settings.TRAKT_CLIENT_ID,
        client_secret=settings.TRAKT_CLIENT_SECRET,
        services=settings.service_seeds,
        status_check_interval_seconds=settings.STATUS_CHECK_INTERVAL_SECONDS,
        sync_interval_minutes=settings.SYNC_INTERVAL_MIN,
    )
    client_id, client_secret = settings_store.trakt_credentials()

    trakt = TraktClient(
        client_id=client_id,
        client_secret=client_secret,
        token_store_path=settings.TOKEN_STORE_PATH,
        dry_run_provider=flag,
    )
    trakt.load_tokens()

    js_url, js_key = settings_store.service_connection("jellyseerr")
    jellyseerr = JellyseerrClient(
        base_url=js_url, api_key=js_key, dry_run_provider=flag
    )
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
        jellyseerr=jellyseerr,
        sonarr=sonarr,
        radarr=radarr,
        tmdb=tmdb,
        omdb=omdb,
        sabnzbd=sabnzbd,
        qbittorrent=qbittorrent,
        scheduler=SchedulerService(),
        webhooks=WebhookRegistry(),
        dry_run_flag=flag,
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


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA at ``/`` if present; otherwise serve a placeholder."""
    if FRONTEND_DIST.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa"
        )
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

    try:
        yield
    finally:
        cancel_device_auth(ctx)
        await ctx.status_checker.stop()
        await ctx.scheduler.stop()
        await ctx.trakt.aclose()
        await ctx.jellyseerr.aclose()
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
    app.include_router(ctx.webhooks.router)
    _mount_frontend(app)

    return app
