"""Bandwidth-Controllarr decision logic and status gathering.

The helpers here are deliberately stateless with respect to the live control
state; the module-level ``_STATE`` instance in ``__init__.py`` is passed in so
APScheduler's required top-level job callable stays decoupled from the state it
mutates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.bandwidth_metrics import update_bandwidth_metrics
from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("bandwidth_controllarr")

_STATUS_DISABLED = "Monitoring only"
_STATUS_ACTIVE = "Active torrents — SABnzbd paused"
_STATUS_IDLE = "No active torrents"


async def gather_status(ctx: AppContext) -> dict:
    """Return the full status payload exposed by the API.

    Combines real-time client statistics with the live control-state mirror.
    """
    from modules.bandwidth_controllarr import _STATE

    qb_stats = await ctx.qbittorrent.get_stats()
    sab_stats = await ctx.sabnzbd.get_stats()
    return {
        "enabled": _STATE.enabled,
        "status": _STATE.status,
        "last_run_at": _STATE.last_run_at,
        "check_interval_seconds": ctx.settings_store.bandwidth_check_interval_seconds(),
        "qbittorrent": qb_stats,
        "sabnzbd": sab_stats,
    }


async def apply_control(ctx: AppContext) -> None:
    """Run one control tick: gather stats, decide, and issue pause/resume."""
    from modules.bandwidth_controllarr import _STATE

    try:
        enabled = ctx.settings_store.bandwidth_control_enabled()
        qb_stats = await ctx.qbittorrent.get_stats()
        sab_stats = await ctx.sabnzbd.get_stats()

        has_torrents = qb_stats["online"] and qb_stats["active_downloads"] > 0
        sab_paused = (
            bool(sab_stats.get("paused", False)) if sab_stats["online"] else False
        )

        if not enabled:
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
