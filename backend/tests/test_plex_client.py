"""Tests for core.clients.plex (read-only Plex Media Server client)."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.plex import (
    PlexClient,
    PlexClientError,
    PlexEpisode,
    PlexShow,
    parse_tvdb_guid,
)

_BASE = "http://plex:32400"
_TOKEN = "plex-token-123"
_IDENTITY = f"{_BASE}/"
_SECTIONS = f"{_BASE}/library/sections"


def make_client(*, base_url: str = _BASE, api_key: str = _TOKEN) -> PlexClient:
    return PlexClient(base_url=base_url, api_key=api_key)


def _container(**fields: object) -> dict[str, object]:
    return {"MediaContainer": fields}


# ---- test_connection ----


@respx.mock
async def test_connection_ok_reports_name_and_version() -> None:
    route = respx.get(_IDENTITY).mock(
        return_value=httpx.Response(
            200, json=_container(friendlyName="Home", version="1.41.0")
        )
    )
    result = await make_client().test_connection()
    assert result == {
        "ok": True,
        "detail": "Connected to Plex Media Server “Home” (version 1.41.0)",
    }
    request = route.calls.last.request
    # The token travels only in the header, never in the URL.
    assert request.headers["X-Plex-Token"] == _TOKEN
    assert request.headers["Accept"] == "application/json"
    assert _TOKEN not in str(request.url)


@respx.mock
async def test_connection_ok_without_identity_fields() -> None:
    respx.get(_IDENTITY).mock(return_value=httpx.Response(200, json=_container()))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to Plex Media Server"}


@respx.mock
async def test_blank_token_reported_without_request() -> None:
    route = respx.get(_IDENTITY).mock(return_value=httpx.Response(200))
    result = await make_client(api_key="  ").test_connection()
    assert result == {"ok": False, "detail": "Plex token is not set"}
    assert not route.called


@respx.mock
async def test_blank_url_reported_without_request() -> None:
    route = respx.get(_IDENTITY).mock(return_value=httpx.Response(200))
    result = await make_client(base_url="").test_connection()
    assert result == {"ok": False, "detail": "Plex URL is not set"}
    assert not route.called


@pytest.mark.parametrize("status", [401, 403])
@respx.mock
async def test_rejected_token(status: int) -> None:
    respx.get(_IDENTITY).mock(return_value=httpx.Response(status))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "Plex rejected the token"}


@respx.mock
async def test_other_status_reports_http_code() -> None:
    respx.get(_IDENTITY).mock(return_value=httpx.Response(500))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "Plex returned HTTP 500 from /"}


@respx.mock
async def test_transport_error_reports_failure() -> None:
    respx.get(_IDENTITY).mock(side_effect=httpx.ConnectError("refused"))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert result["detail"].startswith("Connection to Plex failed")
    assert _TOKEN not in result["detail"]


@respx.mock
async def test_non_json_response_is_an_error() -> None:
    respx.get(_IDENTITY).mock(return_value=httpx.Response(200, text="<html>login"))
    result = await make_client().test_connection()
    assert result == {
        "ok": False,
        "detail": "Plex returned a non-JSON response from /",
    }


@pytest.mark.parametrize("payload", [[1, 2], {"MediaContainer": "nope"}, {}])
@respx.mock
async def test_invalid_payload_shape_is_an_error(payload: object) -> None:
    respx.get(_IDENTITY).mock(return_value=httpx.Response(200, json=payload))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "Plex returned an invalid payload from /"}


@respx.mock
async def test_token_whitespace_is_stripped_in_header() -> None:
    route = respx.get(_IDENTITY).mock(
        return_value=httpx.Response(200, json=_container())
    )
    await make_client(api_key=f" {_TOKEN}\n").test_connection()
    assert route.calls.last.request.headers["X-Plex-Token"] == _TOKEN


@respx.mock
async def test_update_credentials_switches_server_and_token() -> None:
    route = respx.get("http://other:32400/").mock(
        return_value=httpx.Response(200, json=_container(friendlyName="Other"))
    )
    client = make_client(base_url="", api_key="")
    assert client.configured is False
    client.update_credentials(base_url="http://other:32400/", api_key="new-token")
    assert client.configured is True
    result = await client.test_connection()
    assert result["detail"] == "Connected to Plex Media Server “Other”"
    assert route.calls.last.request.headers["X-Plex-Token"] == "new-token"


# ---- library reads ----


@respx.mock
async def test_show_sections_keeps_only_tv_libraries() -> None:
    respx.get(_SECTIONS).mock(
        return_value=httpx.Response(
            200,
            json=_container(
                Directory=[
                    {"key": "1", "type": "movie", "title": "Films"},
                    {"key": "2", "type": "show", "title": "TV"},
                    {"key": 3, "type": "show", "title": "Anime"},
                    {"type": "show", "title": "No key"},
                    "garbage",
                ]
            ),
        )
    )
    assert await make_client().show_sections() == ["2", "3"]


@pytest.mark.parametrize("fields", [{}, {"size": 0}, {"size": "0"}])
@respx.mock
async def test_show_sections_of_an_empty_container(fields: dict[str, object]) -> None:
    # Plex omits the list from an empty container: a valid empty result.
    respx.get(_SECTIONS).mock(
        return_value=httpx.Response(200, json=_container(**fields))
    )
    assert await make_client().show_sections() == []


@pytest.mark.parametrize(
    ("fields", "detail"),
    [
        ({"Directory": "nope"}, "an invalid Directory list"),
        ({"Directory": {"key": "2"}}, "an invalid Directory list"),
        ({"size": 2}, "an incomplete Directory list"),
    ],
)
@respx.mock
async def test_show_sections_reject_a_malformed_directory(
    fields: dict[str, object], detail: str
) -> None:
    respx.get(_SECTIONS).mock(
        return_value=httpx.Response(200, json=_container(**fields))
    )
    with pytest.raises(PlexClientError) as excinfo:
        await make_client().show_sections()
    assert str(excinfo.value) == f"Plex returned {detail} from /library/sections"
    assert excinfo.value.status_code is None


@respx.mock
async def test_shows_parse_tvdb_guids() -> None:
    route = respx.get(f"{_BASE}/library/sections/2/all").mock(
        return_value=httpx.Response(
            200,
            json=_container(
                Metadata=[
                    {
                        "ratingKey": "100",
                        "title": "Frieren",
                        "Guid": [
                            {"id": "imdb://tt22248376"},
                            {"id": "tvdb://424536"},
                        ],
                    },
                    # IMDb-only: matched to nothing.
                    {
                        "ratingKey": 101,
                        "title": "IMDb only",
                        "Guid": [{"id": "imdb://x"}],
                    },
                    # Legacy agent: the item-level guid is not parsed.
                    {
                        "ratingKey": "102",
                        "title": "Legacy",
                        "guid": "com.plexapp.agents.thetvdb://81189?lang=en",
                    },
                    {"title": "No rating key"},
                    "garbage",
                ]
            ),
        )
    )
    shows = await make_client().shows("2")
    assert shows == [
        PlexShow("100", "Frieren", frozenset({424536})),
        PlexShow("101", "IMDb only", frozenset()),
        PlexShow("102", "Legacy", frozenset()),
    ]
    assert route.calls.last.request.url.params["includeGuids"] == "1"


@respx.mock
async def test_shows_of_an_empty_section() -> None:
    respx.get(f"{_BASE}/library/sections/2/all").mock(
        return_value=httpx.Response(200, json=_container(size=0))
    )
    assert await make_client().shows("2") == []


@pytest.mark.parametrize(
    ("fields", "detail"),
    [
        ({"size": 2, "Metadata": "nope"}, "an invalid Metadata list"),
        ({"size": 2}, "an incomplete Metadata list"),
    ],
)
@respx.mock
async def test_shows_reject_a_malformed_metadata_list(
    fields: dict[str, object], detail: str
) -> None:
    respx.get(f"{_BASE}/library/sections/2/all").mock(
        return_value=httpx.Response(200, json=_container(**fields))
    )
    with pytest.raises(PlexClientError) as excinfo:
        await make_client().shows("2")
    assert str(excinfo.value) == f"Plex returned {detail} from /library/sections/2/all"


@pytest.mark.parametrize(
    ("fields", "detail"),
    [
        ({"size": 2, "Metadata": "not a list"}, "an invalid Metadata list"),
        ({"size": 2, "Metadata": None}, "an incomplete Metadata list"),
    ],
)
@respx.mock
async def test_episodes_reject_a_malformed_metadata_list(
    fields: dict[str, object], detail: str
) -> None:
    respx.get(f"{_BASE}/library/metadata/100/allLeaves").mock(
        return_value=httpx.Response(200, json=_container(**fields))
    )
    with pytest.raises(PlexClientError) as excinfo:
        await make_client().episodes("100")
    assert str(excinfo.value) == (
        f"Plex returned {detail} from /library/metadata/100/allLeaves"
    )


@respx.mock
async def test_episodes_read_watch_counts() -> None:
    respx.get(f"{_BASE}/library/metadata/100/allLeaves").mock(
        return_value=httpx.Response(
            200,
            json=_container(
                Metadata=[
                    {"parentIndex": 1, "index": 1, "viewCount": 2},
                    {"parentIndex": 1, "index": 2},
                    {"parentIndex": "1", "index": "3", "viewCount": "bad"},
                    {"parentIndex": 1, "index": 4, "viewCount": -1},
                    # No usable numbering: skipped.
                    {"parentIndex": None, "index": 5},
                    {"parentIndex": 1},
                ]
            ),
        )
    )
    assert await make_client().episodes("100") == [
        PlexEpisode(1, 1, 2),
        PlexEpisode(1, 2, 0),
        PlexEpisode(1, 3, 0),
        PlexEpisode(1, 4, 0),
    ]


@respx.mock
async def test_rating_key_is_path_escaped() -> None:
    route = respx.get(f"{_BASE}/library/metadata/a%2Fb/allLeaves").mock(
        return_value=httpx.Response(200, json=_container())
    )
    assert await make_client().episodes("a/b") == []
    assert route.called


async def test_unconfigured_reads_raise_without_request() -> None:
    with pytest.raises(PlexClientError, match="not configured") as excinfo:
        await make_client(api_key="").show_sections()
    assert excinfo.value.status_code is None


@respx.mock
async def test_read_errors_are_wrapped_with_status() -> None:
    respx.get(_SECTIONS).mock(return_value=httpx.Response(401))
    with pytest.raises(PlexClientError, match="rejected the token") as excinfo:
        await make_client().show_sections()
    assert excinfo.value.status_code == 401

    respx.get(f"{_BASE}/library/metadata/9/allLeaves").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(PlexClientError, match="HTTP 404") as excinfo:
        await make_client().episodes("9")
    assert excinfo.value.status_code == 404


@respx.mock
async def test_aclose_closes_the_http_client() -> None:
    transport = httpx.AsyncClient()
    client = PlexClient(base_url=_BASE, api_key=_TOKEN, http_client=transport)
    await client.aclose()
    assert transport.is_closed


# ---- parse_tvdb_guid ----


def test_parse_tvdb_guid_accepts_only_tvdb_digits() -> None:
    assert parse_tvdb_guid(
        [
            {"id": "tvdb://123"},
            {"id": " tvdb://456 "},
            {"id": "tvdb://0"},
            {"id": "tvdb://12a"},
            {"id": "tvdb://"},
            {"id": "tmdb://99"},
            {"id": 5},
            {},
            "tvdb://789",
        ]
    ) == {123, 456}


@pytest.mark.parametrize("value", [None, "tvdb://1", {"id": "tvdb://1"}, 7])
def test_parse_tvdb_guid_ignores_non_lists(value: object) -> None:
    assert parse_tvdb_guid(value) == set()
