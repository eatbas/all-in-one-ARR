"""Dashboard JSON API for Deletarr media-library cleaning."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.context import SyncAlreadyRunning

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

LibraryType = Literal["movies", "tv"]


class DeletarrScanRequest(BaseModel):
    type: LibraryType = "movies"


class DeletarrDeleteRequest(BaseModel):
    type: LibraryType = "movies"
    paths: list[str] = Field(min_length=1)


class DeletarrSettingsUpdate(BaseModel):
    movies_path: str | None = None
    tv_path: str | None = None
    use_arr_source: bool | None = None


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Deletarr unavailable")


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def create_deletarr_router(ctx: "AppContext") -> APIRouter:
    """Create the Deletarr API router."""
    router = APIRouter(prefix="/api/deletarr", tags=["deletarr"])

    @router.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return ctx.settings_store.deletarr_settings()

    @router.put("/settings")
    async def put_settings(body: DeletarrSettingsUpdate) -> dict:
        if ctx.deletarr_update_settings is None:
            raise _unavailable()
        return await ctx.deletarr_update_settings(
            movies_path=body.movies_path,
            tv_path=body.tv_path,
            use_arr_source=body.use_arr_source,
        )

    @router.get("/status")
    async def get_status() -> dict:
        if ctx.deletarr_status is None:
            raise _unavailable()
        return await ctx.deletarr_status()

    @router.get("/results")
    async def get_results(type: LibraryType = Query(default="movies")) -> dict:
        if ctx.deletarr_results is None:
            raise _unavailable()
        try:
            return await ctx.deletarr_results(type)
        except ValueError as exc:
            raise _bad_request(exc) from exc

    @router.post("/scan")
    async def post_scan(body: DeletarrScanRequest) -> dict:
        if ctx.deletarr_scan is None:
            raise _unavailable()
        try:
            return await ctx.deletarr_scan(body.type)
        except SyncAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail="Deletarr is already running") from exc
        except ValueError as exc:
            raise _bad_request(exc) from exc

    @router.post("/delete")
    async def post_delete(body: DeletarrDeleteRequest) -> dict:
        if ctx.deletarr_delete is None:
            raise _unavailable()
        try:
            return await ctx.deletarr_delete(body.type, body.paths)
        except SyncAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail="Deletarr is already running") from exc
        except ValueError as exc:
            raise _bad_request(exc) from exc

    return router
