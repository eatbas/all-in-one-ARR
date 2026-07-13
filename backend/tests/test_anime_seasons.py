"""Tests for the AniList season-dedup helpers."""

from __future__ import annotations

import pytest

from core.anime_seasons import dedupe_anilist_show_seasons, strip_season_marker


def _row(title, *, tvdb=None, tmdb=None, year=None, **extra):
    base = {
        "media_type": "show",
        "title": title,
        "tvdb": tvdb,
        "tmdb": tmdb,
        "year": year,
    }
    base.update(extra)
    return base


# ---- strip_season_marker ----


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Mushoku Tensei: Jobless Reincarnation Season 2 Part 2",
            "Mushoku Tensei: Jobless Reincarnation",
        ),
        ("My Hero Academia 4th Season: Rising Heroes", "My Hero Academia"),
        ("Monogatari Series: Second Season", "Monogatari Series"),
        ("Attack on Titan: The Final Season", "Attack on Titan"),
        ("Attack on Titan Final Season Part 2", "Attack on Titan"),
        ("Uma Musume: Pretty Derby Cour 3", "Uma Musume: Pretty Derby"),
        ("Golden Kamuy Part 2", "Golden Kamuy"),
    ],
)
def test_explicit_trailing_markers_are_stripped(title, expected) -> None:
    assert strip_season_marker(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "Mob Psycho 100",  # bare trailing digits are not a marker
        "Hunter x Hunter (2011)",
        "From Old Country Bumpkin to Master Swordsman II",  # Roman numerals
        "That Time I Got Reincarnated as a Slime",
        "Part 2 Forever After",  # a bare part marker only counts end-anchored
    ],
)
def test_non_marker_titles_are_untouched(title) -> None:
    assert strip_season_marker(title) == title


def test_a_title_that_is_only_a_marker_is_kept() -> None:
    # Stripping would leave nothing, so the original title survives — both in
    # the helper and through a dedupe pass.
    assert strip_season_marker("Final Season") == "Final Season"
    result = dedupe_anilist_show_seasons([_row("Season 2")])
    assert result[0]["title"] == "Season 2"


# ---- dedupe_anilist_show_seasons ----


