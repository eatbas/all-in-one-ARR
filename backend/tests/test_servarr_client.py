"""Tests for the shared Servarr base client."""

from __future__ import annotations

import httpx
import pytest

from core.clients.servarr import ServarrClient, ServarrClientError


def _client(handler, *, app: str = "sonarr") -> ServarrClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ServarrClient(
        app=app, base_url="http://arr/", api_key="key", http_client=http
    )


async def test_shared_read_endpoints_filter_non_dict_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "key"
        if request.url.path == "/api/v3/series":
            return httpx.Response(200, json=[{"id": 1}, "bad", 3])
        assert request.url.params["seriesId"] == "1"
        return httpx.Response(200, json={"not": "a list"})

    client = _client(handler)
    assert client.base_url == "http://arr"
    assert await client.series() == [{"id": 1}]
    assert await client.episode_files(1) == []
    await client.aclose()


async def test_compatibility_uses_default_feature_name_and_unknown_app_minimum() -> (
    None
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"appName": "Lidarr", "version": "0.1"})

    wrong = _client(handler)
    result = await wrong.compatibility()
    assert result.ok is False
    assert result.detail == (
        "Connected service is Lidarr; aio-arr expected Sonarr for the "
        "configured sonarr connection"
    )
    await wrong.aclose()

    # An app without a registered minimum accepts any version.
    lidarr = _client(handler, app="lidarr")
    result = await lidarr.compatibility()
    assert result.ok is True
    assert result.detail == "Connected to Lidarr 0.1"
    await lidarr.aclose()


async def test_compatibility_defaults_missing_status_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _client(handler)
    result = await client.compatibility()
    assert result.app_name == "sonarr"
    assert result.version == "0.0.0"
    assert result.ok is False
    assert "requires Sonarr 4+" in result.detail
    await client.aclose()


async def test_system_status_rejects_non_dict_payload() -> None:
    client = _client(lambda request: httpx.Response(200, json=[]))
    with pytest.raises(ServarrClientError, match="invalid status payload"):
        await client.system_status()
    await client.aclose()


async def test_non_json_body_becomes_client_error() -> None:
    client = _client(lambda request: httpx.Response(200, content=b"<html>login</html>"))
    with pytest.raises(
        ServarrClientError,
        match="sonarr returned a non-JSON response from /api/v3/series",
    ):
        await client.series()
    await client.aclose()
