"""Findarr run engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from core.logging import get_logger
from modules.findarr.client import FindarrArrClient, FindarrClientError
from modules.findarr.models import APP_NAMES, MODES, FindarrItem, ModeResult, RunResult
from modules.findarr import radarr, sonarr

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("findarr")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hour_cutoff_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _client_for(ctx: "AppContext", app: str) -> FindarrArrClient:
    source = ctx.sonarr if app == "sonarr" else ctx.radarr
    fields = source.connection_fields()
    return FindarrArrClient(app=app, base_url=fields["base_url"], api_key=fields["api_key"])


def _settings_for(ctx: "AppContext") -> dict:
    return ctx.settings_store.findarr_settings()


async def status(ctx: "AppContext") -> dict:
    """Return Findarr's cached status snapshot."""
    settings = _settings_for(ctx)
    hourly_cap = int(settings["hourly_cap"])
    used = ctx.db.findarr_success_count_since(_hour_cutoff_iso())
    run_state = ctx.db.findarr_run_state()
    return {
        "settings": settings,
        "running": ctx.findarr_gate.is_running(),
        "last_run_at": run_state.get("last_run_at"),
        "last_run_status": run_state.get("last_run_status"),
        "last_run_detail": run_state.get("last_run_detail"),
        "apps": {
            app: {
                "detail": run_state.get(f"{app}_detail", "Not checked yet"),
                "version": run_state.get(f"{app}_version"),
                "compatible": run_state.get(f"{app}_compatible") == "true",
                "processed": ctx.db.findarr_counts()[app],
            }
            for app in APP_NAMES
        },
        "hourly": {
            "limit": hourly_cap,
            "used": used,
            "remaining": max(0, hourly_cap - used),
        },
    }


async def history(ctx: "AppContext") -> list[dict]:
    """Return recent Findarr history rows."""
    return ctx.db.findarr_recent_history()


async def reset_state(ctx: "AppContext") -> dict:
    """Clear processed state and append an audit entry."""
    removed = ctx.db.findarr_reset_state()
    ctx.db.findarr_add_history(
        app="sonarr",
        mode="system",
        item_id=None,
        title=None,
        status="success",
        detail=f"Findarr processed state reset ({removed} rows removed)",
    )
    ctx.db.add_activity("Findarr state reset", f"Removed {removed} processed entries")
    return {"status": "reset", "removed": removed}


async def run(ctx: "AppContext", *, app: str | None = None, manual: bool = False) -> dict:
    """Run Findarr for all apps or one requested app."""
    settings = _settings_for(ctx)
    if app is not None and app not in APP_NAMES:
        return RunResult(status="error", detail=f"Unknown Findarr app: {app}").to_dict()
    if not settings["enabled"]:
        result = RunResult(status="skipped", detail="Findarr is disabled")
        _record_run_state(ctx, result)
        return result.to_dict()

    apps = [app] if app else list(APP_NAMES)
    total_processed = 0
    mode_results: list[ModeResult] = []
    for app_name in apps:
        app_settings = settings["apps"][app_name]
        if not app_settings["enabled"]:
            ctx.db.findarr_set_run_state(f"{app_name}_detail", "Disabled")
            continue
        app_processed, results = await _run_app(ctx, app_name, settings, app_settings)
        total_processed += app_processed
        mode_results.extend(results)

    result = RunResult(
        status="completed",
        detail=f"Processed {total_processed} Findarr item(s)",
        processed=total_processed,
        results=mode_results,
    )
    _record_run_state(ctx, result)
    if manual:
        ctx.db.add_activity("Findarr run completed", result.detail)
    return result.to_dict()


def _record_run_state(ctx: "AppContext", result: RunResult) -> None:
    ctx.db.findarr_set_run_state("last_run_at", _now_iso())
    ctx.db.findarr_set_run_state("last_run_status", result.status)
    ctx.db.findarr_set_run_state("last_run_detail", result.detail)


