"""Tests for core.clients.trakt."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from core.clients import trakt as trakt_mod
from core.clients.trakt import TRAKT_BASE_URL, TraktAuthError, TraktClient

_LIST_JSON = [
    {
        "type": "movie",
        "movie": {
            "title": "Dune",
            "year": 2021,
            "ids": {"trakt": 1, "slug": "dune", "imdb": "tt1", "tmdb": 100, "tvdb": None},
        },
    },
    {
        "type": "show",
        "show": {
            "title": "Severance",
            "year": 2022,
            "ids": {"trakt": 2, "imdb": "tt2", "tmdb": 200, "tvdb": 300},
        },
    },
    {"type": "movie", "movie": "broken"},  # skipped: not a dict
]


def make_client(tmp_path, *, dry_run=True, watchlist=True):
    return TraktClient(
        client_id="cid",
        client_secret="secret",
        user="me",
        list_id="watchlist" if watchlist else "my-list",
        token_store_path=str(tmp_path / "tokens.json"),
        dry_run_provider=lambda: dry_run,
    )


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch):
    """Freeze time and make sleeping instant."""
    monkeypatch.setattr(trakt_mod, "_now", lambda: 1000.0)
    monkeypatch.setattr(trakt_mod, "_monotonic", lambda: 0.0)

    async def _noop(_seconds):
        return None

    monkeypatch.setattr(trakt_mod, "_sleep", _noop)


def test_load_tokens_missing_then_present(tmp_path) -> None:
    client = make_client(tmp_path)
    client.load_tokens()
    assert client.is_authenticated() is False

    (tmp_path / "tokens.json").write_text(
        json.dumps({"access_token": "a", "refresh_token": "r", "expires_at": 9e9})
    )
    client.load_tokens()
    assert client.is_authenticated() is True


@respx.mock
async def test_request_device_code_logs(tmp_path) -> None:
    respx.post(f"{TRAKT_BASE_URL}/oauth/device/code").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dev",
                "user_code": "ABCD",
                "verification_url": "https://trakt.tv/activate",
                "interval": 0,
                "expires_in": 600,
            },
        )
    )
    client = make_client(tmp_path)
    data = await client.request_device_code()
    assert data["user_code"] == "ABCD"


@respx.mock
async def test_poll_success(tmp_path) -> None:
    respx.post(f"{TRAKT_BASE_URL}/oauth/device/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "a", "refresh_token": "r", "expires_in": 7200},
        )
    )
    client = make_client(tmp_path)
    ok = await client.poll_for_token({"device_code": "dev", "interval": 0, "expires_in": 600})
    assert ok is True
    assert client.is_authenticated() is True


@respx.mock
async def test_poll_pending_then_success(tmp_path) -> None:
    route = respx.post(f"{TRAKT_BASE_URL}/oauth/device/token")
    route.side_effect = [
        httpx.Response(400),
        httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 1}),
    ]
    client = make_client(tmp_path)
    ok = await client.poll_for_token({"device_code": "dev", "interval": 0, "expires_in": 600})
    assert ok is True


@respx.mock
async def test_poll_failure_status(tmp_path) -> None:
    respx.post(f"{TRAKT_BASE_URL}/oauth/device/token").mock(
        return_value=httpx.Response(410)
    )
    client = make_client(tmp_path)
    ok = await client.poll_for_token({"device_code": "dev", "interval": 0, "expires_in": 600})
    assert ok is False


async def test_poll_expired(tmp_path) -> None:
    client = make_client(tmp_path)
    ok = await client.poll_for_token({"device_code": "dev", "interval": 0, "expires_in": 0})
    assert ok is False


async def test_ensure_token_not_authenticated_raises(tmp_path) -> None:
    client = make_client(tmp_path)
    with pytest.raises(TraktAuthError):
        await client.ensure_token()


async def test_ensure_token_valid_no_refresh(tmp_path) -> None:
    client = make_client(tmp_path)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    assert await client.ensure_token() == "a"


@respx.mock
async def test_ensure_token_refreshes_when_near_expiry(tmp_path) -> None:
    respx.post(f"{TRAKT_BASE_URL}/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 7200}
        )
    )
    client = make_client(tmp_path)
    client._tokens = {"access_token": "old", "refresh_token": "r", "expires_at": 1000.0}
    assert await client.ensure_token() == "new"


@respx.mock
async def test_refresh_failure_raises(tmp_path) -> None:
    respx.post(f"{TRAKT_BASE_URL}/oauth/token").mock(return_value=httpx.Response(500))
    client = make_client(tmp_path)
    client._tokens = {"access_token": "old", "refresh_token": "r", "expires_at": 0.0}
    with pytest.raises(TraktAuthError):
        await client.ensure_token()


@respx.mock
async def test_read_list_items_watchlist(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/sync/watchlist/movies,shows").mock(
        return_value=httpx.Response(200, json=_LIST_JSON)
    )
    client = make_client(tmp_path, watchlist=True)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    items = await client.read_list_items()
    assert len(items) == 2  # broken entry skipped
    assert items[0]["tmdb"] == 100
    assert items[1]["tvdb"] == 300


@respx.mock
async def test_read_list_items_paginates(tmp_path) -> None:
    route = respx.get(f"{TRAKT_BASE_URL}/sync/watchlist/movies,shows")
    route.side_effect = [
        httpx.Response(
            200, json=[_LIST_JSON[0]], headers={"X-Pagination-Page-Count": "2"}
        ),
        httpx.Response(
            200, json=[_LIST_JSON[1]], headers={"X-Pagination-Page-Count": "2"}
        ),
    ]
    client = make_client(tmp_path, watchlist=True)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    items = await client.read_list_items()
    assert [i["trakt_id"] for i in items] == [1, 2]
    assert route.call_count == 2


@respx.mock
async def test_read_list_items_user_list(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/me/lists/my-list/items/movies,shows").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = make_client(tmp_path, watchlist=False)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    assert await client.read_list_items() == []


async def test_remove_items_dry_run_no_request(tmp_path) -> None:
    client = make_client(tmp_path, dry_run=True)
    result = await client.remove_items(movies=[100], shows=[300])
    assert result["dry_run"] is True
    assert result["would_remove"]["movies"] == [{"ids": {"tmdb": 100}}]
    assert result["would_remove"]["shows"] == [{"ids": {"tvdb": 300}}]


@respx.mock
async def test_remove_items_real_movie_user_list(tmp_path) -> None:
    route = respx.post(
        f"{TRAKT_BASE_URL}/users/me/lists/my-list/items/remove"
    ).mock(return_value=httpx.Response(200, json={"deleted": {"movies": 1}}))
    client = make_client(tmp_path, dry_run=False, watchlist=False)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    result = await client.remove_items(movies=[100])
    assert result == {"deleted": {"movies": 1}}
    assert route.called


@respx.mock
async def test_remove_items_real_show_watchlist(tmp_path) -> None:
    route = respx.post(f"{TRAKT_BASE_URL}/sync/watchlist/remove").mock(
        return_value=httpx.Response(200, json={"deleted": {"shows": 1}})
    )
    client = make_client(tmp_path, dry_run=False, watchlist=True)
    client._tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}
    result = await client.remove_items(shows=[300])
    assert result == {"deleted": {"shows": 1}}
    assert route.called


async def test_aclose(tmp_path) -> None:
    client = make_client(tmp_path)
    await client.aclose()


_TOKENS = {"access_token": "a", "refresh_token": "r", "expires_at": 9e9}


def test_update_credentials(tmp_path) -> None:
    client = make_client(tmp_path)
    client.update_credentials(client_id="c2", client_secret="s2", user="bob")
    assert client._client_id == "c2"
    assert client._client_secret == "s2"
    assert client._user == "bob"
    client.update_credentials(client_id="c3", client_secret="s3", user="")
    assert client._user == "me"  # blank user falls back to 'me'


@respx.mock
async def test_read_list_items_explicit_owner_and_list(tmp_path) -> None:
    respx.get(
        f"{TRAKT_BASE_URL}/users/bob/lists/anime/items/movies,shows"
    ).mock(return_value=httpx.Response(200, json=[]))
    client = make_client(tmp_path, watchlist=False)
    client._tokens = dict(_TOKENS)
    assert await client.read_list_items(list_id="anime", owner_user="bob") == []


@respx.mock
async def test_remove_items_explicit_owner_and_list(tmp_path) -> None:
    route = respx.post(
        f"{TRAKT_BASE_URL}/users/bob/lists/anime/items/remove"
    ).mock(return_value=httpx.Response(200, json={"deleted": {"movies": 1}}))
    client = make_client(tmp_path, dry_run=False, watchlist=False)
    client._tokens = dict(_TOKENS)
    result = await client.remove_items(movies=[1], list_id="anime", owner_user="bob")
    assert result == {"deleted": {"movies": 1}}
    assert route.called


@respx.mock
async def test_get_user_lists_normalises_and_filters(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/me/lists").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "Movies", "ids": {"slug": "movies", "trakt": 1}, "item_count": 19},
                {"name": "NoSlug", "ids": {"trakt": 42}, "item_count": 0},
                {"name": "Bad", "ids": {}},  # no slug, no trakt -> dropped
            ],
        )
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    lists = await client.get_user_lists()
    assert [item["slug"] for item in lists] == ["movies", "42"]
    assert lists[0]["owner_user"] == "me"
    assert lists[0]["item_count"] == 19


@respx.mock
async def test_get_list_summary_found(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/me/lists/movies").mock(
        return_value=httpx.Response(
            200, json={"name": "Movies", "ids": {"slug": "movies"}, "item_count": 19}
        )
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    summary = await client.get_list_summary(owner_user="me", slug="movies")
    assert summary["slug"] == "movies"
    assert summary["owner_user"] == "me"


@respx.mock
async def test_get_list_summary_not_found(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/me/lists/ghost").mock(
        return_value=httpx.Response(404)
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    assert await client.get_list_summary(owner_user="me", slug="ghost") is None


@respx.mock
async def test_test_connection_returns_username(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/settings").mock(
        return_value=httpx.Response(200, json={"user": {"username": "erena"}})
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    assert await client.test_connection() == {
        "ok": True,
        "detail": "Connected as erena",
        "username": "erena",
    }


@respx.mock
async def test_test_connection_missing_user(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/settings").mock(
        return_value=httpx.Response(200, json={})
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    assert await client.test_connection() == {
        "ok": True,
        "detail": "Connected to Trakt",
        "username": None,
    }


@respx.mock
async def test_test_connection_returns_failure_on_http_error(tmp_path) -> None:
    respx.get(f"{TRAKT_BASE_URL}/users/settings").mock(
        return_value=httpx.Response(401)
    )
    client = make_client(tmp_path)
    client._tokens = dict(_TOKENS)
    result = await client.test_connection()
    assert result["ok"] is False
    assert "401" in result["detail"]
    assert result["username"] is None
