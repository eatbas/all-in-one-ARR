"""Tests for Findarr's custom-format upgrade candidate discovery."""

from __future__ import annotations

from modules.findarr import custom_formats

_PROFILES = [
    {"id": 9, "upgradeAllowed": True, "cutoffFormatScore": 10000},
    {"id": 8, "upgradeAllowed": False, "cutoffFormatScore": 500},
    {"id": 7, "upgradeAllowed": True},
    {"upgradeAllowed": True, "cutoffFormatScore": 1},
]


class _StubClient:
    def __init__(
        self,
        *,
        series: list[dict] | None = None,
        episodes: dict[int, list[dict]] | None = None,
        movies: list[dict] | None = None,
        movie_files: list[dict] | None = None,
    ) -> None:
        self._series = series or []
        self._episodes = episodes or {}
        self._movies = movies or []
        self._movie_files = movie_files or []
        self.episode_requests: list[int] = []
        self.movie_file_requests: list[list[int]] = []

    async def quality_profiles(self) -> list[dict]:
        return _PROFILES

    async def series(self) -> list[dict]:
        return self._series

    async def episodes_with_files(self, series_id: int) -> list[dict]:
        self.episode_requests.append(series_id)
        return self._episodes.get(series_id, [])

    async def movies(self) -> list[dict]:
        return self._movies

    async def movie_files(self, movie_ids: list[int]) -> list[dict]:
        self.movie_file_requests.append(movie_ids)
        return self._movie_files


def _series(series_id: int, **overrides) -> dict:
    base = {
        "id": series_id,
        "title": f"Show {series_id}",
        "monitored": True,
        "qualityProfileId": 9,
        "statistics": {"episodeFileCount": 3},
    }
    base.update(overrides)
    return base


async def test_sonarr_records_return_episodes_below_the_format_cutoff() -> None:
    client = _StubClient(
        series=[
            _series(1),
            _series(2, monitored=False),
            _series(3, qualityProfileId=8),
            _series(4, statistics={"episodeFileCount": 0}),
            _series(5, qualityProfileId=None),
            {"title": "No id", "qualityProfileId": 9},
            _series(6, statistics=None),
        ],
        episodes={
            1: [
                {"id": 10, "episodeFile": {"customFormatScore": -10000}},
                {"id": 11, "episodeFile": {"customFormatScore": 10000}},
                {"id": 12, "episodeFile": None},
                {"id": 13, "episodeFile": {"customFormatScore": "n/a"}},
            ],
            6: [{"id": 60, "episodeFile": {"customFormatScore": 0}}],
        },
    )
    records = await custom_formats.records(client, "sonarr", monitored_only=True)
    assert [record["id"] for record in records] == [10, 60]
    # The series is embedded so the wanted-record normaliser can label it.
    assert records[0]["series"]["title"] == "Show 1"
    # Unmonitored, non-upgrading, file-less and id-less series are never read.
    assert client.episode_requests == [1, 6]


async def test_sonarr_records_include_unmonitored_series_when_allowed() -> None:
    client = _StubClient(
        series=[_series(2, monitored=False)],
        episodes={2: [{"id": 20, "episodeFile": {"customFormatScore": 5}}]},
    )
    records = await custom_formats.records(client, "sonarr", monitored_only=False)
    assert [record["id"] for record in records] == [20]


async def test_radarr_records_return_movies_below_the_format_cutoff() -> None:
    movies = [
        {
            "id": 1,
            "title": "Low",
            "hasFile": True,
            "monitored": True,
            "qualityProfileId": 9,
        },
        {
            "id": 2,
            "title": "High",
            "hasFile": True,
            "monitored": True,
            "qualityProfileId": 9,
        },
        {"id": 3, "title": "No file", "hasFile": False, "qualityProfileId": 9},
        {
            "id": 4,
            "title": "Unmonitored",
            "hasFile": True,
            "monitored": False,
            "qualityProfileId": 9,
        },
        {"id": 5, "title": "No upgrades", "hasFile": True, "qualityProfileId": 8},
    ]
    client = _StubClient(
        movies=movies,
        movie_files=[
            {"movieId": 1, "customFormatScore": 100},
            {"movieId": 2, "customFormatScore": 10000},
            {"movieId": 99, "customFormatScore": 0},
            {"customFormatScore": 0},
        ],
    )
    records = await custom_formats.records(client, "radarr", monitored_only=True)
    assert [record["title"] for record in records] == ["Low"]
    assert client.movie_file_requests == [[1, 2]]


async def test_radarr_records_skip_the_file_lookup_without_candidates() -> None:
    client = _StubClient(movies=[{"id": 3, "hasFile": False, "qualityProfileId": 9}])
    assert await custom_formats.records(client, "radarr", monitored_only=True) == []
    assert client.movie_file_requests == []
