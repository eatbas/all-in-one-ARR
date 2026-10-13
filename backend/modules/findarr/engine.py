"""Findarr run engine."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from core.app_metrics import (
    record_findarr_run,
    record_findarr_search,
    update_findarr_capacity,
)
from core.logging import get_logger
from modules.findarr import (
    backoff,
    custom_formats,
    grouping,
    outcomes,
    radarr,
    sonarr,
)
from modules.findarr.client import FindarrArrClient, FindarrClientError
from modules.findarr.models import (
    APP_NAMES,
    MODES,
    FindarrItem,
    ModeResult,
    RunResult,
    SearchUnit,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("findarr")


def _format_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    return _format_iso(datetime.now(UTC))


def _hour_cutoff_iso() -> str:
    return (datetime.now(UTC) - timedelta(hours=1)).isoformat()


def _client_for(ctx: AppContext, app: str) -> FindarrArrClient:
    source = ctx.sonarr if app == "sonarr" else ctx.radarr
    fields = source.connection_fields()
    return FindarrArrClient(
        app=app, base_url=fields["base_url"], api_key=fields["api_key"]
    )


def _settings_for(ctx: AppContext) -> dict:
    return ctx.settings_store.findarr_settings()


def _retry_base_hours(settings: dict) -> int:
    """Return the base retry delay (the ``state_reset_hours`` setting)."""
    return int(settings["state_reset_hours"])


async def status(ctx: AppContext) -> dict:
    """Return Findarr's cached status snapshot."""
    settings = _settings_for(ctx)
    hourly_cap = int(settings["hourly_cap"])
    used = ctx.db.findarr_search_count_since(_hour_cutoff_iso())
    remaining = max(0, hourly_cap - used)
    update_findarr_capacity(remaining)
    run_state = ctx.db.findarr_run_state()
    now_iso = datetime.now(UTC).isoformat()
    cooldown = ctx.db.findarr_cooldown_counts(now_iso)
    totals = ctx.db.findarr_totals()
    base_hours = _retry_base_hours(settings)
    return {
        "settings": settings,
        "running": ctx.findarr_gate.is_running(),
        "last_run_at": run_state.get("last_run_at"),
        "last_run_status": run_state.get("last_run_status"),
        "last_run_detail": run_state.get("last_run_detail"),
        "retry": {
            "base_hours": base_hours,
            "max_hours": backoff.max_delay_hours(base_hours),
            "next_due_at": ctx.db.findarr_next_due_at(now_iso),
        },
        "apps": {
            app: {
                "detail": run_state.get(f"{app}_detail", "Not checked yet"),
                "version": run_state.get(f"{app}_version"),
                "compatible": run_state.get(f"{app}_compatible") == "true",
                # ``cooldown`` counts wanted units waiting for their retry delay;
                # ``lifetime`` is the reset-proof all-time tally that drives the
                # headline so it never collapses to 0 once everything is waiting.
                "cooldown": cooldown[app],
                "lifetime": totals[app],
                "wanted": {
                    mode: int(run_state.get(f"{app}_{mode}_wanted", 0))
                    for mode in MODES
                },
                "activity": run_state.get(f"{app}_activity", "Not run yet"),
            }
            for app in APP_NAMES
        },
        "hourly": {
            "limit": hourly_cap,
            "used": used,
            "remaining": remaining,
        },
    }


async def history(ctx: AppContext) -> list[dict]:
    """Return recent Findarr history rows."""
    return ctx.db.findarr_recent_history()


async def reset_state(ctx: AppContext) -> dict:
    """Clear every unit's retry delay and backoff, and append an audit entry."""
    removed = ctx.db.findarr_reset_state()
    ctx.db.findarr_add_history(
        app="sonarr",
        mode="system",
        item_id=None,
        title=None,
        status="success",
        detail=f"Findarr retry state reset ({removed} rows removed)",
    )
    ctx.db.add_activity("Findarr state reset", f"Removed {removed} retry entries")
    return {"status": "reset", "removed": removed}


