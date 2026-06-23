"""Background health checks for all configured integrations.

The :class:`StatusChecker` polls every managed service on the interval configured
in :class:`core.settings_store.SettingsStore` and keeps a cached snapshot that the
dashboard can read cheaply via ``GET /api/status/services``.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


@dataclass
class StatusSnapshot:
    """A single point-in-time health snapshot for one integration."""

    ok: bool
    detail: str
    checked_at: str


@dataclass
class StatusResult:
    """The full status payload exposed to the frontend."""

    interval_seconds: int
    last_check_at: str | None
    services: dict[str, StatusSnapshot] = field(default_factory=dict)


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class StatusChecker:
    """Periodically ping every configured service and cache the results."""

    def __init__(self, ctx: "AppContext") -> None:
        self._ctx = ctx
        self._log = get_logger("status_checker")
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._results: dict[str, StatusSnapshot] = {}
        self._last_check_at: str | None = None

    async def start(self) -> None:
        """Start the background check loop."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        self._log.info("status checker started")

    async def stop(self) -> None:
        """Stop the background check loop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._log.info("status checker stopped")

    async def check_now(self) -> StatusResult:
        """Run one immediate check and return the fresh snapshot."""
        await self._check_once()
        return self.get_statuses()

    def get_statuses(self) -> StatusResult:
        """Return the most recent status snapshot without triggering a check."""
        return StatusResult(
            interval_seconds=self._ctx.settings_store.status_check_interval_seconds(),
            last_check_at=self._last_check_at,
            services=dict(self._results),
        )

    async def _loop(self) -> None:
        """Run checks forever until :meth:`stop` is called."""
        while not self._stop_event.is_set():
            await self._check_once()
            interval = self._ctx.settings_store.status_check_interval_seconds()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)

    async def _check_once(self) -> None:
        """Ping every configured service once and cache the results."""
        self._log.debug("running status checks")
        checked_at = _now_iso()
        coroutines = [
            self._check_one(name, client)
            for name, client in self._service_clients().items()
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        new_results: dict[str, StatusSnapshot] = {}
        for name, outcome in zip(self._service_clients().keys(), results):
            if isinstance(outcome, BaseException):
                snapshot = StatusSnapshot(
                    ok=False,
                    detail=f"Unexpected error: {outcome}",
                    checked_at=checked_at,
                )
            else:
                snapshot = outcome
            new_results[name] = snapshot

        self._results = new_results
        self._last_check_at = checked_at
        self._log.debug("status checks complete: %d services", len(new_results))

    async def _check_one(self, name: str, client: Any) -> StatusSnapshot:
        """Ping a single service and normalise the result."""
        checked_at = _now_iso()
        try:
            result = await client.test_connection()
        except Exception as exc:  # noqa: BLE001 - clients may raise unexpectedly
            self._log.warning("%s status check raised: %s", name, exc)
            return StatusSnapshot(
                ok=False,
                detail=f"Health check failed: {exc}",
                checked_at=checked_at,
            )

        if isinstance(result, dict) and "ok" in result:
            return StatusSnapshot(
                ok=bool(result["ok"]),
                detail=str(result.get("detail", "")),
                checked_at=checked_at,
            )

        # Fallback for any client that returns an unstructured success payload.
        return StatusSnapshot(
            ok=True,
            detail="Connected",
            checked_at=checked_at,
        )

    def _service_clients(self) -> dict[str, Any]:
        """Map service names to the live client instances on the context."""
        return {
            "trakt": self._ctx.trakt,
            "jellyseerr": self._ctx.jellyseerr,
            "sonarr": self._ctx.sonarr,
            "radarr": self._ctx.radarr,
            "tmdb": self._ctx.tmdb,
            "omdb": self._ctx.omdb,
            "sabnzbd": self._ctx.sabnzbd,
            "qbittorrent": self._ctx.qbittorrent,
        }
