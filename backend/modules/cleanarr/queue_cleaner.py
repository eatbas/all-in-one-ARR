"""Cleanarr queue cleaning: strike stuck items and remove repeat offenders.

Each run groups an app's queue records by download (Sonarr reports one record
per episode of a multi-episode download), strikes every usenet download that
failed to import or download (after the ignore lists and the failed-import
patterns) once, clears the strikes of downloads that recovered or left the
queue, and removes downloads at ``max_strikes`` with blocklisting and a new
search. Dry run logs each would-be removal once.

A download Cleanarr cannot decide on is *held*: its strike row is neither
incremented, reclassified, cleared nor removed. That covers an existing
``failed_download`` strike while SABnzbd's history is unavailable, a download
whose category is unknown while category ignore rules exist, a download whose
failing records have no usable queue id to remove, a download (failing or
healthy-looking) whose folder a queue record without a usable ``downloadId``
refers to, and, while any such record names a folder, a struck download
missing from the read (that record may be all that is left of it). When a
queue record can be tied to neither a download nor a folder, or paging ends
short, the whole app's queue cleaning is held and none of its strike rows
change.

Records without a usable queue id still take part in every decision on their
download, so an importing or ignored record protects it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from core.app_metrics import record_cleanarr_removal, record_cleanarr_strike
from modules.cleanarr.client import CleanarrArrClient, CleanarrClientError
from modules.cleanarr.models import (
    AppRun,
    HealthWarning,
    QueueItem,
    RunSummary,
    SabState,
)
from modules.cleanarr.paths import folder_name
from modules.cleanarr.rules import (
    StrikeReason,
    classify,
    import_failures_count,
    is_ignored,
    select_removals,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.db import Database

_DETAIL_MAX = 300

QUEUE_INCOMPLETE_DETAIL = (
    "Queue cleaning held: a queue record could not be matched to a download, "
    "or the queue was only read in part. Strikes left unchanged."
)


class QueueRead(Protocol):
    """The parts of one Sonarr/Radarr queue read that decide what is safe to act on.

    Satisfied by :class:`~modules.cleanarr.models.ArrQueue` and
    :class:`~modules.cleanarr.models.AppRun`.
    """

    @property
    def items(self) -> tuple[QueueItem, ...] | None: ...

    @property
    def unparsed_output_paths(self) -> tuple[str, ...]: ...

    @property
    def downloads_complete(self) -> bool: ...


def download_folders(records: tuple[QueueItem, ...], sab: SabState) -> frozenset[str]:
    """Return the folder names one download is known by.

    That is each record's ``outputPath`` and the storage folder of the SABnzbd
    history job with the same ``downloadId``, wherever they name a folder.
    """
    paths = [record.output_path for record in records]
    job = sab.jobs_by_id.get(records[0].download_id)
    if job is not None:
        paths.append(job.storage)
    names = (folder_name(path) for path in paths)
    return frozenset(name for name in names if name is not None)


@dataclass(frozen=True)
class QueueProtection:
    """What queue reads leave uncertain, shared by queue cleaning and the malware pass.

    ``complete`` is ``False`` when a read holds a record tied to neither a
    download nor a folder (including an ``outputPath`` that names no folder,
    such as ``/``), or paging ended short: any download may then have a record
    (importing, ignored) that was not seen, so nothing is safe.
    ``unmatched_folders`` are the folder names of records without a usable
    ``downloadId``: their state and title cannot be tied to a download, so a
    download known by one of those folders is not safe either.
    """

    complete: bool
    unmatched_folders: frozenset[str]

    @classmethod
    def of(cls, reads: Iterable[QueueRead]) -> QueueProtection:
        """Return the protection over one or more apps' queue reads.

        Applies :func:`~modules.cleanarr.paths.folder_name` itself, so a read
        whose unmatched reference names no folder is incomplete even when the
        read did not flag it.
        """
        reads = tuple(reads)
        names = [
            folder_name(path) for read in reads for path in read.unparsed_output_paths
        ]
        return cls(
            complete=all(read.downloads_complete for read in reads)
            and None not in names,
            unmatched_folders=frozenset(name for name in names if name is not None),
        )

    def holds(self, records: tuple[QueueItem, ...], sab: SabState) -> bool:
        """Return whether one download (all its records) must be left alone."""
        if not self.complete:
            return True
        return not self.unmatched_folders.isdisjoint(download_folders(records, sab))

    def held_ids(self, items: Iterable[QueueItem], sab: SabState) -> frozenset[str]:
        """Return the download ids of ``items`` that must be left alone."""
        return frozenset(
            records[0].download_id
            for records in group_downloads(items)
            if self.holds(records, sab)
        )


@dataclass(frozen=True)
class AppDecisions:
    """One app's failing-download decisions and the strike rows it must keep.

    ``complete`` is ``False`` when the whole app is held (every decision and
    every strike row is then held). ``held_ids`` are the download ids whose
    strike rows stay exactly as they are whatever their records show now,
    including downloads that look healthy or are missing from the read.
    ``held_detail`` explains a hold caused by the queue read, or is ``None``
    when the read held nothing.
    """

    decisions: list[DownloadDecision]
    complete: bool
    held_ids: frozenset[str]
    held_detail: str | None


@dataclass(frozen=True)
class DownloadDecision:
    """What a run does with one failing download (all its queue records).

    ``item`` is the record that represents the download: its queue id is the
    one removed and its message is the one shown. It is a failing record with
    a usable queue id when one exists; otherwise ``held`` is ``True``.
    ``ignored`` is ``None`` when the ignore lists cannot be evaluated
    (unknown category).
    """

    item: QueueItem
    reason: StrikeReason
    ignored: bool | None
    excluded: bool
    held: bool

    @property
    def strikes(self) -> bool:
        """Whether this download earns a strike in this run."""
        return not (self.held or self.ignored or self.excluded)


def short_detail(text: str) -> str:
    """Return ``text`` trimmed to a history-safe length."""
    return text if len(text) <= _DETAIL_MAX else f"{text[: _DETAIL_MAX - 1]}…"


def first_message(item: QueueItem) -> str:
    """Return the most specific status message (the last one), or ``""``."""
    return item.messages[-1] if item.messages else ""


def item_ignored(
    item: QueueItem, settings: dict[str, Any], sab: SabState
) -> bool | None:
    """Return whether the ignore lists exempt a queue item (``None``: undecidable).

    The Arr queue carries no SABnzbd category, so it is looked up from the
    SABnzbd history job with the same ``downloadId``. Without that job the
    category is unknown, which only matters when category entries exist.
    """
    job = sab.jobs_by_id.get(item.download_id)
    return is_ignored(
        download_id=item.download_id,
        title=item.title,
        category=job.category if job else None,
        ignore=settings["ignore"],
    )


def group_downloads(items: Iterable[QueueItem]) -> list[tuple[QueueItem, ...]]:
    """Group queue records by download id, in first-seen order."""
    groups: dict[str, list[QueueItem]] = {}
    for item in items:
        groups.setdefault(item.download_id, []).append(item)
    return [tuple(group) for group in groups.values()]


def download_ignored(
    records: tuple[QueueItem, ...], settings: dict[str, Any], sab: SabState
) -> bool | None:
    """Return whether the ignore lists exempt one download (all its records).

    ``True`` when any record is ignored (an ignored episode title protects the
    whole download), ``None`` when any is undecidable, else ``False``. Shared
    by the queue decisions and the malware pass so they never disagree.
    """
    answers = [item_ignored(item, settings, sab) for item in records]
    if any(answers):
        return True
    return None if None in answers else False


def decide_download(
    records: tuple[QueueItem, ...],
    settings: dict[str, Any],
    sab: SabState,
    held_ids: frozenset[str] = frozenset(),
) -> DownloadDecision | None:
    """Return the decision for one download's records, or ``None`` when healthy.

    ``failed_download`` on any record wins over ``failed_import``; the
    failed-import patterns are evaluated over every failing record. Every
    record counts towards the ignore lists, including records without a
    usable queue id.
    """
    failing = [(classify(item, sab.failed_ids), item) for item in records]
    downloads = [item for reason, item in failing if reason == "failed_download"]
    imports = [item for reason, item in failing if reason == "failed_import"]
    if not downloads and not imports:
        return None
    ignored = download_ignored(records, settings, sab)
    if downloads:
        reason: StrikeReason = "failed_download"
        excluded = False
    else:
        reason = "failed_import"
        queue = settings["queue"]
        excluded = not import_failures_count(
            imports, mode=queue["pattern_mode"], patterns=queue["patterns"]
        )
    item = _representative(downloads or imports)
    return DownloadDecision(
        item=item,
        reason=reason,
        ignored=ignored,
        excluded=excluded,
        held=ignored is None or item.queue_id is None or item.download_id in held_ids,
    )


def _representative(failing: list[QueueItem]) -> QueueItem:
    """Return the first failing record with a usable queue id, else the first one."""
    return next((item for item in failing if item.queue_id is not None), failing[0])


def download_decisions(
    items: Iterable[QueueItem],
    settings: dict[str, Any],
    sab: SabState,
    held_ids: frozenset[str] = frozenset(),
) -> list[DownloadDecision]:
    """Return one decision per failing download, in first-seen order."""
    decisions = (
        decide_download(records, settings, sab, held_ids)
        for records in group_downloads(items)
    )
    return [decision for decision in decisions if decision is not None]


def outage_held_ids(
    strike_rows: Iterable[Mapping[str, Any]], app: str, sab: SabState
) -> frozenset[str]:
    """Return ``app``'s ``failed_download`` strikes frozen while SABnzbd history is unknown."""
    if sab.history is not None:
        return frozenset()
    return frozenset(
        row["download_id"]
        for row in strike_rows
        if row["app"] == app and row["reason"] == "failed_download"
    )