async def _run_app(ctx: "AppContext", app: str, settings: dict, app_settings: dict) -> tuple[int, list[ModeResult]]:
    client = _client_for(ctx, app)
    try:
        try:
            compatibility = await client.compatibility()
        except FindarrClientError as exc:
            detail = str(exc)
            ctx.db.findarr_set_run_state(f"{app}_detail", detail)
            ctx.db.findarr_set_run_state(f"{app}_compatible", "false")
            ctx.db.findarr_add_history(app=app, mode="system", item_id=None, title=None, status="error", detail=detail)
            return 0, []

        ctx.db.findarr_set_run_state(f"{app}_detail", compatibility.detail)
        ctx.db.findarr_set_run_state(f"{app}_version", compatibility.version)
        ctx.db.findarr_set_run_state(f"{app}_compatible", "true" if compatibility.ok else "false")
        if not compatibility.ok:
            ctx.db.findarr_add_history(
                app=app,
                mode="system",
                item_id=None,
                title=None,
                status="error",
                detail=compatibility.detail,
            )
            return 0, []

        queue_limit = int(settings["queue_limit"])
        if queue_limit >= 0:
            queue_size = await client.queue_size()
            if queue_size >= queue_limit:
                detail = f"{app.capitalize()} queue size {queue_size} is at or above Findarr limit {queue_limit}"
                ctx.db.findarr_set_run_state(f"{app}_detail", detail)
                ctx.db.findarr_add_history(app=app, mode="system", item_id=None, title=None, status="skipped", detail=detail)
                return 0, []

        processed = 0
        results: list[ModeResult] = []
        for mode, wanted_kind, limit_key in (
            ("missing", "missing", "missing_limit"),
            ("upgrade", "cutoff", "upgrade_limit"),
        ):
            remaining = max(0, int(settings["hourly_cap"]) - ctx.db.findarr_success_count_since(_hour_cutoff_iso()))
            limit = min(int(app_settings[limit_key]), remaining)
            mode_result = await _run_mode(ctx, client, app, mode, wanted_kind, limit, app_settings)
            processed += mode_result.processed
            results.append(mode_result)
        return processed, results
    finally:
        await client.aclose()


async def _run_mode(
    ctx: "AppContext",
    client: FindarrArrClient,
    app: str,
    mode: str,
    wanted_kind: str,
    limit: int,
    app_settings: dict,
) -> ModeResult:
    result = ModeResult(app=app, mode=mode)
    if limit <= 0:
        result.detail = "No remaining Findarr capacity"
        return result

    records = await client.wanted(wanted_kind)
    items = _normalise_items(app, mode, records)
    result.scanned = len(items)
    candidates = [
        item
        for item in items
        if _item_allowed(ctx, item, monitored_only=app_settings["monitored_only"], skip_future=app_settings["skip_future"])
    ]
    selected = candidates[:limit]
    result.selected = len(selected)
    result.skipped = len(items) - len(selected)

    for item in selected:
        try:
            await client.trigger_search(item_id=item.item_id)
        except FindarrClientError as exc:
            ctx.db.findarr_add_history(
                app=app,
                mode=mode,
                item_id=item.item_id,
                title=item.title,
                status="error",
                detail=str(exc),
            )
            _log.warning("Findarr search failed for %s %s: %s", app, item.item_id, exc)
            continue
        ctx.db.findarr_mark_processed(app=app, mode=mode, item_id=item.item_id, title=item.title)
        ctx.db.findarr_add_history(
            app=app,
            mode=mode,
            item_id=item.item_id,
            title=item.title,
            status="success",
            detail=f"Triggered {app.capitalize()} {mode} search",
        )
        result.processed += 1
    result.detail = f"Processed {result.processed} of {result.selected} selected item(s)"
    return result


def _normalise_items(app: str, mode: str, records: list[dict]) -> list[FindarrItem]:
    normaliser = sonarr.normalise if app == "sonarr" else radarr.normalise
    items: list[FindarrItem] = []
    for record in records:
        item = normaliser(record, mode=mode)
        if item is not None:
            items.append(item)
    return items


def _item_allowed(ctx: "AppContext", item: FindarrItem, *, monitored_only: bool, skip_future: bool) -> bool:
    if monitored_only and not item.monitored:
        return False
    if skip_future and item.is_future:
        return False
    return not ctx.db.findarr_is_processed(app=item.app, mode=item.mode, item_id=item.item_id)
