"""Dashboard JSON API for the managed connection services.

Backs the per-service Settings tabs: view the saved connection (URLs in clear,
secrets reduced to ``<field>_set`` booleans), update fields, and run a Test
connection. The set of services and the fields each one stores are described once
in :mod:`core.service_registry`; this router stays generic over them. Kept
separate from the core dashboard (`core.api`) and the Trakt router
(`core.trakt_api`) so each stays focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.logging import get_logger
from core.service_registry import BY_NAME, SERVICE_NAMES

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.service_registry import ServiceDescriptor


class UpdateServiceRequest(BaseModel):
    # ``None`` leaves a field unchanged (so the UI can save one field without
    # re-entering the others). Fields not declared by a service are ignored.
    url: str | None = None
    api_key: str | None = None


class ServiceTestResponse(BaseModel):
    ok: bool
    detail: str


def _client_for(ctx: "AppContext", name: str):
    """Return the reconfigurable client backing a service name."""
    return {
        "jellyseerr": ctx.jellyseerr,
        "sonarr": ctx.sonarr,
        "radarr": ctx.radarr,
        "tmdb": ctx.tmdb,
        "omdb": ctx.omdb,
        "sabnzbd": ctx.sabnzbd,
        "qbittorrent": ctx.qbittorrent,
    }[name]


def _apply_credentials(ctx: "AppContext", name: str) -> None:
    """Push the stored connection fields into the live client for ``name``.

    Each client's ``update_credentials`` takes only the keyword arguments for the
    fields its service declares (``url`` is passed as ``base_url``), so this maps
    the descriptor's fields onto that call generically. Every managed service
    carries an ``api_key``; only some also carry a ``url``.
    """
    desc: "ServiceDescriptor" = BY_NAME[name]
    values = ctx.settings_store.service_fields(name)
    kwargs: dict[str, str] = {"api_key": values["api_key"]}
    if "url" in desc.fields:
        kwargs["base_url"] = values["url"]
    _client_for(ctx, name).update_credentials(**kwargs)


def _services_response(ctx: "AppContext") -> dict[str, dict[str, Any]]:
    """Build the masked services response (descriptor-trimmed per service)."""
    return ctx.settings_store.masked_services()


def _unknown_service(name: str) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": f"Unknown service: {name}"}
    )


def create_services_router(ctx: "AppContext") -> APIRouter:
    """Build the ``/api`` router for service connection management."""
    router = APIRouter(prefix="/api")
    log = get_logger("services_api")

    # The masked shape varies per service (e.g. ``{url, api_key_set}`` vs the
    # API-key-only ``{api_key_set}``), so the response model is left untyped and
    # the descriptor-trimmed dict is returned verbatim.
    @router.get("/settings/services", response_model=None)
    async def get_services() -> dict[str, dict[str, Any]]:
        return _services_response(ctx)

    @router.put("/settings/services/{name}", response_model=None)
    async def put_service(
        name: str, body: UpdateServiceRequest
    ) -> JSONResponse | dict[str, dict[str, Any]]:
        if name not in SERVICE_NAMES:
            return _unknown_service(name)
        ctx.settings_store.update_service_fields(
            name, url=body.url, api_key=body.api_key
        )
        _apply_credentials(ctx, name)
        log.info("updated %s connection", name)
        return _services_response(ctx)

    @router.post("/services/{name}/test", response_model=ServiceTestResponse)
    async def test_service(name: str) -> JSONResponse | ServiceTestResponse:
        if name not in SERVICE_NAMES:
            return _unknown_service(name)
        result = await _client_for(ctx, name).test_connection()
        return ServiceTestResponse(ok=result["ok"], detail=result["detail"])

    return router
