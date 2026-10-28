"""Pure Cleanarr decision rules: strike reasons, patterns, ignores and the cap.

Nothing here performs I/O, so every rule is table-testable in isolation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any, Literal

from modules.cleanarr.models import QueueItem

StrikeReason = Literal["failed_import", "failed_download"]

# ``trackedDownloadState`` values (lower-cased) that mean the Arr could not
# import a completed download, or that the download itself failed.
_IMPORT_FAILED_STATES = frozenset({"importblocked", "importfailed"})
_DOWNLOAD_FAILED_STATES = frozenset({"failedpending", "failed"})


def classify(
    item: QueueItem, failed_sab_ids: frozenset[str] | None
) -> StrikeReason | None:
    """Return why ``item`` deserves a strike, or ``None`` when it is healthy.

    Only usenet items are considered. ``failed_download`` wins over
    ``failed_import``. When ``failed_sab_ids`` is ``None`` (SABnzbd history
    unavailable) only the Arr's own failed states count as failed downloads.
    """
    if item.protocol != "usenet":
        return None
    state = item.tracked_state.lower()
    if state in _DOWNLOAD_FAILED_STATES or (
        failed_sab_ids is not None and item.download_id in failed_sab_ids
    ):
        return "failed_download"
    if state in _IMPORT_FAILED_STATES or (
        state == "importpending" and item.tracked_status == "warning"
    ):
        return "failed_import"
    return None


def matches_any_pattern(item: QueueItem, patterns: Iterable[str]) -> bool:
    """Return whether a pattern is a case-insensitive substring of a message or title."""
    texts = [text.casefold() for text in (*item.messages, item.title)]
    return any(
        pattern.casefold() in text for pattern in patterns if pattern for text in texts
    )


def import_failure_counts(item: QueueItem, *, mode: str, patterns: list[str]) -> bool:
    """Return whether a failed import earns a strike under the pattern mode.

    In ``exclude`` mode a match exempts the item; in ``include`` mode only a
    match earns a strike.
    """
    return import_failures_count((item,), mode=mode, patterns=patterns)


def import_failures_count(
    items: Iterable[QueueItem], *, mode: str, patterns: list[str]
) -> bool:
    """Return whether the failed-import records of one download earn a strike.

    A pattern matching any record counts for the whole download: in
    ``exclude`` mode it exempts the download, in ``include`` mode it is what
    earns the strike.
    """
    matched = any(matches_any_pattern(item, patterns) for item in items)
    return matched if mode == "include" else not matched


def is_ignored(
    *,
    download_id: str,
    title: str,
    category: str | None,
    ignore: Mapping[str, list[str]],
) -> bool | None:
    """Return whether the ignore lists exempt this download.

    Download ids and categories match exactly (categories case-insensitively);
    title entries match as case-insensitive substrings. ``category=None``
    means the category is unknown: when the id and title do not exempt the
    download but category entries exist, the answer is ``None`` (undecidable)
    rather than a definite ``False``.
    """
    if download_id in ignore.get("download_ids", []):
        return True
    categories = {entry.casefold() for entry in ignore.get("categories", [])}
    if category is not None and category.casefold() in categories - {""}:
        return True
    folded_title = title.casefold()
    if any(
        entry.casefold() in folded_title for entry in ignore.get("title_contains", [])
    ):
        return True
    return None if category is None and categories else False


def select_removals(
    strike_rows: Iterable[Mapping[str, Any]], *, max_strikes: int, cap: int
) -> list[Mapping[str, Any]]:
    """Return rows at or over ``max_strikes``, oldest ``first_seen_at`` first, capped."""
    due = [row for row in strike_rows if int(row["strikes"]) >= max_strikes]
    due.sort(key=lambda row: (str(row["first_seen_at"]), str(row["download_id"])))
    return due[: max(cap, 0)]


def is_blocked_file(name: str, extensions: frozenset[str]) -> bool:
    """Return whether a file name's final suffix (lower-cased) is blocked."""
    return PurePosixPath(name).suffix.lower() in extensions