async def clear_history(ctx: AppContext) -> dict:
    """Empty the Findarr history log and record an audit entry of the clearance.

    Removes only the history rows (the audit log surfaced on the History tab);
    retry state is :func:`reset_state`'s job, and the search log behind the
    hourly cap is never cleared here, so a clear cannot lift the cap. The single
    audit row appended afterwards documents the clearance itself.
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


async def run(ctx: AppContext, *, app: str | None = None, manual: bool = False) -> dict:
    """Run Findarr for all apps or one requested app."""
    settings = _settings_for(ctx)
    metric_app = app or "all"
    if app is not None and app not in APP_NAMES:
        record_findarr_run(app=metric_app, status="error")
        return RunResult(status="error", detail=f"Unknown Findarr app: {app}").to_dict()
    if not settings["enabled"]:
        result = RunResult(status="skipped", detail="Findarr is disabled")
        _record_run_state(ctx, result)
        record_findarr_run(app=metric_app, status=result.status)
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
    record_findarr_run(app=metric_app, status=result.status)
    if manual:
        ctx.db.add_activity("Findarr run completed", result.detail)
    return result.to_dict()


def _record_run_state(ctx: AppContext, result: RunResult) -> None:
    ctx.db.findarr_set_run_state("last_run_at", _now_iso())
    ctx.db.findarr_set_run_state("last_run_status", result.status)
    ctx.db.findarr_set_run_state("last_run_detail", result.detail)


def _record_app_problem(
    ctx: AppContext,
    app: str,
    detail: str,
    *,
    status: str = "error",
    activity: str | None = None,
) -> None:
    """Record why an app was skipped this run: detail, activity, and history."""
    ctx.db.findarr_set_run_state(f"{app}_detail", detail)
    ctx.db.findarr_set_run_state(f"{app}_activity", activity or detail)
    ctx.db.findarr_add_history(
        app=app,
        mode="system",
        item_id=None,
        title=None,
        status=status,
        detail=detail,
    )


async def _check_compatibility(
    ctx: AppContext, client: FindarrArrClient, app: str
) -> bool:
    """Record the app's version/compatibility; return whether the run may go on."""
    try:
        compatibility = await client.compatibility()
    except FindarrClientError as exc:
        detail = str(exc)
        ctx.db.findarr_set_run_state(f"{app}_compatible", "false")
        _record_app_problem(ctx, app, detail, activity=f"Connection error — {detail}")
        return False
    ctx.db.findarr_set_run_state(f"{app}_detail", compatibility.detail)
    ctx.db.findarr_set_run_state(f"{app}_version", compatibility.version)
    ctx.db.findarr_set_run_state(
        f"{app}_compatible", "true" if compatibility.ok else "false"
    )
    if not compatibility.ok:
        _record_app_problem(ctx, app, compatibility.detail)
    return compatibility.ok


async def _queue_blocks_run(
    ctx: AppContext, client: FindarrArrClient, app: str, settings: dict
) -> bool:
    """Whether the Arr download queue is at or above Findarr's queue limit."""
    queue_limit = int(settings["queue_limit"])
    if queue_limit < 0:
        return False
    queue_size = await client.queue_size()
    if queue_size < queue_limit:
        return False
    detail = (
        f"{app.capitalize()} queue size {queue_size} is at or above "
        f"Findarr limit {queue_limit}"
    )
    _record_app_problem(ctx, app, detail, status="skipped")
    return True


def _remaining_capacity(ctx: AppContext, settings: dict) -> int:
    """Return how many more searches the hourly cap allows right now."""
    used = ctx.db.findarr_search_count_since(_hour_cutoff_iso())
    remaining = max(0, int(settings["hourly_cap"]) - used)
    update_findarr_capacity(remaining)
    return remaining