def test_mapped_season_rows_collapse_to_base_row_at_best_rank() -> None:
    # Seasons of one series share Fribb's series-level ids after enrichment;
    # the base entry survives at the group's earliest feed position.
    rows = [
        _row(
            "Mushoku Tensei: Jobless Reincarnation Season 2",
            tvdb=371310,
            tmdb=94664,
            year=2023,
        ),
        _row("Solo Leveling", tvdb=389343, year=2024),
        _row(
            "Mushoku Tensei: Jobless Reincarnation",
            tvdb=371310,
            tmdb=94664,
            year=2021,
        ),
        _row(
            "Mushoku Tensei: Jobless Reincarnation Season 2 Part 2",
            tvdb=371310,
            tmdb=94664,
            year=2024,
        ),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == [
        "Mushoku Tensei: Jobless Reincarnation",
        "Solo Leveling",
    ]
    # The base entry needs no title strip, so the input row itself is emitted.
    assert result[0] is rows[2]


def test_grouping_falls_back_to_tmdb_when_tvdb_is_absent() -> None:
    rows = [
        _row("Frieren: Beyond Journey's End Season 2", tmdb=209867, year=2026),
        _row("Frieren: Beyond Journey's End", tmdb=209867, year=2023),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == ["Frieren: Beyond Journey's End"]


def test_tvdb_takes_precedence_over_tmdb() -> None:
    # Rows sharing a tvdb id group together even when their tmdb ids differ.
    rows = [
        _row("Dandadan", tvdb=422580, tmdb=240411, year=2024),
        _row("Dandadan Season 2", tvdb=422580, tmdb=999999, year=2025),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == ["Dandadan"]


def test_unmapped_season_row_adopts_its_mapped_base_group() -> None:
    # The unmapped season row precedes its mapped base row, as observed in the
    # live anilist/show/popular snapshot ("You and I Are Polar Opposites").
    rows = [
        _row("You and I Are Polar Opposites Season 2", year=2026),
        _row("You and I Are Polar Opposites", tvdb=457078, year=2024),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert len(result) == 1
    assert result[0]["title"] == "You and I Are Polar Opposites"
    assert result[0]["tvdb"] == 457078


def test_unmapped_rows_group_by_stripped_title_alone() -> None:
    rows = [
        _row("Clevatess Season 2", year=2026),
        _row("Clevatess", year=2025),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == ["Clevatess"]


def test_lone_season_row_survives_with_a_stripped_title_copy() -> None:
    # A season-only group keeps one representative whose displayed title loses
    # the marker; the stored input row is never mutated.
    season_only = _row(
        "HELL MODE: A Hardcore Gamer Season 2",
        year=2026,
        anilist=185407,
        poster_url="https://img.anili.st/cover.jpg",
    )
    result = dedupe_anilist_show_seasons([season_only])
    assert result[0]["title"] == "HELL MODE: A Hardcore Gamer"
    assert result[0] is not season_only
    assert result[0]["poster_url"] == "https://img.anili.st/cover.jpg"
    assert season_only["title"] == "HELL MODE: A Hardcore Gamer Season 2"


def test_roman_numeral_sequel_without_shared_ids_stays_separate() -> None:
    # Roman numerals are not season markers, so unmapped sequels keep their
    # own cards; the mapped ones collapse via shared ids instead.
    rows = [
        _row("Grand Blue Dreaming"),
        _row("Grand Blue Dreaming II"),
    ]
    assert dedupe_anilist_show_seasons(rows) == rows


def test_roman_numeral_sequel_with_shared_ids_collapses_to_earliest_year() -> None:
    # Both titles are unmarked, so the earlier year picks the clean base row.
    rows = [
        _row(
            "From Old Country Bumpkin to Master Swordsman II",
            tvdb=452710,
            year=2026,
        ),
        _row("From Old Country Bumpkin to Master Swordsman", tvdb=452710, year=2025),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == [
        "From Old Country Bumpkin to Master Swordsman"
    ]


def test_year_none_orders_last_and_feed_index_breaks_ties() -> None:
    # Every title is marked: a missing year loses to any real one, the two
    # 2025 rows tie on year and the earlier feed index wins, and the
    # survivor's displayed title is emitted stripped.
    rows = [
        _row("Kaiju No. 8 Season 2", tvdb=428771, year=None),
        _row("Kaiju No. 8 Cour 2", tvdb=428771, year=2025),
        _row("Kaiju No. 8 Part 2", tvdb=428771, year=2025),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == ["Kaiju No. 8"]
    assert result[0]["year"] == 2025
    assert rows[1]["title"] == "Kaiju No. 8 Cour 2"


def test_rows_without_ids_or_titles_pass_through_untouched() -> None:
    rows = [
        _row(None, tvdb=452710),  # mapped but untitled: cannot seed adoption
        _row(None),
        _row("   "),  # normalises to nothing: no usable title either
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert result == rows
    assert result[0] is rows[0]


def test_bool_ids_and_years_are_ignored() -> None:
    # Defensive: bools subclass int but are never ids or years, so neither row
    # gets an id key — they group by base title and the unmarked row wins.
    rows = [
        _row("Ranma 1/2 Season 2", tvdb=True, tmdb=True, year=True),
        _row("Ranma 1/2", tvdb=False, tmdb=False, year=2024),
    ]
    result = dedupe_anilist_show_seasons(rows)
    assert [row["title"] for row in result] == ["Ranma 1/2"]


def test_dedupe_is_idempotent() -> None:
    rows = [
        _row("Oshi no Ko Season 2", tvdb=417909, year=2024),
        _row("Oshi no Ko", tvdb=417909, year=2023),
        _row("Clevatess Season 2", year=2026),
    ]
    once = dedupe_anilist_show_seasons(rows)
    assert dedupe_anilist_show_seasons(once) == once
