"""Findarr run engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from core.logging import get_logger
from modules.findarr.client import FindarrArrClient, FindarrClientError
from modules.findarr.models import APP_NAMES, FindarrItem, ModeResult, RunResult, SearchUnit
from modules.findarr import grouping, radarr, sonarr

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("findarr")

# Run-state key marking when the current processed-state window began.
_STATE_ANCHOR_KEY = "state_created_at"


def _format_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    return _format_iso(datetime.now(timezone.utc))


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - defensive against a corrupt anchor
        return None
    if parsed.tzinfo is None:  # pragma: no cover - anchors are always tz-aware
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
        "state": _state_snapshot(run_state, settings),
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
    """Clear processed state, restart the reset window, and append an audit entry."""
    removed = ctx.db.findarr_reset_state()
    ctx.db.findarr_set_run_state(_STATE_ANCHOR_KEY, _now_iso())
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


async def clear_history(ctx: "AppContext") -> dict:
    """Empty the Findarr history log and record an audit entry of the clearance.

    Removes only the history rows (the audit log surfaced on the History tab);
    processed-media bookkeeping is left intact — that is :func:`reset_state`'s
    job. The single audit row appended afterwards documents the clearance itself.
    """
    removed = ctx.db.findarr_clear_history()
    ctx.db.findarr_add_history(
        app="sonarr",
        mode="system",
        item_id=None,
        title=None,
        status="success",
        detail=f"Findarr history cleared ({removed} rows removed)",
    )
    ctx.db.add_activity("Findarr history cleared", f"Removed {removed} history entries")
    return {"status": "cleared", "removed": removed}


def _state_snapshot(run_state: dict, settings: dict) -> dict:
    """Describe the stateful-management window for the status response."""
    reset_hours = int(settings["state_reset_hours"])
    created_raw = run_state.get(_STATE_ANCHOR_KEY)
    created = _parse_iso(created_raw) if created_raw else None
    reset_at = _format_iso(created + timedelta(hours=reset_hours)) if created else None
    return {"created_at": created_raw, "reset_at": reset_at, "reset_hours": reset_hours}


def _maybe_reset_state(ctx: "AppContext", settings: dict) -> None:
    """Seed the reset anchor, or clear processed state once the window elapses.

    Mirrors Huntarr's stateful management: processed-media ids are wiped after
    ``state_reset_hours`` so previously handled items become eligible again
    ("re-look where we left off and renew"). Media and Arr libraries are never
    touched — only Findarr's own processed bookkeeping.
    """
    run_state = ctx.db.findarr_run_state()
    created_raw = run_state.get(_STATE_ANCHOR_KEY)
    created = _parse_iso(created_raw) if created_raw else None
    if created is None:
        ctx.db.findarr_set_run_state(_STATE_ANCHOR_KEY, _now_iso())
        return
    reset_hours = int(settings["state_reset_hours"])
    if datetime.now(timezone.utc) < created + timedelta(hours=reset_hours):
        return
    removed = ctx.db.findarr_reset_state()
    ctx.db.findarr_set_run_state(_STATE_ANCHOR_KEY, _now_iso())
    detail = f"Findarr state auto-reset after {reset_hours}h ({removed} rows removed)"
    ctx.db.findarr_add_history(
        app="sonarr", mode="system", item_id=None, title=None, status="success", detail=detail
    )
    ctx.db.add_activity("Findarr state auto-reset", f"Removed {removed} processed entries after {reset_hours}h")


async def run(ctx: "AppContext", *, app: str | None = None, manual: bool = False) -> dict:
    """Run Findarr for all apps or one requested app."""
    settings = _settings_for(ctx)
    if app is not None and app not in APP_NAMES:
        return RunResult(status="error", detail=f"Unknown Findarr app: {app}").to_dict()
    if not settings["enabled"]:
        result = RunResult(status="skipped", detail="Findarr is disabled")
        _record_run_state(ctx, result)
        return result.to_dict()

    _maybe_reset_state(ctx, settings)

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

        sleep_seconds = int(settings["command_sleep_seconds"])
        processed = 0
        results: list[ModeResult] = []
        for mode, wanted_kind, limit_key in (
            ("missing", "missing", "missing_limit"),
            ("upgrade", "cutoff", "upgrade_limit"),
        ):
            remaining = max(0, int(settings["hourly_cap"]) - ctx.db.findarr_success_count_since(_hour_cutoff_iso()))
            limit = min(int(app_settings[limit_key]), remaining)
            mode_result = await _run_mode(
                ctx, client, app, mode, wanted_kind, limit, app_settings, sleep_seconds
            )
            processed += mode_result.processed
            results.append(mode_result)
        return processed, results
    finally:
        await client.aclose()


def _granularity_for(app: str, mode: str, app_settings: dict) -> str:
    """Return the search granularity for an app/mode (Radarr is always movies)."""
    if app != "sonarr":
        return "movies"
    return app_settings.get(f"{mode}_mode", "episodes")


async def _run_mode(
    ctx: "AppContext",
    client: FindarrArrClient,
    app: str,
    mode: str,
    wanted_kind: str,
    limit: int,
    app_settings: dict,
    sleep_seconds: int,
) -> ModeResult:
    result = ModeResult(app=app, mode=mode)
    if limit <= 0:
        result.detail = "No remaining Findarr capacity"
        return result

    records = await client.wanted(wanted_kind)
    items = _normalise_items(app, mode, records)
    granularity = _granularity_for(app, mode, app_settings)
    units = grouping.build_units(app, mode, items, granularity)
    result.scanned = len(units)
    candidates = [
        unit
        for unit in units
        if _unit_allowed(ctx, unit, monitored_only=app_settings["monitored_only"], skip_future=app_settings["skip_future"])
    ]
    selected = candidates[:limit]
    result.selected = len(selected)
    result.skipped = len(units) - len(selected)

    for index, unit in enumerate(selected):
        if index and sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)
        try:
            await client.trigger_search(unit)
        except FindarrClientError as exc:
            ctx.db.findarr_add_history(
                app=app,
                mode=mode,
                item_id=unit.key,
                title=unit.title,
                status="error",
                detail=str(exc),
            )
            _log.warning("Findarr search failed for %s %s: %s", app, unit.key, exc)
            continue
        ctx.db.findarr_mark_processed(app=app, mode=mode, item_id=unit.key, title=unit.title)
        ctx.db.findarr_add_history(
            app=app,
            mode=mode,
            item_id=unit.key,
            title=unit.title,
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


def _unit_allowed(ctx: "AppContext", unit: SearchUnit, *, monitored_only: bool, skip_future: bool) -> bool:
    if monitored_only and not unit.monitored:
        return False
    if skip_future and unit.is_future:
        return False
    return not ctx.db.findarr_is_processed(app=unit.app, mode=unit.mode, item_id=unit.key)
