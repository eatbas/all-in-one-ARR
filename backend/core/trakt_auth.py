"""UI-driven Trakt device-authorisation coordinator.

The dashboard starts the Trakt device-code flow with a single click and polls its
status until the token is saved. This module wraps the lower-level
:class:`~core.clients.trakt.TraktClient` device primitives in a small, in-process
session object (one Uvicorn worker by design) and a background polling task.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("trakt_auth")

# Authorisation session states surfaced to the dashboard.
IDLE = "idle"
PENDING = "pending"
CONNECTED = "connected"
FAILED = "failed"


@dataclass
class TraktAuthSession:
    """Mutable state for the in-flight (or last) device-auth attempt."""

    state: str = IDLE
    user_code: str | None = None
    verification_url: str | None = None
    message: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def is_pending(self) -> bool:
        """Whether an authorisation attempt is currently in progress."""
        return self.state == PENDING


async def start_device_auth(ctx: AppContext) -> TraktAuthSession:
    """Begin device authorisation and spawn the background polling task.

    If an attempt is already pending the existing session is returned unchanged,
    so repeated clicks do not start competing polls.
    """
    session = ctx.trakt_auth
    if session.is_pending:
        return session

    device = await ctx.trakt.request_device_code()
    session.state = PENDING
    session.user_code = device.get("user_code")
    session.verification_url = device.get("verification_url")
    session.message = "Waiting for you to authorise at Trakt"
    session.task = asyncio.create_task(_poll_device_auth(ctx, device))
    return session


async def _poll_device_auth(ctx: AppContext, device: dict[str, Any]) -> None:
    """Poll Trakt until the device code is authorised, denied, or expires."""
    session = ctx.trakt_auth
    try:
        authorised = await ctx.trakt.poll_for_token(device)
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        raise
    except Exception as exc:  # never let the background task die silently
        session.state = FAILED
        session.message = f"Authorisation error: {exc}"
        _log.exception("Trakt device authorisation failed: %s", exc)
        return

    if authorised:
        session.state = CONNECTED
        session.message = "Connected"
    else:
        session.state = FAILED
        session.message = "Authorisation did not complete"


def cancel_device_auth(ctx: AppContext) -> None:
    """Cancel any in-flight polling task (called on application shutdown)."""
    task = ctx.trakt_auth.task
    if task is not None and not task.done():
        task.cancel()