def departed_held_ids(
    protection: QueueProtection,
    items: Iterable[QueueItem],
    strike_rows: Iterable[Mapping[str, Any]],
) -> frozenset[str]:
    """Return the struck downloads missing from a read that cannot rule them out.

    A record without a usable ``downloadId`` may be all that is left of a
    struck download, so while such a record names a folder, a struck download
    missing from the read cannot be told from one that left the queue. Its
    row is kept until the download is listed again or no such record remains.
    ``strike_rows`` must belong to the read's app.
    """
    if not protection.unmatched_folders:
        return frozenset()
    listed = {item.download_id for item in items}
    return frozenset(
        row["download_id"] for row in strike_rows if row["download_id"] not in listed
    )


def _read_held_detail(
    read_held: frozenset[str],
    decisions: list[DownloadDecision],
    strike_rows: Iterable[Mapping[str, Any]],
) -> str | None:
    """Return the ``queue_held`` note for downloads the read holds, or ``None``.

    Only held downloads that are failing or struck count: a healthy download
    without strikes has nothing to hold.
    """
    relevant = {decision.item.download_id for decision in decisions}
    relevant.update(row["download_id"] for row in strike_rows)
    count = len(read_held & relevant)
    if not count:
        return None
    return (
        f"{count} download(s) held: a queue record without a download ID may "
        "belong to them. Strikes left unchanged."
    )


