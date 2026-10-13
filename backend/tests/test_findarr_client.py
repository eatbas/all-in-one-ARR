"""Tests for the Findarr Servarr API helper."""

from __future__ import annotations

import httpx
import pytest
import respx

from modules.findarr.client import FindarrArrClient, FindarrClientError, parse_version
from modules.findarr.models import SearchUnit


def _unit(command: str, **kwargs) -> SearchUnit:
    base = {
        "app": "sonarr",
        "mode": "missing",
        "command": command,
        "key": "k",
        "title": "t",
        "monitored": True,
        "is_future": False,
    }
    base.update(kwargs)
    return SearchUnit(**base)


def test_parse_version_handles_suffixes_and_short_values() -> None:
    assert parse_version("6.0.1.2") == (6, 0, 1)
    assert parse_version("4.0.0-nightly") == (4, 0, 0)
    assert parse_version("") == (0, 0, 0)


@respx.mock
async def test_compatibility_accepts_supported_sonarr() -> None:
    respx.get("http://sonarr/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"appName": "Sonarr", "version": "4.0.1"})
    )
    result = await FindarrArrClient(
        app="sonarr", base_url="http://sonarr", api_key="k"
    ).compatibility()
    assert result.ok is True
    assert result.detail == "Connected to Sonarr 4.0.1"


@respx.mock
async def test_compatibility_rejects_old_radarr() -> None:
    respx.get("http://radarr/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"appName": "Radarr", "version": "5.9.9"})
    )
    result = await FindarrArrClient(
        app="radarr", base_url="http://radarr", api_key="k"
    ).compatibility()
    assert result.ok is False
    assert "Radarr 6+" in result.detail


@pytest.mark.parametrize(
    ("configured_app", "reported_app", "version"),
    [
        ("sonarr", "Radarr", "6.0.0"),
        ("radarr", "Sonarr", "4.0.0"),
    ],
)
@respx.mock
async def test_compatibility_rejects_wrong_service_identity(
    configured_app: str,
    reported_app: str,
    version: str,
) -> None:
    respx.get(f"http://{configured_app}/api/v3/system/status").mock(
        return_value=httpx.Response(
            200, json={"appName": reported_app, "version": version}
        )
    )
    result = await FindarrArrClient(
        app=configured_app,
        base_url=f"http://{configured_app}",
        api_key="k",
    ).compatibility()
    assert result.ok is False
    assert reported_app in result.detail
    assert configured_app.capitalize() in result.detail


@respx.mock
async def test_request_errors_are_normalised() -> None:
    respx.get("http://sonarr/api/v3/system/status").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(FindarrClientError):
        await FindarrArrClient(
            app="sonarr", base_url="http://sonarr", api_key="k"
        ).system_status()


@respx.mock
async def test_system_status_rejects_non_dict_payload() -> None:
    respx.get("http://sonarr/api/v3/system/status").mock(
        return_value=httpx.Response(200, json=[])
    )
    with pytest.raises(FindarrClientError):
        await FindarrArrClient(
            app="sonarr", base_url="http://sonarr", api_key="k"
        ).system_status()


async def test_unconfigured_client_raises() -> None:
    client = FindarrArrClient(app="sonarr", base_url="", api_key="")
    with pytest.raises(FindarrClientError):
        await client.system_status()
    await client.aclose()


@respx.mock
async def test_queue_size_accepts_dict_and_list_payloads() -> None:
    respx.get("http://sonarr/api/v3/queue").mock(
        return_value=httpx.Response(200, json={"totalRecords": 7, "records": []})
    )
    assert (
        await FindarrArrClient(
            app="sonarr", base_url="http://sonarr", api_key="k"
        ).queue_size()
        == 7
    )

    respx.get("http://radarr/api/v3/queue").mock(
        return_value=httpx.Response(200, json=[{}, {}])
    )
    assert (
        await FindarrArrClient(
            app="radarr", base_url="http://radarr", api_key="k"
        ).queue_size()
        == 2
    )

    respx.get("http://other/api/v3/queue").mock(
        return_value=httpx.Response(200, json="bad")
    )
    assert (
        await FindarrArrClient(
            app="radarr", base_url="http://other", api_key="k"
        ).queue_size()
        == 0
    )


@respx.mock
async def test_wanted_paginates_records() -> None:
    respx.get(
        "http://sonarr/api/v3/wanted/missing",
        params={"page": 1, "pageSize": 100, "includeSeries": "true"},
    ).mock(
        return_value=httpx.Response(
            200, json={"totalRecords": 2, "records": [{"id": 1}]}
        )
    )
    respx.get(
        "http://sonarr/api/v3/wanted/missing",
        params={"page": 2, "pageSize": 100, "includeSeries": "true"},
    ).mock(
        return_value=httpx.Response(
            200, json={"totalRecords": 2, "records": [{"id": 2}]}
        )
    )
    items = await FindarrArrClient(
        app="sonarr", base_url="http://sonarr", api_key="k"
    ).wanted("missing")
    assert items == [{"id": 1}, {"id": 2}]