async def _run_app(
    ctx: AppContext, app: str, settings: dict, app_settings: dict
) -> tuple[int, list[ModeResult]]:
    client = _client_for(ctx, app)
    try:
        if not await _check_compatibility(ctx, client, app):
            return 0, []
        try:
            base_hours = _retry_base_hours(settings)
            await outcomes.resolve_pending(ctx, client, app, base_hours=base_hours)
            if await _queue_blocks_run(ctx, client, app, settings):
                return 0, []
            results: list[ModeResult] = []
            for mode in MODES:
                limit = min(
                    int(app_settings[f"{mode}_limit"]),
                    _remaining_capacity(ctx, settings),
                )
                results.append(
                    await _run_mode(
                        ctx,
                        client,
                        app,
                        mode,
                        limit=limit,
                        app_settings=app_settings,
                        sleep_seconds=int(settings["command_sleep_seconds"]),
                        base_hours=base_hours,
                    )
                )
        except FindarrClientError as exc:
            # A wanted-list or queue fetch can fail after the compatibility check
            # passed (e.g. the Arr drops mid-run). Record it like any other
            # connection problem and skip this app rather than aborting the whole
            # run for every app.
            detail = str(exc)
            _record_app_problem(
                ctx, app, detail, activity=f"Connection error — {detail}"
            )
            return 0, []
        for mode_result in results:
            ctx.db.findarr_set_run_state(
                f"{app}_{mode_result.mode}_wanted", str(mode_result.scanned)
            )
        ctx.db.findarr_set_run_state(f"{app}_activity", _app_activity(results))
        return sum(result.processed for result in results), results
    finally:
        await client.aclose()


def _app_activity(results: list[ModeResult]) -> str:
    """Summarise what the last run did for an app, so an idle 0 is explained.

    Distinguishes the legitimate ways a run ends — searched, throttled, search
    errors, caught up because items were skipped by the monitored-only/skip-future
    preferences, caught up because every item is waiting for its retry delay, and
    nothing wanted — from a connection or compatibility failure (handled by the
    caller's earlier exits).
    """
    scanned = sum(result.scanned for result in results)
    selected = sum(result.selected for result in results)
    processed = sum(result.processed for result in results)
    filtered = sum(result.filtered for result in results)
    if processed:
        return f"Searched {processed} item(s) on the last run"
    if any(result.detail == "No remaining Findarr capacity" for result in results):
        return "Throttled — hourly cap reached"
    if selected:
        return "Search errors on the last run — see history"
    if filtered:
        return f"Caught up — {filtered} wanted item(s) skipped by your monitored-only/skip-future settings"
    if scanned:
        return "Caught up — every wanted item is waiting for its retry delay"
    return "Nothing wanted — all caught up"


def _granularity_for(app: str, mode: str, app_settings: dict) -> str:
    """Return the search granularity for an app/mode (Radarr is always movies)."""
    if app != "sonarr":
        return "movies"
    return app_settings.get(f"{mode}_mode", "episodes")


async def _wanted_records(
    client: FindarrArrClient, app: str, mode: str, *, monitored_only: bool
) -> list[dict]:
    """Fetch the raw records a mode searches.

    ``missing`` is the Arr's missing list. ``upgrade`` is the cutoff-unmet list
    plus files below their profile's custom-format cutoff score, which the Arr's
    quality-only cutoff list never includes.
    """
    if mode == "missing":
        return await client.wanted("missing")
    cutoff_unmet = await client.wanted("cutoff")
    below_format_cutoff = await custom_formats.records(
        client, app, monitored_only=monitored_only
    )
    return cutoff_unmet + below_format_cutoff


def _select_units(
    units: list[SearchUnit],
    retry_state: dict[str, dict],
    *,
    monitored_only: bool,
    skip_future: bool,
    limit: int,
) -> list[SearchUnit]:
    """Pick up to ``limit`` due units, never-searched ones first.

    Wanted-list order is kept within each group, so the choice is
    deterministic; units still inside their retry delay are left out.
    """
    now = datetime.now(UTC)
    due = [
        unit
        for unit in units
        if _unit_due(
            unit,
            retry_state,
            now=now,
            monitored_only=monitored_only,
            skip_future=skip_future,
        )
    ]
    due.sort(key=lambda unit: unit.key in retry_state)
    return due[:limit]


