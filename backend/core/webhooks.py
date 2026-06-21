"""Single webhook router shared by all modules.

Modules register a handler for a sub-path (e.g. ``traktsync`` registers
``arr`` to receive ``/webhook/arr``). The router reads the raw body, logs the
full JSON on receipt (field names vary across arr versions), then dispatches to
the registered handler.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Request, Response

from core.logging import get_logger

# A handler receives the parsed payload and returns an optional result dict.
WebhookHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class WebhookRegistry:
    """Holds webhook handlers and exposes a FastAPI router that dispatches."""

    def __init__(self) -> None:
        self._handlers: dict[str, WebhookHandler] = {}
        self._log = get_logger("webhooks")
        self.router = APIRouter(prefix="/webhook")
        self.router.add_api_route(
            "/{subpath}", self._dispatch, methods=["POST"]
        )

    def register(self, subpath: str, handler: WebhookHandler) -> None:
        """Register ``handler`` for ``POST /webhook/{subpath}``."""
        self._handlers[subpath] = handler
        self._log.info("registered webhook handler subpath=%s", subpath)

    async def _dispatch(self, subpath: str, request: Request) -> Response:
        raw = await request.body()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._log.error("webhook %s received invalid JSON", subpath)
            return Response(status_code=400, content="invalid json")

        # Log the full raw payload so unknown shapes can be inspected.
        self._log.info("webhook %s payload=%s", subpath, json.dumps(payload))

        handler = self._handlers.get(subpath)
        if handler is None:
            self._log.warning("no webhook handler registered for subpath=%s", subpath)
            return Response(status_code=404, content="no handler")

        try:
            await handler(payload)
        except Exception as exc:
            # Never surface a 5xx to the arr connection: log and acknowledge so
            # Radarr/Sonarr do not retry or disable the webhook.
            self._log.exception("webhook %s handler failed: %s", subpath, exc)
        return Response(status_code=200, content="ok")