def app_decisions(
    app: str,
    read: QueueRead,
    settings: dict[str, Any],
    sab: SabState,
    strike_rows: Iterable[Mapping[str, Any]],
) -> AppDecisions:
    """Return one app's decisions with every hold applied, for runs and the Queue view.

    Downloads are held by a SABnzbd history outage (see
    :func:`outage_held_ids`) and by the read's :class:`QueueProtection`
    (see also :func:`departed_held_ids`), so a run never acts on or clears,
    and the Queue view never offers to remove, a download the read cannot
    vouch for. The held ids cover every listed download, not only failing
    ones, so a held download that looks healthy keeps its strikes too.
    """
    rows = [row for row in strike_rows if row["app"] == app]
    protection = QueueProtection.of((read,))
    items = read.items or ()
    read_held = protection.held_ids(items, sab) | departed_held_ids(
        protection, items, rows
    )
    held_ids = outage_held_ids(rows, app, sab) | read_held
    decisions = download_decisions(items, settings, sab, held_ids)
    if not protection.complete:
        return AppDecisions(decisions, False, held_ids, QUEUE_INCOMPLETE_DETAIL)
    detail = _read_held_detail(read_held, decisions, rows)
    return AppDecisions(decisions, True, held_ids, detail)


def strike_app(
    db: Database,
    run: AppRun,
    settings: dict[str, Any],
    sab: SabState,
    summary: RunSummary,
) -> list[dict[str, Any]]:
    """Strike each failing download once; clear downloads that recovered or left.

    Held downloads keep their strike rows exactly as they are, whether they
    look failing, healthy or are missing from the read (see
    :attr:`AppDecisions.held_ids`). While SABnzbd history is unknown,
    ``failed_download`` rows of downloads that left the queue are kept too, so
    an outage neither resets nor removes them. When the queue read is
    incomplete, no strike row of the app changes at all, because a download
    missing from the read may still be queued. Each hold caused by the read
    adds a ``queue_held`` note to the Status tab.
    """
    plan = app_decisions(run.app, run, settings, sab, db.cleanarr_strike_rows())
    if plan.held_detail is not None:
        summary.notes.append(
            HealthWarning(source=run.app, code="queue_held", detail=plan.held_detail)
        )
    if not plan.complete:
        return []
    struck: list[dict[str, Any]] = []
    held: list[str] = []
    for decision in plan.decisions:
        item = decision.item
        # A missing queue id always holds the decision; checking it here too
        # narrows the type for the strike row.
        if decision.held or item.queue_id is None:
            held.append(item.download_id)
            continue
        if not decision.strikes:
            continue
        struck.append(
            db.cleanarr_strike(
                run.app,
                item.download_id,
                queue_id=item.queue_id,
                title=item.title,
                reason=decision.reason,
                message=short_detail(first_message(item)),
            )
        )
        record_cleanarr_strike(app=run.app, reason=decision.reason)
    keep = [row["download_id"] for row in struck] + held + sorted(plan.held_ids)
    if sab.history is None:
        db.cleanarr_clear_strikes_for_reason_except(run.app, "failed_import", keep)
    else:
        db.cleanarr_clear_strikes_except(run.app, keep)
    summary.struck += len(struck)
    return struck


