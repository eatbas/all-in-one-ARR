"""Tests for the Trending API router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import trending as trending_mod
from core.context import SyncAlreadyRunning
from core.settings_store import TrackedList
from core.trending import SEER_TRENDING_SYNC_PAGES
from core.trending_api import create_trending_router, fetch_feed
from tests.conftest import make_ctx


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_trending_router(ctx))
    return TestClient(app)


def _row(media_type="movie", tmdb=100, **extra):
    base = {"media_type": media_type, "tmdb": tmdb, "title": "X", "year": 2021}
    base.update(extra)
    return base


# ---- GET /api/trending: source/category dispatch ----


def test_trakt_trending_and_popular(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(imdb="tt1", tvdb=None, trakt=1)]
    ctx.trakt.get_popular.return_value = [_row(tmdb=101)]
    client = build_client(ctx)

    trending = client.get(
        "/api/trending",
        params={"source": "trakt", "media": "movie", "category": "trending"},
    ).json()
    assert trending[0]["source"] == "trakt"
    assert trending[0]["imdb"] == "tt1"
    assert trending[0]["already_tracked"] is False

    popular = client.get(
        "/api/trending", params={"source": "trakt", "category": "popular"}
    ).json()
    assert popular[0]["tmdb"] == 101


def test_tmdb_trending_and_popular(db) -> None:
    ctx = make_ctx(db=db)
    ctx.tmdb.get_trending.return_value = [_row(tmdb=200)]
    ctx.tmdb.get_popular.return_value = [_row(tmdb=201)]
    client = build_client(ctx)

    trending = client.get(
        "/api/trending",
        params={
            "source": "tmdb",
            "media": "movie",
            "category": "trending",
            "window": "day",
        },
    ).json()
    assert trending[0]["tmdb"] == 200
    ctx.tmdb.get_trending.assert_awaited_once()
    assert ctx.tmdb.get_trending.await_args.kwargs["window"] == "day"

    popular = client.get(
        "/api/trending", params={"source": "tmdb", "category": "popular"}
    ).json()
    assert popular[0]["tmdb"] == 201


def test_seer_trending_filters_to_requested_media(db) -> None:
    ctx = make_ctx(db=db)
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": [_row(media_type="movie", tmdb=300, seer_status=5)],
        "show": [_row(media_type="show", tmdb=301)],
    }
    client = build_client(ctx)
    result = client.get(
        "/api/trending",
        params={"source": "seer", "media": "movie", "category": "trending"},
    ).json()
    assert [item["tmdb"] for item in result] == [300]
    assert result[0]["seer_status"] == 5


async def test_seer_trending_fetch_uses_bucket_helper_for_requested_media(db) -> None:
    ctx = make_ctx(db=db)
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": [
            _row(media_type="movie", tmdb=300),
            _row(media_type="movie", tmdb=301),
        ],
        "show": [_row(media_type="show", tmdb=400)],
    }

    rows = await fetch_feed(
        ctx,
        source="seer",
        media="movie",
        category="trending",
        window="week",
        limit=2,
        pages=1,
    )

    assert [row["tmdb"] for row in rows] == [300, 301]
    ctx.seer.discover_trending_buckets.assert_awaited_once_with(
        limit_per_media=2,
        pages=SEER_TRENDING_SYNC_PAGES,
    )


def test_seer_popular(db) -> None:
    ctx = make_ctx(db=db)
    ctx.seer.discover_popular.return_value = [_row(media_type="show", tmdb=400)]
    client = build_client(ctx)
    result = client.get(
        "/api/trending",
        params={"source": "seer", "media": "show", "category": "popular"},
    ).json()
    assert result[0]["tmdb"] == 400


def test_trakt_anime_forwards_genre_filter(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(media_type="show", tmdb=500)]
    ctx.trakt.get_popular.return_value = [_row(media_type="show", tmdb=501)]
    client = build_client(ctx)

    trending = client.get(
        "/api/trending",
        params={"source": "trakt-anime", "media": "show", "category": "trending"},
    ).json()
    assert trending[0]["source"] == "trakt-anime"
    assert trending[0]["tmdb"] == 500
    assert ctx.trakt.get_trending.await_args.kwargs["genres"] == "anime"

    popular = client.get(
        "/api/trending",
        params={"source": "trakt-anime", "media": "show", "category": "popular"},
    ).json()
    assert popular[0]["tmdb"] == 501
    assert ctx.trakt.get_popular.await_args.kwargs["genres"] == "anime"


def test_tmdb_anime_dispatches_to_discover_methods(db) -> None:
    ctx = make_ctx(db=db)
    ctx.tmdb.get_anime_trending.return_value = [_row(media_type="show", tmdb=600)]
    ctx.tmdb.get_anime_popular.return_value = [_row(media_type="show", tmdb=601)]
    client = build_client(ctx)

    trending = client.get(
        "/api/trending",
        params={"source": "tmdb-anime", "media": "show", "category": "trending"},
    ).json()
    assert trending[0]["tmdb"] == 600
    ctx.tmdb.get_anime_trending.assert_awaited_once()

    popular = client.get(
        "/api/trending",
        params={"source": "tmdb-anime", "media": "show", "category": "popular"},
    ).json()
    assert popular[0]["tmdb"] == 601
    ctx.tmdb.get_anime_popular.assert_awaited_once()


def test_anilist_rows_are_enriched_and_carry_anime_fields(db) -> None:
    ctx = make_ctx(db=db)
    ctx.anilist.get_trending.return_value = [
        {
            "media_type": "show",
            "anilist": 195600,
            "mal": 62001,
            "title": "Daemons of the Shadow Realm",
            "year": 2026,
            "poster_url": "https://img.anili.st/cover.jpg",
        }
    ]

    async def _fill(rows):
        for row in rows:
            row["tmdb"] = 42
            row["tvdb"] = 4242
        return rows

    ctx.anime_ids.enrich.side_effect = _fill
    client = build_client(ctx)

    result = client.get(
        "/api/trending",
        params={"source": "anilist", "media": "show", "category": "trending"},
    ).json()
    assert result[0]["source"] == "anilist"
    assert result[0]["anilist"] == 195600
    assert result[0]["poster_url"] == "https://img.anili.st/cover.jpg"
    assert result[0]["tmdb"] == 42
    assert result[0]["tvdb"] == 4242
    ctx.anime_ids.enrich.assert_awaited_once()


def test_anilist_without_id_map_serves_unenriched_rows(db) -> None:
    ctx = make_ctx(db=db)
    ctx.anime_ids = None
    ctx.anilist.get_popular.return_value = [
        {"media_type": "show", "anilist": 1, "title": "X", "year": 2026}
    ]
    client = build_client(ctx)
    result = client.get(
        "/api/trending",
        params={"source": "anilist", "media": "show", "category": "popular"},
    ).json()
    assert result[0]["anilist"] == 1
    assert result[0]["tmdb"] is None


def test_already_tracked_reflects_db(db) -> None:
    # One item with a TMDB id and one without, to exercise both filter branches.
    db.upsert_item(
        trakt_id=1,
        type="movie",
        title="Tracked",
        year=2020,
        tmdb=100,
        tvdb=None,
        imdb=None,
        list_id="my-list",
    )
    db.upsert_item(
        trakt_id=2,
        type="movie",
        title="NoTmdb",
        year=2020,
        tmdb=None,
        tvdb=None,
        imdb=None,
        list_id="my-list",
    )
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(tmdb=100), _row(tmdb=999)]
    client = build_client(ctx)
    result = client.get(
        "/api/trending", params={"source": "trakt", "category": "trending"}
    ).json()
    assert {item["tmdb"]: item["already_tracked"] for item in result} == {
        100: True,
        999: False,
    }


def test_removed_items_are_not_tracked(db) -> None:
    db.upsert_item(
        trakt_id=1,
        type="movie",
        title="Gone",
        year=2020,
        tmdb=100,
        tvdb=None,
        imdb=None,
        list_id="my-list",
    )
    db.set_status(trakt_id=1, list_id="my-list", status="removed")
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(tmdb=100)]
    result = (
        build_client(ctx)
        .get("/api/trending", params={"source": "trakt", "category": "trending"})
        .json()
    )
    assert result[0]["already_tracked"] is False


def test_in_library_flags_radarr_movie_and_sonarr_show(db) -> None:
    ctx = make_ctx(db=db)
    ctx.radarr.library_items.return_value = [{"tmdbId": 100}]
    ctx.sonarr.library_items.return_value = [{"tvdbId": 300, "tmdbId": 555}]
    ctx.trakt.get_trending.return_value = [_row(tmdb=100), _row(tmdb=999)]
    movies = (
        build_client(ctx)
        .get(
            "/api/trending",
            params={"source": "trakt", "media": "movie", "category": "trending"},
        )
        .json()
    )
    assert {m["tmdb"]: m["in_library"] for m in movies} == {100: True, 999: False}

    ctx.trakt.get_trending.return_value = [
        _row(media_type="show", tmdb=1, tvdb=300),  # in Sonarr by tvdb
        _row(media_type="show", tmdb=555, tvdb=None),  # in Sonarr by tmdb
        _row(media_type="show", tmdb=7, tvdb=8),  # not in Sonarr
    ]
    shows = (
        build_client(ctx)
        .get(
            "/api/trending",
            params={"source": "trakt", "media": "show", "category": "trending"},
        )
        .json()
    )
    assert [s["in_library"] for s in shows] == [True, True, False]


def test_in_library_available_reflects_download_state(db) -> None:
    # 100 is downloaded (hasFile); 200 has a Radarr record but no file yet; 999 absent.
    ctx = make_ctx(db=db)
    ctx.radarr.library_items.return_value = [
        {"tmdbId": 100, "hasFile": True},
        {"tmdbId": 200, "hasFile": False},
    ]
    ctx.trakt.get_trending.return_value = [
        _row(tmdb=100),
        _row(tmdb=200),
        _row(tmdb=999),
    ]
    movies = (
        build_client(ctx)
        .get(
            "/api/trending",
            params={"source": "trakt", "media": "movie", "category": "trending"},
        )
        .json()
    )
    flags = {m["tmdb"]: (m["in_library"], m["in_library_available"]) for m in movies}
    assert flags == {100: (True, True), 200: (True, False), 999: (False, False)}


def test_in_library_uses_cache_within_ttl(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(tmdb=100)]
    client = build_client(ctx)
    client.get("/api/trending", params={"source": "trakt", "category": "trending"})
    client.get("/api/trending", params={"source": "trakt", "category": "trending"})
    # The library index is cached, so each Arr library is listed only once.
    assert ctx.radarr.library_items.await_count == 1
    assert ctx.sonarr.library_items.await_count == 1


def test_fetch_error_degrades_to_empty_list(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.side_effect = RuntimeError("trakt down")
    client = build_client(ctx)
    response = client.get(
        "/api/trending", params={"source": "trakt", "category": "trending"}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_invalid_source_is_422(db) -> None:
    response = build_client(make_ctx(db=db)).get(
        "/api/trending", params={"source": "imdb"}
    )
    assert response.status_code == 422


def test_get_trending_serves_warm_store_without_fetching(db) -> None:
    # A feed kept warm by the scheduler is served from the store; no provider call.
    ctx = make_ctx(db=db)
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(tmdb=100)],
    )
    result = (
        build_client(ctx)
        .get("/api/trending", params={"source": "trakt", "category": "trending"})
        .json()
    )
    assert [item["tmdb"] for item in result] == [100]
    ctx.trakt.get_trending.assert_not_awaited()


def test_get_trending_caches_cold_fetch_in_store(db) -> None:
    # A cold feed is fetched live once, then served from the store on the next read.
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(tmdb=100)]
    client = build_client(ctx)
    client.get("/api/trending", params={"source": "trakt", "category": "trending"})
    client.get("/api/trending", params={"source": "trakt", "category": "trending"})
    ctx.trakt.get_trending.assert_awaited_once()


def test_get_trending_uses_stale_library_index_while_refreshing(
    db, monkeypatch
) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(trending_mod, "_now", lambda: clock["now"])
    ctx = make_ctx(db=db)
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(tmdb=100)],
    )
    ctx.radarr.library_items.return_value = [{"tmdbId": 100, "hasFile": True}]
    ctx.sonarr.library_items.side_effect = RuntimeError("sonarr down")
    client = build_client(ctx)

    first = client.get(
        "/api/trending", params={"source": "trakt", "category": "trending"}
    ).json()
    assert first[0]["in_library"] is True
    assert first[0]["in_library_available"] is True

    clock["now"] = 1061.0
    ctx.radarr.library_items.side_effect = RuntimeError("radarr down")
    second = client.get(
        "/api/trending", params={"source": "trakt", "category": "trending"}
    ).json()
    assert second[0]["in_library"] is True
    assert second[0]["in_library_available"] is True


# ---- GET /api/trending/status ----


def test_trending_status_before_first_sync(db) -> None:
    body = build_client(make_ctx(db=db)).get("/api/trending/status").json()
    assert body == {
        "last_synced_at": None,
        "interval_minutes": 1440,
        "next_sync_at": None,
    }


def test_trending_status_after_sync_derives_next(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trending_store.mark_synced("2026-06-30T12:00:00+00:00")
    body = build_client(ctx).get("/api/trending/status").json()
    assert body["last_synced_at"] == "2026-06-30T12:00:00+00:00"
    assert body["interval_minutes"] == 1440
    assert body["next_sync_at"] == "2026-07-01T12:00:00+00:00"


# ---- rating overlay on GET /api/trending ----


def test_get_trending_embeds_stored_ratings(db) -> None:
    db.trending_ratings_upsert(key="tt1", imdb_rating=8.6, imdb_votes=100)
    db.trending_ratings_upsert(key="movie:101", imdb_rating=7.2, imdb_votes=50)
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [
        _row(tmdb=100, imdb="tt1"),  # rated via its IMDb key
        _row(tmdb=101),  # rated via the media:tmdb alias
        _row(tmdb=102),  # not yet backfilled
    ]
    result = (
        build_client(ctx)
        .get("/api/trending", params={"source": "trakt", "category": "trending"})
        .json()
    )
    assert [item["imdb_rating"] for item in result] == [8.6, 7.2, None]
    # The overlay is a local read; no upstream rating traffic on the request path.
    ctx.omdb.fetch_rating.assert_not_awaited()


# ---- GET /api/trending/rating (compat shim, served from the DB store) ----


def test_rating_by_imdb_served_from_store(db) -> None:
    db.trending_ratings_upsert(key="tt1", imdb_rating=8.6, imdb_votes=100)
    ctx = make_ctx(db=db)
    result = (
        build_client(ctx).get("/api/trending/rating", params={"imdb": "tt1"}).json()
    )
    assert result == {"imdb_rating": 8.6, "imdb_votes": 100}
    # The route never calls upstream; the backfill owns OMDb/TMDB traffic.
    ctx.omdb.fetch_rating.assert_not_awaited()
    ctx.tmdb.fetch_external_ids.assert_not_awaited()


def test_rating_by_tmdb_served_from_alias_key(db) -> None:
    db.trending_ratings_upsert(key="movie:603", imdb_rating=7.1, imdb_votes=5)
    ctx = make_ctx(db=db)
    result = (
        build_client(ctx)
        .get("/api/trending/rating", params={"media": "movie", "tmdb": 603})
        .json()
    )
    assert result == {"imdb_rating": 7.1, "imdb_votes": 5}
    ctx.tmdb.fetch_external_ids.assert_not_awaited()


def test_rating_miss_returns_nulls_without_upstream_calls(db) -> None:
    ctx = make_ctx(db=db)
    result = (
        build_client(ctx)
        .get("/api/trending/rating", params={"media": "movie", "tmdb": 603})
        .json()
    )
    assert result == {"imdb_rating": None, "imdb_votes": None}
    ctx.omdb.fetch_rating.assert_not_awaited()
    ctx.tmdb.fetch_external_ids.assert_not_awaited()


def test_rating_without_any_id_returns_nulls(db) -> None:
    ctx = make_ctx(db=db)
    result = build_client(ctx).get("/api/trending/rating").json()
    assert result == {"imdb_rating": None, "imdb_votes": None}
    ctx.omdb.fetch_rating.assert_not_awaited()


# ---- POST /api/trending/add ----


def _owned_ctx(db, **kwargs):
    store_lists = [TrackedList(owner_user="me", slug="my-list", name="My List")]
    from tests.conftest import StubSettingsStore

    return make_ctx(
        db=db, settings_store=StubSettingsStore(lists=store_lists), **kwargs
    )


def test_add_movie_triggers_sync(db) -> None:
    ctx = _owned_ctx(db)
    ran = {"sync": False}

    async def sync_now():
        ran["sync"] = True

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
            "title": "Dune",
        },
    )
    assert response.json() == {"status": "added"}
    assert ran["sync"] is True
    ctx.trakt.add_items.assert_awaited_once()
    # No trakt id in the body, so the tmdb id is resolved to one before the add.
    ctx.trakt.lookup_ids.assert_awaited_once()
    assert ctx.trakt.add_items.await_args.kwargs["movies"] == [
        {"trakt": 500, "tmdb": 100}
    ]


def test_add_resolves_tmdb_only_item(db) -> None:
    # A TMDB/Seer-tab card carries only a tmdb id; it must still be added.
    ctx = _owned_ctx(db)

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
        },
    )
    assert response.json() == {"status": "added"}
    assert ctx.trakt.add_items.await_args.kwargs["movies"] == [
        {"trakt": 500, "tmdb": 100}
    ]


def test_add_skips_lookup_when_trakt_id_present(db) -> None:
    # Trakt-tab cards already carry a trakt id, so no lookup is needed.
    ctx = _owned_ctx(db)

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
            "trakt": 7,
        },
    )
    assert response.json() == {"status": "added"}
    ctx.trakt.lookup_ids.assert_not_awaited()
    assert ctx.trakt.add_items.await_args.kwargs["movies"] == [
        {"trakt": 7, "tmdb": 100}
    ]


def test_add_resolves_via_imdb_when_tmdb_absent(db) -> None:
    # An anime-shaped payload (Fribb mapping filled imdb/tvdb but no tmdb)
    # resolves through the IMDb lookup — the first usable candidate.
    ctx = _owned_ctx(db)
    ctx.trakt.lookup_ids.return_value = {"trakt": 42, "imdb": "tt5", "tvdb": 77}

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "show",
            "owner_user": "me",
            "slug": "my-list",
            "imdb": "tt5",
            "tvdb": 77,
        },
    )
    assert response.json() == {"status": "added"}
    ctx.trakt.lookup_ids.assert_awaited_once_with(
        id_type="imdb", id_value="tt5", media_type="show"
    )
    assert ctx.trakt.add_items.await_args.kwargs["shows"] == [
        {"trakt": 42, "imdb": "tt5", "tvdb": 77}
    ]


def test_add_falls_back_to_tvdb_for_shows(db) -> None:
    # With only a tvdb id available, a show still resolves via the TVDB lookup.
    ctx = _owned_ctx(db)
    ctx.trakt.lookup_ids.return_value = {"trakt": 43, "tvdb": 88}

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "show",
            "owner_user": "me",
            "slug": "my-list",
            "tvdb": 88,
        },
    )
    assert response.json() == {"status": "added"}
    ctx.trakt.lookup_ids.assert_awaited_once_with(
        id_type="tvdb", id_value=88, media_type="show"
    )


def test_add_movie_never_attempts_tvdb_lookup(db) -> None:
    # Trakt does not index movies by TVDB id: a movie with only a tvdb id has
    # no resolvable candidate and must fail fast without any lookup or add.
    ctx = _owned_ctx(db)
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tvdb": 88,
            "title": "Odd Movie",
        },
    )
    assert response.status_code == 502
    assert "Odd Movie" in response.json()["detail"]
    ctx.trakt.lookup_ids.assert_not_awaited()
    ctx.trakt.add_items.assert_not_awaited()


def test_add_lookup_failure_tries_next_candidate(db) -> None:
    # The tmdb lookup dying must not abort resolution: the imdb candidate is
    # tried next and its trakt id carries the add.
    ctx = _owned_ctx(db)
    ctx.trakt.lookup_ids.side_effect = [
        RuntimeError("search down"),
        {"trakt": 44, "imdb": "tt6"},
    ]

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
            "imdb": "tt6",
        },
    )
    assert response.json() == {"status": "added"}
    assert ctx.trakt.lookup_ids.await_count == 2
    assert ctx.trakt.add_items.await_args.kwargs["movies"] == [
        {"trakt": 44, "imdb": "tt6", "tmdb": 100}
    ]


def test_add_trakt_less_resolution_tries_next_candidate(db) -> None:
    # A lookup that answers without a trakt id is a miss, not a success.
    ctx = _owned_ctx(db)
    ctx.trakt.lookup_ids.side_effect = [
        {"tmdb": 100},  # no trakt id: keep looking
        {"trakt": 45, "imdb": "tt7"},
    ]

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
            "imdb": "tt7",
        },
    )
    assert response.json() == {"status": "added"}
    assert ctx.trakt.lookup_ids.await_count == 2


def test_add_unresolvable_trakt_id_fails_fast(db) -> None:
    # Every add must post a trakt id: when no candidate resolves one, the add
    # fails with a title-naming detail and nothing is posted to the list.
    ctx = _owned_ctx(db)
    ctx.trakt.lookup_ids.return_value = None

    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
            "title": "Ghost Film",
        },
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Could not resolve a Trakt id for Ghost Film"
    ctx.trakt.add_items.assert_not_awaited()


def test_add_not_found_is_502(db) -> None:
    # Trakt returns 201 even when nothing resolved; a no-op add must surface as 502.
    ctx = _owned_ctx(db)
    ctx.trakt.add_items.return_value = {
        "added": {"movies": 0},
        "not_found": {"movies": [{"ids": {"tmdb": 100}}]},
    }
    ran = {"sync": False}

    async def sync_now():
        ran["sync"] = True

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
        },
    )
    assert response.status_code == 502
    assert "could not find" in response.json()["detail"].lower()
    assert ran["sync"] is False


def test_add_show_with_all_ids(db) -> None:
    ctx = _owned_ctx(db)

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "show",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 200,
            "imdb": "tt9",
            "trakt": 7,
            "tvdb": 42,
        },
    )
    assert response.json() == {"status": "added"}
    assert ctx.trakt.add_items.await_args.kwargs["shows"] == [
        {"trakt": 7, "imdb": "tt9", "tvdb": 42, "tmdb": 200}
    ]


def test_add_without_sync_callable(db) -> None:
    ctx = _owned_ctx(db)
    ctx.sync_now = None
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
        },
    )
    assert response.json() == {"status": "added"}


def test_add_pending_when_sync_already_running(db) -> None:
    ctx = _owned_ctx(db)

    class _BusyGate:
        async def try_run(self, _factory):
            raise SyncAlreadyRunning()

    ctx.sync_gate = _BusyGate()

    async def sync_now():
        return None

    ctx.sync_now = sync_now
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
        },
    )
    assert response.json() == {"status": "added_pending_sync"}


def test_add_to_unknown_list_is_404(db) -> None:
    ctx = _owned_ctx(db)
    response = build_client(ctx).post(
        "/api/trending/add",
        json={"media_type": "movie", "owner_user": "me", "slug": "ghost", "tmdb": 100},
    )
    assert response.status_code == 404


def test_add_to_watchlist_is_rejected(db) -> None:
    from tests.conftest import StubSettingsStore

    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            lists=[TrackedList(owner_user="me", slug="watchlist", name="watchlist")]
        ),
    )
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "watchlist",
            "tmdb": 100,
        },
    )
    assert response.status_code == 404


def test_add_without_usable_id_is_422(db) -> None:
    ctx = _owned_ctx(db)
    response = build_client(ctx).post(
        "/api/trending/add",
        json={"media_type": "movie", "owner_user": "me", "slug": "my-list"},
    )
    assert response.status_code == 422


def test_add_trakt_failure_is_502(db) -> None:
    ctx = _owned_ctx(db)
    ctx.trakt.add_items.side_effect = RuntimeError("trakt rejected")
    response = build_client(ctx).post(
        "/api/trending/add",
        json={
            "media_type": "movie",
            "owner_user": "me",
            "slug": "my-list",
            "tmdb": 100,
        },
    )
    assert response.status_code == 502
    assert "trakt rejected" in response.json()["detail"]