@respx.mock
async def test_wanted_paginates_when_total_records_absent() -> None:
    # Older Arr builds omit ``totalRecords``; pagination must then continue until
    # an empty page rather than stopping after the first (which dropped records).
    respx.get(
        "http://radarr/api/v3/wanted/missing", params={"page": 1, "pageSize": 100}
    ).mock(return_value=httpx.Response(200, json={"records": [{"id": 1}]}))
    respx.get(
        "http://radarr/api/v3/wanted/missing", params={"page": 2, "pageSize": 100}
    ).mock(return_value=httpx.Response(200, json={"records": [{"id": 2}]}))
    respx.get(
        "http://radarr/api/v3/wanted/missing", params={"page": 3, "pageSize": 100}
    ).mock(return_value=httpx.Response(200, json={"records": []}))
    items = await FindarrArrClient(
        app="radarr", base_url="http://radarr", api_key="k"
    ).wanted("missing")
    assert items == [{"id": 1}, {"id": 2}]


@respx.mock
async def test_wanted_without_total_records_stops_on_empty_first_page() -> None:
    respx.get(
        "http://radarr/api/v3/wanted/missing", params={"page": 1, "pageSize": 100}
    ).mock(return_value=httpx.Response(200, json={"records": []}))
    assert (
        await FindarrArrClient(
            app="radarr", base_url="http://radarr", api_key="k"
        ).wanted("missing")
        == []
    )


@respx.mock
async def test_wanted_requests_embedded_series_for_sonarr_only() -> None:
    sonarr_route = respx.get("http://sonarr/api/v3/wanted/missing").mock(
        return_value=httpx.Response(200, json={"totalRecords": 0, "records": []})
    )
    await FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k").wanted(
        "missing"
    )
    assert sonarr_route.calls.last.request.url.params["includeSeries"] == "true"

    radarr_route = respx.get("http://radarr/api/v3/wanted/missing").mock(
        return_value=httpx.Response(200, json={"totalRecords": 0, "records": []})
    )
    await FindarrArrClient(app="radarr", base_url="http://radarr", api_key="k").wanted(
        "missing"
    )
    assert "includeSeries" not in radarr_route.calls.last.request.url.params


@respx.mock
async def test_wanted_accepts_list_payload_and_rejects_invalid_records() -> None:
    respx.get("http://radarr/api/v3/wanted/cutoff").mock(
        return_value=httpx.Response(200, json=[{"id": 1}, "bad"])
    )
    assert await FindarrArrClient(
        app="radarr", base_url="http://radarr", api_key="k"
    ).wanted("cutoff") == [{"id": 1}]

    respx.get("http://sonarr/api/v3/wanted/cutoff").mock(
        return_value=httpx.Response(200, json={"records": "bad"})
    )
    with pytest.raises(FindarrClientError):
        await FindarrArrClient(
            app="sonarr", base_url="http://sonarr", api_key="k"
        ).wanted("cutoff")

    respx.get("http://other/api/v3/wanted/cutoff").mock(
        return_value=httpx.Response(200, json="bad")
    )
    with pytest.raises(FindarrClientError):
        await FindarrArrClient(
            app="radarr", base_url="http://other", api_key="k"
        ).wanted("cutoff")


@respx.mock
async def test_trigger_search_uses_episode_and_movie_payloads() -> None:
    sonarr_route = respx.post("http://sonarr/api/v3/command").mock(
        return_value=httpx.Response(201, json={})
    )
    await FindarrArrClient(
        app="sonarr", base_url="http://sonarr", api_key="k"
    ).trigger_search(_unit("EpisodeSearch", episode_ids=(12,)))
    assert (
        sonarr_route.calls.last.request.content
        == b'{"name":"EpisodeSearch","episodeIds":[12]}'
    )

    radarr_route = respx.post("http://radarr/api/v3/command").mock(
        return_value=httpx.Response(201, json={})
    )
    await FindarrArrClient(
        app="radarr", base_url="http://radarr", api_key="k"
    ).trigger_search(_unit("MoviesSearch", app="radarr", movie_ids=(34,)))
    assert (
        radarr_route.calls.last.request.content
        == b'{"name":"MoviesSearch","movieIds":[34]}'
    )


@respx.mock
async def test_trigger_search_builds_season_and_series_payloads() -> None:
    season_route = respx.post("http://sonarr/api/v3/command").mock(
        return_value=httpx.Response(201, json={})
    )
    client = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    await client.trigger_search(_unit("SeasonSearch", series_id=7, season_number=2))
    assert (
        season_route.calls.last.request.content
        == b'{"name":"SeasonSearch","seriesId":7,"seasonNumber":2}'
    )

    await client.trigger_search(_unit("SeriesSearch", series_id=9))
    assert (
        season_route.calls.last.request.content
        == b'{"name":"SeriesSearch","seriesId":9}'
    )


