"""Tests for the Deletarr Servarr client."""

from __future__ import annotations

import httpx
import pytest

from modules.deletarr.arr_source import DeletarrArrClient, DeletarrArrError, client_for
from tests.conftest import make_ctx


def _client(handler, *, api_key: str = "key") -> DeletarrArrClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return DeletarrArrClient(
        app="radarr", base_url="http://arr/", api_key=api_key, http_client=http
    )


async def test_endpoints_return_filtered_dict_lists() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "key"
        path = request.url.path
        if path == "/api/v3/rootfolder":
            return httpx.Response(200, json=[{"path": "/movies"}, "bad"])
        if path == "/api/v3/movie":
            return httpx.Response(200, json=[{"id": 1}])
        if path == "/api/v3/series":
            return httpx.Response(200, json=[{"id": 2}])
        if path == "/api/v3/episodefile":
            assert request.url.params["seriesId"] == "2"
            return httpx.Response(200, json=[{"id": 3}])
        return httpx.Response(404)  # pragma: no cover - defensive

    client = _client(handler)
    assert await client.root_folders() == [{"path": "/movies"}]
    assert await client.movies() == [{"id": 1}]
    assert await client.series() == [{"id": 2}]
    assert await client.episode_files(2) == [{"id": 3}]
    await client.aclose()


async def test_empty_body_yields_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = _client(handler)
    assert await client.movies() == []
    await client.aclose()


async def test_unconfigured_client_raises() -> None:
    client = DeletarrArrClient(app="radarr", base_url="", api_key="")
    assert client.configured is False
    with pytest.raises(DeletarrArrError):
        await client.root_folders()
    await client.aclose()


async def test_http_status_error_becomes_deletarr_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client(handler)
    with pytest.raises(DeletarrArrError):
        await client.movies()
    await client.aclose()


async def test_transport_error_becomes_deletarr_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = _client(handler)
    with pytest.raises(DeletarrArrError):
        await client.movies()
    await client.aclose()


async def test_client_for_selects_app_from_context(db) -> None:
    ctx = make_ctx(db=db)
    movies_client = client_for(ctx, "movies")
    tv_client = client_for(ctx, "tv")
    assert movies_client.app == "radarr"
    assert tv_client.app == "sonarr"
    assert movies_client.configured is True
    await movies_client.aclose()
    await tv_client.aclose()
