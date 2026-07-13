"""Bandwidth-Controllarr module: prioritise qBittorrent over SABnzbd.

When enabled, the control loop checks qBittorrent on a short interval. While
qBittorrent has active torrents, SABnzbd is paused; once the torrents finish,
SABnzbd is resumed. The module exposes live status and settings callables on
``AppContext`` so the core router can serve them without importing the module.

APScheduler 4 requires top-level importable job callables, so the scheduled job
is the module-level ``control_job()`` which resolves the active context from the
single module-level reference set in ``setup()``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import FastAPI

from core.app_metrics import observe_scheduler_job
from core.bandwidth_types import BandwidthClientName
from core.logging import get_logger
from modules.bandwidth_controllarr.control import (
    apply_control,
    apply_sab_limit_settings,
    gather_status,
    set_client_paused,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("bandwidth_controllarr")

# The active context, set during setup() so the top-level scheduled job can reach
# the shared clients/db without the scheduler needing to reference a closure.
_CONTEXT: AppContext | None = None


@dataclass
class _ControlState:
    """Live, in-memory state written by the control job and read by the API."""

    enabled: bool = False
    status: str = "Monitoring only"
    last_run_at: str | None = None
    sab_paused: bool = False
    manual_paused_clients: set[BandwidthClientName] = field(default_factory=set)
    _control_lock: asyncio.Lock | None = field(default=None, repr=False)

    def control_lock(self) -> asyncio.Lock:
        """Return the control lock, creating it inside the active event loop."""
        if self._control_lock is None:
            self._control_lock = asyncio.Lock()
        return self._control_lock


_STATE = _ControlState()


def register_context(ctx: AppContext) -> None:
    """Store the active context for the scheduled job to use."""
    global _CONTEXT
    _CONTEXT = ctx


def _require_context() -> AppContext:
    if _CONTEXT is None:  # pragma: no cover
        raise RuntimeError("bandwidth_controllarr context not initialised")
    return _CONTEXT


async def control_job() -> None:
    """Scheduled entrypoint for the Bandwidth-Controllarr loop."""
    ctx = _require_context()
    await observe_scheduler_job("bandwidth_control", lambda: apply_control(ctx))


async def setup(scheduler: SchedulerService, app: FastAPI, ctx: AppContext) -> None:
    """Register the control job and the status/settings callables."""
    register_context(ctx)

    _STATE.enabled = ctx.settings_store.bandwidth_control_enabled()
    _STATE.manual_paused_clients.clear()
    _STATE._control_lock = None

    await scheduler.add_interval(
        control_job,
        seconds=ctx.settings_store.bandwidth_check_interval_seconds(),
        id="bandwidth_control",
    )

    ctx.bandwidth_status = lambda: gather_status(ctx)
    ctx.bandwidth_update_settings = _make_update_settings(scheduler, ctx)
    ctx.bandwidth_update_client = lambda **kwargs: set_client_paused(ctx, **kwargs)

    _log.info("bandwidth_controllarr module ready")


def _make_update_settings(
    scheduler: SchedulerService, ctx: AppContext
) -> Callable[..., Awaitable[dict]]:
    """Build the closure used by the settings endpoint.

    Applying an interval change also reschedules the control loop so the new
    interval takes effect immediately.
    """

    async def update_settings(
        *,
        enabled: bool | None = None,
        check_interval_seconds: int | None = None,
        sab_limit_enabled: bool | None = None,
        sab_limit_mbps: float | None = None,
    ) -> dict:
        if enabled is not None:
            _STATE.enabled = ctx.settings_store.update_bandwidth_control_enabled(
                enabled
            )
            # Run the control decision immediately so disabling restores SABnzbd
            # without waiting for the next scheduled tick.
            await apply_control(ctx)
        if check_interval_seconds is not None:
            seconds = ctx.settings_store.update_bandwidth_check_interval(
                check_interval_seconds
            )
            await scheduler.reschedule_interval(
                control_job, seconds=seconds, id="bandwidth_control"
            )
        if sab_limit_enabled is not None or sab_limit_mbps is not None:
            # Persist and push the limiter change immediately rather than
            # waiting for the next scheduled tick to notice the drift.
            await apply_sab_limit_settings(
                ctx, enabled=sab_limit_enabled, mbps=sab_limit_mbps
            )
        return await gather_status(ctx)

    return update_settings