@respx.mock
async def test_trigger_search_accepts_empty_response() -> None:
    respx.post("http://sonarr/api/v3/command").mock(return_value=httpx.Response(204))
    await FindarrArrClient(
        app="sonarr", base_url="http://sonarr", api_key="k"
    ).trigger_search(_unit("EpisodeSearch", episode_ids=(1,)))


@respx.mock
async def test_trigger_search_returns_the_command_id() -> None:
    respx.post("http://sonarr/api/v3/command").mock(
        side_effect=[
            httpx.Response(201, json={"id": 4242, "name": "EpisodeSearch"}),
            httpx.Response(201, json={"id": "not-an-int"}),
        ]
    )
    client = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    unit = _unit("EpisodeSearch", episode_ids=(1,))
    assert await client.trigger_search(unit) == 4242
    assert await client.trigger_search(unit) is None


@respx.mock
async def test_command_returns_resource_none_when_purged_and_raises_otherwise() -> None:
    respx.get("http://sonarr/api/v3/command/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "status": "completed"})
    )
    respx.get("http://sonarr/api/v3/command/2").mock(return_value=httpx.Response(404))
    respx.get("http://sonarr/api/v3/command/3").mock(return_value=httpx.Response(500))
    respx.get("http://sonarr/api/v3/command/4").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    assert (await client.command(1)) == {"id": 1, "status": "completed"}
    assert await client.command(2) is None
    with pytest.raises(FindarrClientError) as server_error:
        await client.command(3)
    assert server_error.value.status_code == 500
    with pytest.raises(FindarrClientError, match="invalid command payload"):
        await client.command(4)


@respx.mock
async def test_transport_errors_carry_no_status_code() -> None:
    respx.get("http://sonarr/api/v3/command/1").mock(
        side_effect=httpx.ConnectError("refused")
    )
    client = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    with pytest.raises(FindarrClientError) as transport_error:
        await client.command(1)
    assert transport_error.value.status_code is None


@respx.mock
async def test_custom_format_endpoints() -> None:
    respx.get("http://sonarr/api/v3/qualityprofile").mock(
        return_value=httpx.Response(200, json=[{"id": 9}, "junk"])
    )
    episodes = respx.get("http://sonarr/api/v3/episode").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    sonarr = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    assert await sonarr.quality_profiles() == [{"id": 9}]
    assert await sonarr.episodes_with_files(7) == [{"id": 1}]
    assert episodes.calls.last.request.url.params["seriesId"] == "7"
    assert episodes.calls.last.request.url.params["includeEpisodeFile"] == "true"

    respx.get("http://radarr/api/v3/movie").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    files = respx.get("http://radarr/api/v3/moviefile").mock(
        return_value=httpx.Response(200, json=[{"movieId": 1}])
    )
    radarr = FindarrArrClient(app="radarr", base_url="http://radarr", api_key="k")
    assert await radarr.movies() == [{"id": 1}]
    movie_ids = list(range(1, 151))
    assert await radarr.movie_files(movie_ids) == [{"movieId": 1}, {"movieId": 1}]
    # 150 ids are read in two batches, each as repeated movieId parameters.
    assert files.call_count == 2
    first_batch = files.calls[0].request.url.params.get_list("movieId")
    assert first_batch == [str(movie_id) for movie_id in range(1, 101)]
    assert files.calls[1].request.url.params.get_list("movieId")[0] == "101"
    assert await radarr.movie_files([]) == []


@respx.mock
async def test_grabs_since_reads_grabbed_history_with_episodes_for_sonarr() -> None:
    sonarr_route = respx.get("http://sonarr/api/v3/history/since").mock(
        return_value=httpx.Response(200, json=[{"episodeId": 1}, "junk"])
    )
    sonarr = FindarrArrClient(app="sonarr", base_url="http://sonarr", api_key="k")
    assert await sonarr.grabs_since("2026-10-13T00:00:00+00:00") == [{"episodeId": 1}]
    params = sonarr_route.calls.last.request.url.params
    assert params["date"] == "2026-10-13T00:00:00+00:00"
    assert params["eventType"] == "grabbed"
    assert params["includeEpisode"] == "true"

    radarr_route = respx.get("http://radarr/api/v3/history/since").mock(
        return_value=httpx.Response(200, json=[{"movieId": 2}])
    )
    radarr = FindarrArrClient(app="radarr", base_url="http://radarr", api_key="k")
    assert await radarr.grabs_since("2026-10-13T00:00:00+00:00") == [{"movieId": 2}]
    assert "includeEpisode" not in radarr_route.calls.last.request.url.params
