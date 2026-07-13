"""Bandwidth-Controllarr decision logic and status gathering.

The helpers here are deliberately stateless with respect to the live control
state; the module-level ``_STATE`` instance in ``__init__.py`` is passed in so
APScheduler's required top-level job callable stays decoupled from the state it
mutates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.bandwidth_metrics import update_bandwidth_metrics
from core.bandwidth_types import DOWNLOAD_HISTORY_LIMIT, BandwidthClientName
from core.context import BandwidthClientControlError
from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("bandwidth_controllarr")

_STATUS_DISABLED = "Monitoring only"
_STATUS_ACTIVE = "Active torrents — SABnzbd paused"
_STATUS_IDLE = "No active torrents"
_STATUS_MANUAL = "Manual pause — automatic control suspended"


async def gather_status(ctx: AppContext) -> dict:
    """Return the full status payload exposed by the API.

    Combines real-time client statistics with the live control-state mirror.
    """
    from modules.bandwidth_controllarr import _STATE

    qb_stats, qb_activity = await _status_snapshot(ctx.qbittorrent)
    sab_stats, sab_activity = await _status_snapshot(ctx.sabnzbd)
    download_history = sorted(
        qb_activity["history"] + sab_activity["history"],
        key=_history_sort_key,
        reverse=True,
    )[:DOWNLOAD_HISTORY_LIMIT]
    return {
        "enabled": _STATE.enabled,
        "status": _STATE.status,
        "last_run_at": _STATE.last_run_at,
        "tracking_suspended": bool(_STATE.manual_paused_clients),
        "manual_paused_clients": sorted(_STATE.manual_paused_clients),
        "check_interval_seconds": ctx.settings_store.bandwidth_check_interval_seconds(),
        "sab_limit_enabled": ctx.settings_store.bandwidth_sab_limit_enabled(),
        "sab_limit_mbps": ctx.settings_store.bandwidth_sab_limit_mbps(),
        "qbittorrent": qb_stats,
        "sabnzbd": sab_stats,
        "download_history": download_history,
        "queue": {
            "qbittorrent": {
                "items": qb_activity["queue"],
                "total": qb_activity["queue_total"],
            },
            "sabnzbd": {
                "items": sab_activity["queue"],
                "total": sab_activity["queue_total"],
            },
        },
    }


async def apply_control(ctx: AppContext) -> None:
    """Run one control tick: gather stats, decide, and issue pause/resume."""
    from modules.bandwidth_controllarr import _STATE

    async with _STATE.control_lock():
        await _apply_control_locked(ctx)


async def _apply_control_locked(ctx: AppContext) -> None:
    """Run one control decision while the caller holds the module lock."""
    from modules.bandwidth_controllarr import _STATE

    try:
        enabled = ctx.settings_store.bandwidth_control_enabled()
        qb_stats = await ctx.qbittorrent.get_stats()
        sab_stats = await ctx.sabnzbd.get_stats()

        await _enforce_sab_speed_limit(ctx, sab_stats)

        has_torrents = qb_stats["online"] and qb_stats["active_downloads"] > 0
        sab_paused = (
            bool(sab_stats.get("paused", False)) if sab_stats["online"] else False
        )

        if _STATE.manual_paused_clients:
            status = _STATUS_MANUAL
        elif not enabled:
            status = _STATUS_DISABLED
            if sab_paused and sab_stats["online"]:
                ok = await ctx.sabnzbd.resume()
                if ok:
                    _STATE.sab_paused = False
                    sab_stats["paused"] = False
                    ctx.db.add_activity(
                        "SABnzbd resumed",
                        "Bandwidth-Controllarr resumed SABnzbd (control disabled)",
                    )
        elif has_torrents:
            status = _STATUS_ACTIVE
            if not sab_paused and sab_stats["online"]:
                ok = await ctx.sabnzbd.pause()
                if ok:
                    _STATE.sab_paused = True
                    sab_stats["paused"] = True
                    ctx.db.add_activity(
                        "SABnzbd paused",
                        "Bandwidth-Controllarr paused SABnzbd while qBittorrent is active",
                    )
        else:
            status = _STATUS_IDLE
            if sab_paused and sab_stats["online"]:
                ok = await ctx.sabnzbd.resume()
                if ok:
                    _STATE.sab_paused = False
                    sab_stats["paused"] = False
                    ctx.db.add_activity(
                        "SABnzbd resumed",
                        "Bandwidth-Controllarr resumed SABnzbd (qBittorrent idle)",
                    )

        _STATE.enabled = enabled
        _STATE.status = status
        _STATE.last_run_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        update_bandwidth_metrics(qb_stats, sab_stats, check_ok=True)
    except Exception:
        update_bandwidth_metrics({"online": False}, {"online": False}, check_ok=False)
        raise


async def apply_sab_limit_settings(
    ctx: AppContext, *, enabled: bool | None = None, mbps: float | None = None
) -> None:
    """Persist SABnzbd limiter changes and push the new limit to SABnzbd once.

    A failed client call is logged rather than raised: the persisted setting is
    authoritative and the control tick re-asserts it as soon as SABnzbd is
    reachable again. Clearing only happens on an enabled→disabled transition so
    a limit the user set directly in SABnzbd is never clobbered while the
    limiter stays disabled.
    """
    from modules.bandwidth_controllarr import _STATE

    async with _STATE.control_lock():
        store = ctx.settings_store
        was_enabled = store.bandwidth_sab_limit_enabled()
        if mbps is not None:
            store.update_bandwidth_sab_limit_mbps(mbps)
        if enabled is not None:
            store.update_bandwidth_sab_limit_enabled(enabled)

        if store.bandwidth_sab_limit_enabled():
            limit = store.bandwidth_sab_limit_mbps()
            if await ctx.sabnzbd.set_speed_limit(limit):
                ctx.db.add_activity(
                    "SABnzbd speed limit set",
                    f"Bandwidth-Controllarr limited SABnzbd downloads to {limit} MB/s",
                )
            else:
                _log.warning("could not apply the SABnzbd speed limit")
        elif was_enabled:
            if await ctx.sabnzbd.set_speed_limit(None):
                ctx.db.add_activity(
                    "SABnzbd speed limit removed",
                    "Bandwidth-Controllarr removed the SABnzbd download limit",
                )
            else:
                _log.warning("could not clear the SABnzbd speed limit")


async def _enforce_sab_speed_limit(ctx: AppContext, sab_stats: dict[str, Any]) -> None:
    """Re-assert the configured SABnzbd speed limit when it has drifted.

    SABnzbd can lose or change the limit outside this app (a restart, or a
    manual change in its own interface); while the limiter is enabled the
    configured cap is the source of truth, so drift is corrected on the next
    tick. A disabled limiter never touches SABnzbd.
    """
    if not ctx.settings_store.bandwidth_sab_limit_enabled():
        return
    if not sab_stats["online"]:
        return
    desired = ctx.settings_store.bandwidth_sab_limit_mbps()
    if not _sab_limit_drifted(sab_stats.get("speed_limit_mbps"), desired):
        return
    if await ctx.sabnzbd.set_speed_limit(desired):
        ctx.db.add_activity(
            "SABnzbd speed limit re-applied",
            f"Bandwidth-Controllarr restored the {desired} MB/s SABnzbd download limit",
        )


def _sab_limit_drifted(observed: float | None, desired: float) -> bool:
    """Whether the observed SABnzbd limit differs enough to re-apply.

    The tolerance absorbs the MB/s → integer-KB/s rounding of the config call;
    an unknown observed limit always counts as drift so the (idempotent)
    re-apply errs towards enforcement.
    """
    if observed is None:
        return True
    return abs(observed - desired) > max(0.01, desired * 0.01)


async def set_client_paused(
    ctx: AppContext, *, client: BandwidthClientName, paused: bool
) -> dict:
    """Apply an idempotent manual client command and return live status."""
    from modules.bandwidth_controllarr import _STATE

    async with _STATE.control_lock():
        already_paused = client in _STATE.manual_paused_clients
        if already_paused == paused:
            return await gather_status(ctx)

        download_client = ctx.qbittorrent if client == "qbittorrent" else ctx.sabnzbd
        command = download_client.pause if paused else download_client.resume
        if not await command():
            action = "pause" if paused else "resume"
            raise BandwidthClientControlError(f"{client} could not {action} downloads")

        if paused:
            _STATE.manual_paused_clients.add(client)
        else:
            _STATE.manual_paused_clients.remove(client)

        action = "paused" if paused else "resumed"
        tracking = (
            "automatic control suspended"
            if _STATE.manual_paused_clients
            else "automatic control resumed"
        )
        ctx.db.add_activity(
            f"{_client_label(client)} {action} manually",
            f"{_client_label(client)} downloads {action}; {tracking}",
        )
        await _apply_control_locked(ctx)
        return await gather_status(ctx)


def _client_label(client: BandwidthClientName) -> str:
    return "qBittorrent" if client == "qbittorrent" else "SABnzbd"


async def _download_activity(client: Any) -> dict[str, Any]:
    """Return optional downloader activity for clients that expose it."""
    get_download_activity = getattr(client, "get_download_activity", None)
    if get_download_activity is None:
        return {"queue": [], "queue_total": 0, "history": []}
    return await get_download_activity()


async def _status_snapshot(
    client: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return downloader stats and activity, preferring a shared fetch path."""
    get_status_snapshot = getattr(client, "get_status_snapshot", None)
    if get_status_snapshot is not None:
        snapshot = await get_status_snapshot()
        return snapshot["stats"], snapshot["activity"]
    return await client.get_stats(), await _download_activity(client)


def _history_sort_key(item: dict[str, Any]) -> str:
    """Sort download history by completion time, then by add time."""
    completed_at = item.get("completed_at")
    if isinstance(completed_at, str):
        return completed_at
    added_at = item.get("added_at")
    return added_at if isinstance(added_at, str) else ""