async def _send_search(
    ctx: AppContext,
    client: FindarrArrClient,
    unit: SearchUnit,
    *,
    retry_state: dict[str, dict],
    base_hours: int,
) -> bool:
    """Send one search command and record it; return whether the Arr accepted it."""
    app, mode = unit.app, unit.mode
    try:
        command_id = await client.trigger_search(unit)
    except FindarrClientError as exc:
        ctx.db.findarr_add_history(
            app=app,
            mode=mode,
            item_id=unit.key,
            title=unit.title,
            status="error",
            detail=str(exc),
        )
        record_findarr_search(app=app, mode=mode, status="error")
        _log.warning("Findarr search failed for %s %s: %s", app, unit.key, exc)
        return False
    attempts = int(retry_state.get(unit.key, {}).get("attempts", 0))
    ctx.db.findarr_mark_searched(
        app=app,
        mode=mode,
        item_id=unit.key,
        title=unit.title,
        next_eligible_at=backoff.next_eligible_at(
            datetime.now(UTC), attempts, base_hours
        ),
    )
    ctx.db.findarr_increment_total(app=app, mode=mode)
    history_id = ctx.db.findarr_add_history(
        app=app,
        mode=mode,
        item_id=unit.key,
        title=unit.title,
        status="sent",
        detail=f"{mode.capitalize()} search sent to {app.capitalize()}; result pending",
    )
    ctx.db.findarr_log_search(
        app=app,
        mode=mode,
        item_id=unit.key,
        command_id=command_id,
        history_id=history_id,
    )
    record_findarr_search(app=app, mode=mode, status="success")
    return True


async def _run_mode(
    ctx: AppContext,
    client: FindarrArrClient,
    app: str,
    mode: str,
    *,
    limit: int,
    app_settings: dict,
    sleep_seconds: int,
    base_hours: int,
) -> ModeResult:
    result = ModeResult(app=app, mode=mode)
    if limit <= 0:
        result.detail = "No remaining Findarr capacity"
        return result

    monitored_only = app_settings["monitored_only"]
    skip_future = app_settings["skip_future"]
    records = await _wanted_records(client, app, mode, monitored_only=monitored_only)
    items = _normalise_items(app, mode, records)
    granularity = _granularity_for(app, mode, app_settings)
    units = grouping.build_units(app, mode, items, granularity)
    ctx.db.findarr_prune_processed(
        app=app, mode=mode, keep_item_ids=[unit.key for unit in units]
    )
    retry_state = ctx.db.findarr_retry_state(app=app, mode=mode)
    result.scanned = len(units)
    result.filtered = sum(
        1
        for unit in units
        if _filtered_by_preference(
            unit, monitored_only=monitored_only, skip_future=skip_future
        )
    )
    selected = _select_units(
        units,
        retry_state,
        monitored_only=monitored_only,
        skip_future=skip_future,
        limit=limit,
    )
    result.selected = len(selected)
    result.skipped = len(units) - len(selected)

    for index, unit in enumerate(selected):
        if index and sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)
        if await _send_search(
            ctx, client, unit, retry_state=retry_state, base_hours=base_hours
        ):
            result.processed += 1
    result.detail = (
        f"Processed {result.processed} of {result.selected} selected item(s)"
    )
    return result


def _normalise_items(app: str, mode: str, records: list[dict]) -> list[FindarrItem]:
    """Normalise wanted records, keeping the first record for each item id.

    The upgrade mode merges two sources (cutoff-unmet and below the custom-format
    cutoff) that can both list the same episode or movie.
    """
    normaliser = sonarr.normalise if app == "sonarr" else radarr.normalise
    items: list[FindarrItem] = []
    seen: set[str] = set()
    for record in records:
        item = normaliser(record, mode=mode)
        if item is not None and item.item_id not in seen:
            seen.add(item.item_id)
            items.append(item)
    return items


def _filtered_by_preference(
    unit: SearchUnit, *, monitored_only: bool, skip_future: bool
) -> bool:
    """Whether a unit is excluded by the monitored-only / skip-future preferences."""
    if monitored_only and not unit.monitored:
        return True
    if skip_future and unit.is_future:
        return True
    return False


def _unit_due(
    unit: SearchUnit,
    retry_state: dict[str, dict],
    *,
    now: datetime,
    monitored_only: bool,
    skip_future: bool,
) -> bool:
    """Whether a unit passes the preferences and is past its retry delay."""
    if _filtered_by_preference(
        unit, monitored_only=monitored_only, skip_future=skip_future
    ):
        return False
    entry = retry_state.get(unit.key)
    return entry is None or backoff.is_due(entry["next_eligible_at"], now)
