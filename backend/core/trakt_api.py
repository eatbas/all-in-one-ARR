"""Dashboard JSON API for managing the Trakt connection and synced lists.

These endpoints back the Settings page: editing the Trakt credentials, running
the device-auth flow, testing the connection, discovering the account's lists,
and adding/removing lists (including by pasting a Trakt list URL). They are kept
separate from the core dashboard endpoints (``core.api``) so each module stays
focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.logging import get_logger
from core.trakt_auth import start_device_auth
from core.trakt_url import TraktUrlError, parse_trakt_list_url

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class TrackedListModel(BaseModel):
    owner_user: str
    slug: str
    name: str


class TraktSettingsResponse(BaseModel):
    client_id_hint: str
    client_id_set: bool
    client_secret_set: bool
    connected: bool
    lists: list[TrackedListModel]


class UpdateTraktSettingsRequest(BaseModel):
    # ``None`` leaves a field unchanged (so the UI can save the client id without
    # re-entering the secret).
    client_id: str | None = None
    client_secret: str | None = None


class TraktAuthStartResponse(BaseModel):
    state: str
    user_code: str | None
    verification_url: str | None
    message: str | None


class TraktAuthStatusResponse(BaseModel):
    state: str
    user_code: str | None
    verification_url: str | None
    message: str | None
    connected: bool


class TraktTestResponse(BaseModel):
    ok: bool
    user: str | None
    message: str


class TraktListEntry(BaseModel):
    name: str | None
    slug: str
    owner_user: str
    item_count: int | None
    selected: bool


class AddListRequest(BaseModel):
    url: str | None = None
    owner_user: str | None = None
    slug: str | None = None


def _settings_response(ctx: "AppContext") -> TraktSettingsResponse:
    """Build the masked Trakt settings view from the store and client."""
    client_id, client_secret = ctx.settings_store.trakt_credentials()
    return TraktSettingsResponse(
        client_id_hint=client_id[-4:] if client_id else "",
        client_id_set=bool(client_id),
        client_secret_set=bool(client_secret),
        connected=ctx.trakt.is_authenticated(),
        lists=[
            TrackedListModel(**item.to_dict())
            for item in ctx.settings_store.tracked_lists()
        ],
    )


def create_trakt_router(ctx: "AppContext") -> APIRouter:
    """Build the ``/api`` router for Trakt connection and list management."""
    router = APIRouter(prefix="/api")
    log = get_logger("trakt_api")

    @router.get("/settings/trakt", response_model=TraktSettingsResponse)
    async def get_trakt_settings() -> TraktSettingsResponse:
        return _settings_response(ctx)

    @router.put("/settings/trakt", response_model=TraktSettingsResponse)
    async def put_trakt_settings(
        body: UpdateTraktSettingsRequest,
    ) -> TraktSettingsResponse:
        ctx.settings_store.update_trakt_credentials(
            client_id=body.client_id,
            client_secret=body.client_secret,
        )
        client_id, client_secret = ctx.settings_store.trakt_credentials()
        ctx.trakt.update_credentials(
            client_id=client_id, client_secret=client_secret
        )
        log.info("Trakt settings updated")
        return _settings_response(ctx)

    @router.post("/trakt/auth/start", response_model=TraktAuthStartResponse)
    async def post_trakt_auth_start() -> JSONResponse | TraktAuthStartResponse:
        client_id, _ = ctx.settings_store.trakt_credentials()
        if not client_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "Set the Trakt client id and secret first"},
            )
        try:
            session = await start_device_auth(ctx)
        except Exception as exc:  # network/Trakt error starting the flow
            return JSONResponse(
                status_code=502,
                content={"detail": f"Could not start authorisation: {exc}"},
            )
        return TraktAuthStartResponse(
            state=session.state,
            user_code=session.user_code,
            verification_url=session.verification_url,
            message=session.message,
        )

    @router.get("/trakt/auth/status", response_model=TraktAuthStatusResponse)
    async def get_trakt_auth_status() -> TraktAuthStatusResponse:
        session = ctx.trakt_auth
        return TraktAuthStatusResponse(
            state=session.state,
            user_code=session.user_code,
            verification_url=session.verification_url,
            message=session.message,
            connected=ctx.trakt.is_authenticated(),
        )

    @router.post("/trakt/test", response_model=TraktTestResponse)
    async def post_trakt_test() -> TraktTestResponse:
        result = await ctx.trakt.test_connection()
        return TraktTestResponse(
            ok=result["ok"],
            user=result.get("username"),
            message=result["detail"],
        )

    @router.get("/trakt/lists", response_model=list[TraktListEntry])
    async def get_trakt_lists() -> JSONResponse | list[TraktListEntry]:
        try:
            discovered = await ctx.trakt.get_user_lists()
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Could not fetch lists: {exc}"},
            )
        selected = {item.key for item in ctx.settings_store.tracked_lists()}
        return [
            TraktListEntry(
                name=entry["name"],
                slug=entry["slug"],
                owner_user=entry["owner_user"],
                item_count=entry["item_count"],
                selected=(entry["owner_user"], entry["slug"]) in selected,
            )
            for entry in discovered
        ]

    @router.post("/trakt/lists", response_model=TraktSettingsResponse)
    async def post_add_trakt_list(
        body: AddListRequest,
    ) -> JSONResponse | TraktSettingsResponse:
        try:
            owner_user, slug = _resolve_list_ref(body)
        except TraktUrlError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        try:
            summary = await ctx.trakt.get_list_summary(
                owner_user=owner_user, slug=slug
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200]
            return JSONResponse(
                status_code=400,
                content={
                    "detail": (
                        f"Could not validate list {owner_user}/{slug}: "
                        f"HTTP {exc.response.status_code} — {body}"
                    )
                },
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Could not validate list {owner_user}/{slug}: {exc}"},
            )
        if summary is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Trakt list not found: {owner_user}/{slug}"},
            )
        ctx.settings_store.add_list(
            owner_user=summary["owner_user"],
            slug=summary["slug"],
            name=summary["name"] or summary["slug"],
        )
        log.info("added Trakt list %s/%s", summary["owner_user"], summary["slug"])
        return _settings_response(ctx)

    @router.delete(
        "/trakt/lists/{owner_user}/{slug}", response_model=TraktSettingsResponse
    )
    async def delete_trakt_list(owner_user: str, slug: str) -> TraktSettingsResponse:
        ctx.settings_store.remove_list(owner_user=owner_user, slug=slug)
        log.info("removed Trakt list %s/%s", owner_user, slug)
        return _settings_response(ctx)

    return router


def _resolve_list_ref(body: AddListRequest) -> tuple[str, str]:
    """Resolve an add-list request to ``(owner_user, slug)``.

    Accepts either a Trakt list ``url`` or an explicit ``owner_user`` + ``slug``.
    Raises :class:`TraktUrlError` when neither is usable.
    """
    if body.url:
        return parse_trakt_list_url(body.url)
    if body.owner_user and body.slug:
        return body.owner_user, body.slug
    raise TraktUrlError("Provide a Trakt list url, or owner_user and slug")
