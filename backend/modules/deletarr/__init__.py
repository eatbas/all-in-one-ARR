"""Deletarr module: scan media libraries for reviewed junk-file deletion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from core.logging import get_logger
from modules.deletarr.engine import DeletarrService

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("deletarr")


async def setup(
    scheduler: "SchedulerService", app: FastAPI, ctx: "AppContext"
) -> None:
    """Register Deletarr API callables on the shared context."""
    del scheduler, app
    service = DeletarrService(ctx)
    ctx.deletarr_status = service.status
    ctx.deletarr_scan = service.scan
    ctx.deletarr_results = service.results
    ctx.deletarr_delete = service.delete
    ctx.deletarr_update_settings = service.update_settings
    _log.info("deletarr module ready")
