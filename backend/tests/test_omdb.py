"""Tests for core.clients.omdb (OMDb connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.omdb import OmdbClient

_URL = "https://www.omdbapi.com"


@respx.mock
async def test_valid_key_succeeds() -> None:
    route = respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "x"})
    )
    result = await OmdbClient(api_key="ok").test_connection()
    assert result == {"ok": True, "detail": "Connected to OMDb (1 key OK)"}
    assert route.calls.last.request.url.params["apikey"] == "ok"


@respx.mock
async def test_invalid_key_reports_error_body() -> None:
    # OMDb answers a bad key with HTTP 200 and the reason in the body.
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"Response": "False", "Error": "Invalid API key!"}
        )
    )
    result = await OmdbClient(api_key="bad").test_connection()
    assert result == {
        "ok": False,
        "detail": "1 key configured — key 1: Invalid API key!",
    }


@respx.mock
async def test_non_200_reports_http_status() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(401, json={}))
    result = await OmdbClient(api_key="bad").test_connection()
    assert result["ok"] is False
    assert "key 1: invalid API key" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    result = await OmdbClient(api_key="x").test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_non_json_body_is_handled() -> None:
    # A 200 whose body is not JSON must degrade gracefully, not raise.
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    result = await OmdbClient(api_key="x").test_connection()
    assert result == {
        "ok": False,
        "detail": "1 key configured — key 1: OMDb rejected the API key",
    }


@respx.mock
async def test_update_credentials_changes_key() -> None:
    route = respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    client = OmdbClient(api_key="old")
    client.update_credentials(api_key="new")
    await client.test_connection()
    assert route.calls.last.request.url.params["apikey"] == "new"


_POSTER_URL = "https://m.media-amazon.com/images/poster.jpg"


@respx.mock
async def test_fetch_poster_downloads_image() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"Response": "True", "Poster": _POSTER_URL}
        )
    )
    respx.get(_POSTER_URL).mock(return_value=httpx.Response(200, content=b"OMDBJPEG"))
    data = await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1")
    assert data == b"OMDBJPEG"


@respx.mock
async def test_fetch_poster_na_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": "N/A"}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_missing_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Title": "x"}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_lookup_non_200_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500, json={}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_lookup_network_error_returns_none() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_non_json_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_image_non_200_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": _POSTER_URL}))
    respx.get(_POSTER_URL).mock(return_value=httpx.Response(404))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_image_network_error_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": _POSTER_URL}))
    respx.get(_POSTER_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_rating_parses_rating_and_votes() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "imdbRating": "8.6", "imdbVotes": "1,234,567"},
        )
    )
    result = await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1")
    assert result == {"imdb_rating": 8.6, "imdb_votes": 1234567}


@respx.mock
async def test_fetch_rating_na_values_become_none() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"imdbRating": "N/A", "imdbVotes": "N/A"})
    )
    assert await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_unparseable_values_become_none() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"imdbRating": "bad", "imdbVotes": "x"})
    )
    assert await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_non_200_is_a_retryable_failure() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500, json={}))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") is None


@respx.mock
async def test_fetch_rating_network_error_is_a_retryable_failure() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") is None


@respx.mock
async def test_fetch_rating_non_json_is_a_retryable_failure() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>"))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") is None


async def test_aclose() -> None:
    await OmdbClient(api_key="x").aclose()


# ---- API-key rotation ----


@respx.mock
async def test_rating_rotates_to_next_key_on_401_and_sticks() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(
            401, json={"Response": "False", "Error": "Request limit reached!"}
        )
    )
    working = respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(
            200, json={"imdbRating": "8.6", "imdbVotes": "1,234"}
        )
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    result = await client.fetch_rating(imdb_id="tt1")
    assert result == {"imdb_rating": 8.6, "imdb_votes": 1234}
    # The rotation sticks: the next lookup goes straight to the working key.
    await client.fetch_rating(imdb_id="tt2")
    assert working.call_count == 2


@respx.mock
async def test_rating_all_keys_exhausted_is_a_retryable_failure() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(401, json={}))
    client = OmdbClient(api_key="k1", api_key_2="k2")
    # A failure, not a "no rating" answer: callers must retry, never cache.
    assert await client.fetch_rating(imdb_id="tt1") is None
    # Parked on the last key: a later call costs one probe, not a full sweep.
    calls_before = respx.calls.call_count
    await client.fetch_rating(imdb_id="tt2")
    assert respx.calls.call_count == calls_before + 1


@respx.mock
async def test_rotation_resets_on_new_utc_day(monkeypatch) -> None:
    from core.clients import omdb as omdb_mod

    day = {"value": "2026-07-12"}
    monkeypatch.setattr(omdb_mod, "_today", lambda: day["value"])
    primary = respx.get(_URL, params={"apikey": "k1"})
    primary.mock(return_value=httpx.Response(401, json={}))
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(200, json={"imdbRating": "7.0", "imdbVotes": "10"})
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    await client.fetch_rating(imdb_id="tt1")  # rotated to k2

    day["value"] = "2026-07-13"  # quotas reset overnight
    primary.mock(
        return_value=httpx.Response(200, json={"imdbRating": "9.0", "imdbVotes": "5"})
    )
    result = await client.fetch_rating(imdb_id="tt2")
    assert result["imdb_rating"] == 9.0  # back on the primary key


@respx.mock
async def test_rating_network_error_does_not_rotate() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        side_effect=httpx.ConnectError("down")
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    assert await client.fetch_rating(imdb_id="tt1") is None
    # A network failure is not key-specific, so the primary stays active.
    assert client._active_index == 0


@respx.mock
async def test_update_credentials_restarts_rotation() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(401, json={})
    )
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(200, json={"imdbRating": "7.0", "imdbVotes": "1"})
    )
    fresh = respx.get(_URL, params={"apikey": "fresh"}).mock(
        return_value=httpx.Response(200, json={"imdbRating": "6.0", "imdbVotes": "2"})
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    await client.fetch_rating(imdb_id="tt1")  # rotated to k2
    client.update_credentials(api_key="fresh")
    result = await client.fetch_rating(imdb_id="tt2")
    assert result["imdb_rating"] == 6.0
    assert fresh.call_count == 1


def test_key_count_dedupes_and_drops_blanks() -> None:
    client = OmdbClient(api_key="k1", api_key_2="", api_key_3="k1", api_key_4="k2")
    assert client.key_count() == 2
    # No usable key at all still reports a sane count for the budget maths.
    assert OmdbClient(api_key="").key_count() == 0


async def test_fetch_rating_without_any_key_is_a_retryable_failure() -> None:
    client = OmdbClient(api_key="")
    assert await client.fetch_rating(imdb_id="tt1") is None


@respx.mock
async def test_poster_lookup_uses_rotation() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(401, json={})
    )
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(200, json={"Poster": "https://img.example/p.jpg"})
    )
    respx.get("https://img.example/p.jpg").mock(
        return_value=httpx.Response(200, content=b"img-bytes")
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    assert await client.fetch_poster(imdb_id="tt1") == b"img-bytes"


# ---- multi-key connection test and the status-checker probe ----


@respx.mock
async def test_test_connection_reports_extras_when_primary_is_empty() -> None:
    # Regression for the "Test OMDb is not working" report: with no UI-managed
    # primary key but configured rotation keys, the test reports the real pool
    # state instead of failing on the empty primary.
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    client = OmdbClient(api_key="", api_key_2="k2")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to OMDb (1 key OK)"}


@respx.mock
async def test_test_connection_sweeps_every_configured_key() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    respx.get(_URL, params={"apikey": "k3"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    client = OmdbClient(api_key="k1", api_key_2="k2", api_key_3="k3")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to OMDb (3 keys OK)"}
    assert respx.calls.call_count == 3


@respx.mock
async def test_test_connection_names_the_broken_key() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    respx.get(_URL, params={"apikey": "bad"}).mock(
        return_value=httpx.Response(
            200, json={"Response": "False", "Error": "Invalid API key!"}
        )
    )
    client = OmdbClient(api_key="k1", api_key_2="bad")
    result = await client.test_connection()
    assert result["ok"] is False
    assert result["detail"] == "2 keys configured — key 2: Invalid API key!"


@respx.mock
async def test_test_connection_treats_limit_reached_as_valid() -> None:
    # A quota-exhausted key is still a working key; the test must not go red
    # every evening on busy days.
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    respx.get(_URL, params={"apikey": "k2"}).mock(
        return_value=httpx.Response(
            401, json={"Response": "False", "Error": "Request limit reached!"}
        )
    )
    client = OmdbClient(api_key="k1", api_key_2="k2")
    result = await client.test_connection()
    assert result == {
        "ok": True,
        "detail": "Connected to OMDb (2 keys valid, 1 at today's request limit)",
    }


async def test_test_connection_without_any_key() -> None:
    result = await OmdbClient(api_key="").test_connection()
    assert result == {"ok": False, "detail": "No OMDb API key configured"}


@respx.mock
async def test_status_probe_checks_only_the_first_key() -> None:
    # The background checker runs every 30-60 s; probing the whole pool there
    # would burn thousands of requests per day, so it checks one key only.
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    client = OmdbClient(api_key="k1", api_key_2="k2", api_key_3="k3")
    result = await client.status_probe()
    assert result == {"ok": True, "detail": "Connected to OMDb"}
    assert respx.calls.call_count == 1


@respx.mock
async def test_status_probe_reports_limited_key_as_connected() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(
            401, json={"Response": "False", "Error": "Request limit reached!"}
        )
    )
    client = OmdbClient(api_key="k1")
    result = await client.status_probe()
    assert result == {
        "ok": True,
        "detail": "Connected to OMDb (key at today's request limit)",
    }


@respx.mock
async def test_status_probe_reports_failure() -> None:
    respx.get(_URL, params={"apikey": "k1"}).mock(
        return_value=httpx.Response(500, json={})
    )
    client = OmdbClient(api_key="k1")
    result = await client.status_probe()
    assert result == {"ok": False, "detail": "OMDb: HTTP 500"}


async def test_status_probe_without_any_key() -> None:
    result = await OmdbClient(api_key="").status_probe()
    assert result == {"ok": False, "detail": "No OMDb API key configured"}
