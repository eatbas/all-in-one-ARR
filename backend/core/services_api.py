"""Dashboard JSON API for the URL/API-key services (Jellyseerr, Sonarr, Radarr).

Backs the per-service Settings tabs: view the saved URL + whether a key is set,
update the URL/key, and run a Test connection. Kept separate from the core
dashboard (`core.api`) and the Trakt router (`core.trakt_api`) so each stays
focused. Trakt has its own richer router; these three share one shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.logging import get_logger
from core.settings_store import SERVICE_NAMES

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class ServiceConnection(BaseModel):
    url: str
    api_key_set: bool


class UpdateServiceRequest(BaseModel):
    # ``None`` leaves a field unchanged (so the UI can save the URL without
    # re-entering the key).
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
    }[name]


def _services_response(ctx: "AppContext") -> dict[str, ServiceConnection]:
    """Build the masked services response model from the settings store."""
    return {
        name: ServiceConnection(**entry)
        for name, entry in ctx.settings_store.masked_services().items()
    }


def _unknown_service(name: str) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": f"Unknown service: {name}"}
    )


def create_services_router(ctx: "AppContext") -> APIRouter:
    """Build the ``/api`` router for service connection management."""
    router = APIRouter(prefix="/api")
    log = get_logger("services_api")

    @router.get(
        "/settings/services", response_model=dict[str, ServiceConnection]
    )
    async def get_services() -> dict[str, ServiceConnection]:
        return _services_response(ctx)

    @router.put(
        "/settings/services/{name}", response_model=dict[str, ServiceConnection]
    )
    async def put_service(
        name: str, body: UpdateServiceRequest
    ) -> JSONResponse | dict[str, ServiceConnection]:
        if name not in SERVICE_NAMES:
            return _unknown_service(name)
        ctx.settings_store.update_service_connection(
            name, url=body.url, api_key=body.api_key
        )
        url, api_key = ctx.settings_store.service_connection(name)
        _client_for(ctx, name).update_credentials(base_url=url, api_key=api_key)
        log.info("updated %s connection", name)
        return _services_response(ctx)

    @router.post("/services/{name}/test", response_model=ServiceTestResponse)
    async def test_service(name: str) -> JSONResponse | ServiceTestResponse:
        if name not in SERVICE_NAMES:
            return _unknown_service(name)
        result = await _client_for(ctx, name).test_connection()
        return ServiceTestResponse(ok=result["ok"], detail=result["detail"])

    return router