async def apply_removals(
    db: Database,
    clients: dict[str, CleanarrArrClient],
    runs: list[AppRun],
    settings: dict[str, Any],
    summary: RunSummary,
) -> None:
    """Remove (or, in dry run, log once) the oldest downloads at the threshold.

    Only downloads struck in this run are eligible, and live removals and
    dry-run would-removes share one ``max_removals_per_run`` budget. In dry
    run, rows already reported are left out before the cap, so they never
    hold back later downloads; a live run still removes them.
    """
    rows = [row for run in runs for row in run.struck]
    if summary.dry_run:
        rows = [row for row in rows if not row["would_remove_logged"]]
    due = select_removals(
        rows,
        max_strikes=int(settings["max_strikes"]),
        cap=int(settings["max_removals_per_run"]),
    )
    for row in due:
        if summary.dry_run:
            _log_would_remove(db, row, summary)
        else:
            await _remove(db, clients[row["app"]], row, summary)


def _log_would_remove(db: Database, row: Any, summary: RunSummary) -> None:
    """Log a dry-run would-remove entry and flag the strike row as reported."""
    _history(db, row, "would_remove", row["reason"], dry_run=True)
    db.cleanarr_mark_would_remove_logged(row["app"], row["download_id"])
    record_cleanarr_removal(app=row["app"], reason=row["reason"], dry_run=True)
    summary.would_remove += 1


async def _remove(
    db: Database, client: CleanarrArrClient, row: Any, summary: RunSummary
) -> None:
    """Remove one queue item, blocklisting it and searching again."""
    try:
        removed = await client.remove(int(row["queue_id"]))
    except CleanarrClientError as exc:
        _history(db, row, "remove_failed", short_detail(str(exc)), dry_run=False)
        summary.remove_failed += 1
        return
    db.cleanarr_delete_strike(row["app"], row["download_id"])
    if removed:
        _history(db, row, "removed", row["reason"], dry_run=False)
        record_cleanarr_removal(app=row["app"], reason=row["reason"], dry_run=False)
        summary.removed += 1
    else:
        _history(db, row, "already_gone", row["reason"], dry_run=False)
        summary.already_gone += 1


def _history(
    db: Database, row: Any, action: str, detail: str, *, dry_run: bool
) -> None:
    """Write one queue history row from a strike row."""
    db.cleanarr_add_history(
        app=row["app"],
        action=action,
        download_id=row["download_id"],
        title=row["title"],
        detail=detail,
        dry_run=dry_run,
    )
