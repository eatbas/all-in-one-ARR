"""Season-level dedup for the AniList show feeds.

AniList models every season, cour and part of a series as a separate media
entry, so the trending/popular show grids render the same series repeatedly
("Mushoku Tensei … Season 2", "… Season 2 Part 2", "… Cour 2"). Fribb's
mapping (:mod:`core.anime_ids`) assigns *series-level* TVDB/TMDB ids, so
seasons of one series share ids after enrichment; grouping by those ids
collapses the mapped duplicates without any title parsing. Unmapped season
rows fall back to a conservative title heuristic: only explicit trailing
markers are recognised — bare digits ("Mob Psycho 100") and Roman numerals
("… II") are never treated as season markers.

Applied to the ``anilist``/``show`` feeds only. Movies are excluded on
purpose: distinct films of a franchise can share a series-level id in Fribb's
mapping, so id-grouping would wrongly merge them. Every function here is pure
— input rows are never mutated (they are shared with ``ctx.trending_store``)
— and :func:`dedupe_anilist_show_seasons` is idempotent, so it is safe to
apply at both the fetch and the read pipeline points.
"""

from __future__ import annotations

import re
from typing import Any

# Explicit trailing season markers only. The season/cour forms may trail a
# part number or subtitle ("Season 2 Part 2", "4th Season: …"); a bare part
# marker must end the title so a mid-title "Part" is never clipped. Bare
# trailing digits and Roman numerals are deliberately not markers — the
# mapped sequels they name collapse via shared ids instead.
_SEASON_MARKER = re.compile(
    r"""
    (?: ^ | [\s:\-–—]+ )            # start of title, or a separator run
    (?:
        (?:
            season\s+\d+
          | \d+(?:st|nd|rd|th)\s+season
          | (?:first|second|third|fourth|fifth)\s+season
          | (?:the\s+)?final\s+season
          | cour\s+\d+
        )
        (?: [\s:\-–—] .* )?         # optional part number or subtitle tail
      | part\s+\d+                  # bare part marker, end-anchored only
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_season_marker(title: str) -> str:
    """Return ``title`` with a trailing season marker removed (trimmed).

    The original title is returned when no marker matches, or when the strip
    would leave nothing (a title that is nothing but a marker).
    """
    match = _SEASON_MARKER.search(title)
    if match is None:
        return title
    stripped = title[: match.start()].strip()
    return stripped if stripped else title


def _normalise(title: str) -> str:
    """Casefold and collapse whitespace, for title-based group matching."""
    return " ".join(title.casefold().split())


def _valid_int(value: Any) -> int | None:
    """Return ``value`` when it is a usable int (``bool`` excluded)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _series_id_key(row: dict[str, Any]) -> tuple[str, int] | None:
    """Return the row's series-level id grouping key, preferring TVDB."""
    tvdb = _valid_int(row.get("tvdb"))
    if tvdb is not None:
        return ("tvdb", tvdb)
    tmdb = _valid_int(row.get("tmdb"))
    if tmdb is not None:
        return ("tmdb", tmdb)
    return None


def _base_title(row: dict[str, Any]) -> str | None:
    """Return the row's normalised, marker-stripped title, or ``None``."""
    title = row.get("title")
    if not isinstance(title, str):
        return None
    return _normalise(strip_season_marker(title)) or None


def _representative(members: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    """Pick the row that should represent one season group.

    An unmarked (base) title beats marked ones, an earlier year beats a later
    or missing one, and the feed position breaks any remaining tie.
    """

    def sort_key(member: tuple[int, dict[str, Any]]) -> tuple[bool, bool, int, int]:
        index, row = member
        title = row.get("title")
        marked = isinstance(title, str) and _SEASON_MARKER.search(title) is not None
        year = _valid_int(row.get("year"))
        return (marked, year is None, year if year is not None else 0, index)

    return min(members, key=sort_key)[1]


def dedupe_anilist_show_seasons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-season AniList show rows to one row per series.

    Rows sharing a series-level TVDB/TMDB id form one group; an unmapped row
    whose marker-stripped title matches a mapped row's adopts that row's
    group, remaining unmapped rows group by stripped title alone, and rows
    with neither ids nor a usable title pass through untouched. Each group
    keeps a single representative — the base entry when present — at the
    group's best (earliest) feed position, and a surviving season-marked
    title is emitted as a *copy* with the marker stripped; input rows are
    never mutated.
    """
    # Pass 1: record the first id key seen per base title, so an unmapped
    # season row adopts its mapped base row's group regardless of feed order.
    adopted_id_keys: dict[str, tuple[str, int]] = {}
    for row in rows:
        id_key = _series_id_key(row)
        if id_key is None:
            continue
        base_title = _base_title(row)
        if base_title is not None and base_title not in adopted_id_keys:
            adopted_id_keys[base_title] = id_key

    # Pass 2: group in feed order; dict insertion order pins each group to
    # its first occurrence, i.e. the group's best trending rank.
    groups: dict[object, list[tuple[int, dict[str, Any]]]] = {}
    for index, row in enumerate(rows):
        base_title = _base_title(row)
        key: object = _series_id_key(row)
        if key is None and base_title is not None:
            key = adopted_id_keys.get(base_title)
        if key is None:
            key = ("title", base_title) if base_title is not None else ("row", index)
        groups.setdefault(key, []).append((index, row))

    result: list[dict[str, Any]] = []
    for members in groups.values():
        row = _representative(members)
        title = row.get("title")
        if isinstance(title, str):
            stripped = strip_season_marker(title)
            if stripped != title:
                row = {**row, "title": stripped}
        result.append(row)
    return result
