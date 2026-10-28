"""Safety tests for Cleanarr's queue cleaning: one strike per download, held
decisions during SABnzbd outages and uncertain Sonarr/Radarr queue reads,
dry-run reporting beyond the removal cap and Ignore serialised with destructive
runs.

These reuse the end-to-end fakes of :mod:`tests.test_cleanarr_engine`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from core.context import SyncAlreadyRunning
from core.sabnzbd_types import SabHistoryJob
from core.settings_modules import CleanarrIgnoreListFull
from core.settings_normalisers import CLEANARR_IGNORE_MAX
from modules.cleanarr import engine as engine_module
from modules.cleanarr.client import CleanarrArrClient
from modules.cleanarr.models import ArrQueue
from modules.cleanarr.queue_cleaner import QUEUE_INCOMPLETE_DETAIL, QueueProtection
from tests.test_cleanarr_engine import (
    FakeArr,
    FakeSab,
    _history,
    _record,
    _run_times,
    _service,
    _strikes,
)


class PagedArr(FakeArr):
    """A fake Arr whose queue is served as explicit pages.

    ``total`` overrides the reported ``totalRecords`` (default: the records
    actually served), to simulate a queue read that ends short.
    """

    def __init__(self, app: str) -> None:
        super().__init__(app)
        self.pages: list[list[Any]] = []
        self.total: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/queue" and request.method == "GET":
            self.calls.append(("GET", request.url.path, request.url.query.decode()))
            page = int(request.url.params["page"])
            total = self.total
            if total is None:
                total = sum(len(records) for records in self.pages)
            records = self.pages[page - 1] if page <= len(self.pages) else []
            return httpx.Response(200, json={"totalRecords": total, "records": records})
        return super().handler(request)


@pytest.fixture
def arrs(monkeypatch) -> dict[str, FakeArr]:
    fakes: dict[str, FakeArr] = {
        "sonarr": PagedArr("sonarr"),
        "radarr": FakeArr("radarr"),
    }
    fakes["sonarr"].version = "4.0.0"
    monkeypatch.setattr(
        engine_module, "client_for", lambda _ctx, app: fakes[app].client()
    )
    return fakes


@pytest.fixture
def sab() -> FakeSab:
    return FakeSab()


def _episodes(download: int, *queue_ids: int, **overrides: Any) -> list[dict[str, Any]]:
    """Return one queue record per episode of a single multi-episode download."""
    return [
        _record(
            queue_id,
            downloadId=f"nzo_{download}",
            title=f"Season Pack {download}",
            **overrides,
        )
        for queue_id in queue_ids
    ]


def _job(
    nzo_id: str, *, status: str = "Completed", category: str = "tv"
) -> SabHistoryJob:
    return SabHistoryJob(
        nzo_id=nzo_id, name=nzo_id, status=status, category=category, storage=""
    )


def _strike_row(service, download_id: str) -> dict[str, Any]:
    return next(
        row
        for row in service._ctx.db.cleanarr_strike_rows()
        if row["download_id"] == download_id
    )


# ---- F2: one strike per download per run ----


async def test_multi_episode_download_gets_one_strike_per_run(db, arrs, sab) -> None:
    arrs["sonarr"].pages = [_episodes(1, 11, 12, 13)]
    service = _service(db, sab)

    first = await service.run_now()
    assert first["counts"]["struck"] == 1
    assert first["counts"]["removed"] == 0
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}
    assert arrs["sonarr"].deletes() == []

    await service.run_now()
    third = await service.run_now()
    assert third["counts"]["removed"] == 1
    # One DELETE for the whole download, aimed at one of its own queue ids.
    assert [call[1] for call in arrs["sonarr"].deletes()] == ["/api/v3/queue/11"]
    assert _history(service) == [("removed", "nzo_1")]


async def test_duplicates_across_pages_count_once(db, arrs, sab) -> None:
    pack = _episodes(1, 11, 12)
    arrs["sonarr"].pages = [[pack[0], _record(2)], [pack[1], pack[0]]]
    service = _service(db, sab)
    result = await service.run_now()
    assert result["counts"]["struck"] == 2
    assert _strikes(service) == {("sonarr", "nzo_1"): 1, ("sonarr", "nzo_2"): 1}


async def test_queue_view_shows_one_row_per_download(db, arrs, sab) -> None:
    arrs["sonarr"].pages = [
        _episodes(1, 11, 12, 13)
        + [
            _record(
                14,
                downloadId="nzo_1",
                title="Season Pack 1",
                trackedDownloadState="downloading",
                trackedDownloadStatus="ok",
            )
        ]
    ]
    service = _service(db, sab)
    await service.run_now()
    items = (await service.queue())["items"]
    assert [(row["download_id"], row["queue_id"], row["strikes"]) for row in items] == [
        ("nzo_1", 11, 1)
    ]


async def test_patterns_are_evaluated_over_every_record_of_a_download(
    db, arrs, sab
) -> None:
    excluded_episode = _record(
        12,
        downloadId="nzo_1",
        statusMessages=[{"title": "t", "messages": ["matched to series by ID"]}],
    )
    arrs["sonarr"].pages = [[_record(11, downloadId="nzo_1"), excluded_episode]]
    service = _service(db, sab)
    await service.run_now()
    assert _strikes(service) == {}
    row = (await service.queue())["items"][0]
    assert (row["download_id"], row["excluded"]) == ("nzo_1", True)


async def test_a_failed_download_record_wins_for_the_whole_download(
    db, arrs, sab
) -> None:
    arrs["sonarr"].pages = [
        [
            _record(11, downloadId="nzo_1"),
            _record(
                12,
                downloadId="nzo_1",
                trackedDownloadState="failed",
                trackedDownloadStatus="error",
            ),
        ]
    ]
    service = _service(db, sab)
    await service.run_now()
    row = _strike_row(service, "nzo_1")
    assert (row["reason"], row["queue_id"], row["strikes"]) == (
        "failed_download",
        12,
        1,
    )


# ---- F3: failed-download rows survive a SABnzbd outage unchanged ----


@pytest.mark.parametrize(
    "outage_state",
    [
        {"trackedDownloadState": "failed", "trackedDownloadStatus": "error"},
        {"trackedDownloadState": "importBlocked", "trackedDownloadStatus": "warning"},
    ],
    ids=["arr_failed_state", "reclassified_as_failed_import"],
)
async def test_outage_freezes_failed_download_rows(
    db, arrs, sab, outage_state: dict[str, str]
) -> None:
    arrs["sonarr"].pages = [
        [_record(1, trackedDownloadState="downloading", trackedDownloadStatus="ok")]
    ]
    sab.history = [_job("nzo_1", status="Failed")]
    service = _service(db, sab)
    await _run_times(service, 2)
    before = _strike_row(service, "nzo_1")
    assert (before["reason"], before["strikes"]) == ("failed_download", 2)

    sab.history = None
    arrs["sonarr"].pages = [[_record(1, **outage_state)]]
    for _ in range(3):
        result = await service.run_now()
        assert result["counts"]["struck"] == 0
    assert _strike_row(service, "nzo_1") == before
    assert arrs["sonarr"].deletes() == []
    queue_row = (await service.queue())["items"][0]
    assert queue_row["would_remove"] is False

    # Once the history is back, the row resumes counting from where it was.
    sab.history = [_job("nzo_1", status="Failed")]
    resumed = await service.run_now()
    assert resumed["counts"]["removed"] == 1


# ---- F10: an unknown category never voids a category exclusion ----


async def test_category_exclusion_holds_while_the_category_is_unknown(
    db, arrs, sab
) -> None:
    arrs["sonarr"].pages = [[_record(1), _record(2)]]
    sab.history = [_job("nzo_1", category="tv"), _job("nzo_2", category="movies")]
    service = _service(db, sab, ignore={"categories": ["tv"]})
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_2"): 1}

    sab.history = None
    for _ in range(4):
        result = await service.run_now()
        assert result["counts"]["struck"] == 0
    # The ignored download was never struck and the other one is held as it was.
    assert _strikes(service) == {("sonarr", "nzo_2"): 1}
    assert arrs["sonarr"].deletes() == []
    rows = {row["download_id"]: row for row in (await service.queue())["items"]}
    assert rows["nzo_1"]["ignored"] is False
    assert rows["nzo_1"]["would_remove"] is False

    sab.history = [_job("nzo_1", category="tv"), _job("nzo_2", category="movies")]
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_2"): 2}


async def test_download_missing_from_history_is_held_only_with_category_rules(
    db, arrs, sab
) -> None:
    arrs["sonarr"].pages = [[_record(1)]]
    held = _service(db, sab, ignore={"categories": ["tv"]})
    await held.run_now()
    assert _strikes(held) == {}

    # The id and title lists still apply when the category is unknown.
    by_title = _service(
        db, sab, ignore={"categories": ["tv"], "title_contains": ["Release"]}
    )
    await by_title.run_now()
    assert _strikes(by_title) == {}

    unconstrained = _service(db, sab)
    await unconstrained.run_now()
    assert _strikes(unconstrained) == {("sonarr", "nzo_1"): 1}


# ---- F13: records without a usable queue id ----


def _without_queue_id(record: dict[str, Any], queue_id: object) -> dict[str, Any]:
    """Return ``record`` with an unusable ``id`` (``None`` drops the field)."""
    record = dict(record)
    if queue_id is None:
        del record["id"]
    else:
        record["id"] = queue_id
    return record


@pytest.mark.parametrize("queue_id", ["bad", True, None])
async def test_a_failing_download_is_removed_through_a_usable_queue_id(
    db, arrs, sab, queue_id: object
) -> None:
    first, second = _episodes(1, 11, 12)
    arrs["sonarr"].pages = [[_without_queue_id(first, queue_id), second]]
    service = _service(db, sab)
    result = await _run_times(service, 3)
    assert result["counts"]["removed"] == 1
    assert [call[1] for call in arrs["sonarr"].deletes()] == ["/api/v3/queue/12"]
    assert _history(service) == [("removed", "nzo_1")]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("queue_id", ["bad", True, None])
async def test_a_download_whose_failing_record_has_no_queue_id_is_held(
    db, arrs, sab, queue_id: object, dry_run: bool
) -> None:
    healthy = {"trackedDownloadState": "importPending", "trackedDownloadStatus": "ok"}
    failing, other = _episodes(1, 11, 12)
    other.update(healthy)
    arrs["sonarr"].pages = [[failing, other]]
    service = _service(db, sab, dry_run=dry_run)
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}

    # The failing record loses its id: nothing can be removed, so the strike
    # row is neither incremented, cleared nor acted on.
    arrs["sonarr"].pages = [[_without_queue_id(failing, queue_id), other]]
    result = await _run_times(service, 4)
    assert result["counts"]["struck"] == 0
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}
    assert arrs["sonarr"].deletes() == []
    assert _history(service) == []
    rows = (await service.queue())["items"]
    assert [(row["download_id"], row["queue_id"]) for row in rows] == [("nzo_1", None)]
    assert rows[0]["would_remove"] is False


# ---- F16: queue reads that cannot vouch for every record of a download ----

_JOB_FOLDER = "/data/complete/tv/Job1"
# Folder references that name no folder (F17).
_FOLDERLESS_PATHS = ["/", "//", ".", "/data/complete/.."]
_UNCERTAIN_READS = [
    "shared_folder",
    "no_association",
    *(f"folderless:{path}" for path in _FOLDERLESS_PATHS),
    "malformed_record",
    "short_page",
]


def _primary() -> dict[str, Any]:
    """Return the failing record of ``nzo_1``, stored in ``_JOB_FOLDER``."""
    return _record(1, outputPath=_JOB_FOLDER)


def _uncertain_read(arr: PagedArr, uncertain: str) -> None:
    """Serve ``nzo_1`` beside a record (or a page) Cleanarr cannot tie to it.

    ``shared_folder``: a record without a ``downloadId`` (whose title the
    ignore list protects) refers to the same folder; ``no_association``: a
    record has neither field; ``folderless:<path>``: its ``outputPath`` names
    no folder; ``malformed_record``: a record is not an object;
    ``short_page``: paging ends before ``totalRecords``.
    """
    if uncertain == "short_page":
        arr.pages, arr.total = [[_primary()]], 2
        return
    companion: Any = _record(2, title="Keep.This.S01E02", outputPath=_JOB_FOLDER)
    del companion["downloadId"]
    if uncertain == "no_association":
        del companion["outputPath"]
    elif uncertain.startswith("folderless:"):
        companion["outputPath"] = uncertain.removeprefix("folderless:")
    elif uncertain == "malformed_record":
        companion = "not a record"
    arr.pages = [[_primary(), companion]]


def _complete_read(arr: PagedArr) -> None:
    arr.pages, arr.total = [[_primary()]], None


async def _held_note(service) -> str | None:
    """Return the Status tab's ``queue_held`` note for Sonarr, if any."""
    return next(
        (
            warning["detail"]
            for warning in (await service.status())["health"]
            if (warning["source"], warning["code"]) == ("sonarr", "queue_held")
        ),
        None,
    )


def _expected_held_detail(uncertain: str) -> str:
    if uncertain == "shared_folder":
        return (
            "1 download(s) held: a queue record without a download ID may "
            "belong to them. Strikes left unchanged."
        )
    return QUEUE_INCOMPLETE_DETAIL


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("uncertain", _UNCERTAIN_READS)
async def test_an_uncertain_queue_read_holds_the_download_and_its_strikes(
    db, arrs, sab, uncertain: str, dry_run: bool
) -> None:
    sonarr = arrs["sonarr"]
    _complete_read(sonarr)
    service = _service(
        db, sab, dry_run=dry_run, ignore={"title_contains": ["keep.this"]}
    )
    await _run_times(service, 2)
    before = _strike_row(service, "nzo_1")
    assert before["strikes"] == 2

    # Without the hold, the next run would reach max_strikes and remove nzo_1.
    _uncertain_read(sonarr, uncertain)
    for _ in range(4):
        result = await service.run_now()
        assert result["counts"]["struck"] == 0
        assert result["counts"]["removed"] == 0
        assert result["counts"]["would_remove"] == 0
    assert _strike_row(service, "nzo_1") == before
    assert sonarr.deletes() == []
    assert _history(service) == []
    assert await _held_note(service) == _expected_held_detail(uncertain)

    # A complete read resumes normal decisions from the preserved strikes.
    _complete_read(sonarr)
    result = await service.run_now()
    assert await _held_note(service) is None
    if dry_run:
        assert result["counts"]["would_remove"] == 1
        assert _history(service) == [("would_remove", "nzo_1")]
        assert sonarr.deletes() == []
    else:
        assert result["counts"]["removed"] == 1
        assert _history(service) == [("removed", "nzo_1")]
        assert [call[1] for call in sonarr.deletes()] == ["/api/v3/queue/1"]


@pytest.mark.parametrize("uncertain", _UNCERTAIN_READS)
async def test_the_queue_view_never_offers_to_remove_a_held_download(
    db, arrs, sab, uncertain: str
) -> None:
    _complete_read(arrs["sonarr"])
    service = _service(db, sab, dry_run=True)
    await _run_times(service, 3)
    ready = await service.queue()
    assert ready["held"] == {}
    assert [row["would_remove"] for row in ready["items"]] == [True]

    _uncertain_read(arrs["sonarr"], uncertain)
    queue = await service.queue()
    assert queue["held"] == {"sonarr": _expected_held_detail(uncertain)}
    assert [
        (row["download_id"], row["strikes"], row["would_remove"])
        for row in queue["items"]
    ] == [("nzo_1", 3, False)]


@pytest.mark.parametrize("uncertain", ["no_association", "folderless:/", "short_page"])
async def test_an_incomplete_read_changes_no_strike_row(
    db, arrs, sab, uncertain: str
) -> None:
    sonarr = arrs["sonarr"]
    sonarr.pages = [[_primary(), _record(3)]]
    service = _service(db, sab)
    await service.run_now()
    before = {row["download_id"]: row for row in db.cleanarr_strike_rows()}
    assert set(before) == {"nzo_1", "nzo_3"}

    # nzo_3 is missing and nzo_1 now looks like a failed download, but the
    # read cannot show every record: nothing is cleared or reclassified.
    _uncertain_read(sonarr, uncertain)
    sab.history = [_job("nzo_1", status="Failed")]
    await _run_times(service, 3)
    after = {row["download_id"]: row for row in db.cleanarr_strike_rows()}
    assert after == before

    sab.history = []
    _complete_read(sonarr)
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_1"): 2}


async def test_a_companion_with_its_download_id_still_decides_normally(
    db, arrs, sab
) -> None:
    companion = _record(
        2, downloadId="nzo_1", title="Keep.This.S01E02", outputPath=_JOB_FOLDER
    )
    arrs["sonarr"].pages = [[_primary(), companion]]
    service = _service(db, sab, ignore={"title_contains": ["keep.this"]})
    result = await _run_times(service, 3)
    # The ignored companion protects its download through the download id.
    assert result["counts"]["struck"] == 0
    assert _strikes(service) == {}
    assert arrs["sonarr"].deletes() == []
    assert await _held_note(service) is None
    assert (await service.queue())["held"] == {}


async def test_a_record_without_a_download_id_elsewhere_holds_nothing(
    db, arrs, sab
) -> None:
    unrelated = _record(2, outputPath="/data/complete/tv/Other")
    del unrelated["downloadId"]
    arrs["sonarr"].pages = [[_primary(), unrelated]]
    service = _service(db, sab)
    result = await _run_times(service, 3)
    assert result["counts"]["removed"] == 1
    assert [call[1] for call in arrs["sonarr"].deletes()] == ["/api/v3/queue/1"]
    assert await _held_note(service) is None


async def test_a_shared_sab_job_folder_holds_the_download(db, arrs, sab) -> None:
    # The record names no folder, but SABnzbd's job for nzo_1 uses the one
    # an unmatched record refers to.
    companion = _record(2, outputPath=_JOB_FOLDER)
    del companion["downloadId"]
    arrs["sonarr"].pages = [[_record(1, outputPath=""), companion]]
    sab.history = [
        SabHistoryJob(
            nzo_id="nzo_1",
            name="Job1",
            status="Completed",
            category="tv",
            storage=_JOB_FOLDER,
        )
    ]
    service = _service(db, sab)
    result = await _run_times(service, 3)
    assert result["counts"]["struck"] == 0
    assert _strikes(service) == {}
    assert arrs["sonarr"].deletes() == []
    assert await _held_note(service) == _expected_held_detail("shared_folder")


@pytest.mark.parametrize("path", _FOLDERLESS_PATHS)
def test_a_reference_naming_no_folder_makes_the_protection_incomplete(
    path: str,
) -> None:
    # The protection applies the folder rule itself, whoever built the read.
    read = ArrQueue(items=(), unparsed_output_paths=(_JOB_FOLDER, path))
    protection = QueueProtection.of([read])
    assert protection.complete is False
    assert protection.unmatched_folders == frozenset({"Job1"})

    control = QueueProtection.of(
        [ArrQueue(items=(), unparsed_output_paths=(_JOB_FOLDER,))]
    )
    assert control.complete is True


# ---- F16: a held download keeps its strikes whatever its records show ----

_HEALTHY = {"trackedDownloadState": "importPending", "trackedDownloadStatus": "ok"}
_HELD_DETAIL = _expected_held_detail("shared_folder")


def _without_download_id(record: dict[str, Any]) -> dict[str, Any]:
    record = dict(record)
    del record["downloadId"]
    return record


def _hiding_read(arr: PagedArr, hiding: str) -> None:
    """Serve ``nzo_1`` so that its records cannot show whether it still fails.

    ``looks_healthy``: its record looks healthy beside a record without a
    ``downloadId`` in its folder; ``lost_download_id``: its only record has
    lost its ``downloadId``.
    """
    if hiding == "looks_healthy":
        healthy = _record(1, outputPath=_JOB_FOLDER, **_HEALTHY)
        arr.pages = [
            [healthy, _without_download_id(_record(2, outputPath=_JOB_FOLDER))]
        ]
    else:
        arr.pages = [[_without_download_id(_primary())]]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("hiding", ["looks_healthy", "lost_download_id"])
async def test_a_held_download_keeps_its_strikes_until_a_complete_read(
    db, arrs, sab, hiding: str, dry_run: bool
) -> None:
    sonarr = arrs["sonarr"]
    _complete_read(sonarr)
    service = _service(db, sab, dry_run=dry_run)
    await _run_times(service, 2)
    before = _strike_row(service, "nzo_1")
    assert before["strikes"] == 2

    _hiding_read(sonarr, hiding)
    for _ in range(4):
        result = await service.run_now()
        assert result["counts"]["struck"] == 0
        assert result["counts"]["removed"] == 0
        assert result["counts"]["would_remove"] == 0
    # The whole row is unchanged: strikes, timestamps, reason and reporting flag.
    assert _strike_row(service, "nzo_1") == before
    assert sonarr.deletes() == []
    assert _history(service) == []
    assert await _held_note(service) == _HELD_DETAIL
    queue = await service.queue()
    assert queue["held"] == {"sonarr": _HELD_DETAIL}
    assert queue["items"] == []

    # A complete failing read resumes counting from the preserved two strikes.
    _complete_read(sonarr)
    result = await service.run_now()
    assert await _held_note(service) is None
    if dry_run:
        assert result["counts"]["would_remove"] == 1
        assert _strike_row(service, "nzo_1")["strikes"] == 3
        assert _history(service) == [("would_remove", "nzo_1")]
        assert sonarr.deletes() == []
    else:
        assert result["counts"]["removed"] == 1
        assert [call[1] for call in sonarr.deletes()] == ["/api/v3/queue/1"]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("read", ["healthy", "departed"])
async def test_a_complete_read_still_clears_recovered_and_departed_strikes(
    db, arrs, sab, read: str, dry_run: bool
) -> None:
    sonarr = arrs["sonarr"]
    _complete_read(sonarr)
    service = _service(db, sab, dry_run=dry_run)
    await _run_times(service, 2)
    assert _strikes(service) == {("sonarr", "nzo_1"): 2}

    healthy = [[_record(1, outputPath=_JOB_FOLDER, **_HEALTHY)]]
    sonarr.pages = healthy if read == "healthy" else []
    await service.run_now()
    assert _strikes(service) == {}
    assert await _held_note(service) is None


async def test_departed_strikes_wait_while_a_record_without_a_download_id_remains(
    db, arrs, sab
) -> None:
    sonarr = arrs["sonarr"]
    sonarr.pages = [[_primary(), _record(3)]]
    service = _service(db, sab)
    await service.run_now()
    departed = _strike_row(service, "nzo_3")

    # nzo_1 recovered and nzo_3 is no longer listed, but the record without a
    # downloadId (in another folder) may be all that is left of nzo_3.
    unmatched = _without_download_id(_record(2, outputPath="/data/complete/tv/Other"))
    sonarr.pages = [[_record(1, outputPath=_JOB_FOLDER, **_HEALTHY), unmatched]]
    await _run_times(service, 2)
    assert _strikes(service) == {("sonarr", "nzo_3"): 1}
    assert _strike_row(service, "nzo_3") == departed
    assert await _held_note(service) == _HELD_DETAIL

    # Once no such record remains, the departed download loses its strikes.
    sonarr.pages = [[_record(1, outputPath=_JOB_FOLDER, **_HEALTHY)]]
    await service.run_now()
    assert _strikes(service) == {}
    assert await _held_note(service) is None


# ---- F7: dry run reports every download, even beyond the cap ----


async def test_dry_run_reports_downloads_beyond_the_cap(db, arrs, sab) -> None:
    arrs["sonarr"].pages = [[_record(1), _record(2), _record(3)]]
    service = _service(db, sab, dry_run=True, max_removals_per_run=1)
    await _run_times(service, 3)
    assert _history(service) == [("would_remove", "nzo_1")]
    await service.run_now()
    await service.run_now()
    reported = sorted(download for _action, download in _history(service))
    assert reported == ["nzo_1", "nzo_2", "nzo_3"]
    await _run_times(service, 3)
    # Each download is reported exactly once.
    assert len(_history(service)) == 3

    # A later live run still removes the downloads reported in dry run.
    live = _service(db, sab, max_removals_per_run=1)
    result = await live.run_now()
    assert result["counts"]["removed"] == 1
    assert len(arrs["sonarr"].deletes()) == 1


# ---- F5 / F9: Ignore is serialised with runs and never claims a lost id ----


async def test_ignore_is_rejected_while_a_run_is_removing(
    db, arrs, sab, monkeypatch
) -> None:
    arrs["sonarr"].pages = [[_record(1), _record(2)]]
    service = _service(db, sab)
    await _run_times(service, 2)

    started = asyncio.Event()
    release = asyncio.Event()
    original_remove = CleanarrArrClient.remove

    async def slow_remove(self: CleanarrArrClient, queue_id: int) -> bool:
        started.set()
        await release.wait()
        return await original_remove(self, queue_id)

    monkeypatch.setattr(CleanarrArrClient, "remove", slow_remove)
    run = asyncio.create_task(service.run_now())
    await started.wait()
    with pytest.raises(SyncAlreadyRunning):
        await service.ignore("nzo_2")
    release.set()
    result = await run

    # The rejected Ignore changed nothing, so the run's removals stand.
    assert result["counts"]["removed"] == 2
    assert "nzo_2" not in service.settings()["ignore"]["download_ids"]
    assert service._ctx.db.recent_activity(1)[0]["action"] == "Cleanarr"

    # Once the run finished, Ignore succeeds.
    settings = await service.ignore("nzo_2")
    assert "nzo_2" in settings["ignore"]["download_ids"]


async def test_ignore_with_a_full_list_keeps_the_strikes(db, arrs, sab) -> None:
    full = [f"SABnzbd_nzo_{index}" for index in range(CLEANARR_IGNORE_MAX)]
    arrs["sonarr"].pages = [[_record(1)]]
    service = _service(db, sab, ignore={"download_ids": full})
    await service.run_now()

    with pytest.raises(CleanarrIgnoreListFull):
        await service.ignore("nzo_1")
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}
    assert service.settings()["ignore"]["download_ids"] == full
    activity = [row["action"] for row in service._ctx.db.recent_activity(5)]
    assert "Cleanarr download ignored" not in activity

    # An id that is already listed is still acknowledged.
    assert (await service.ignore(full[0]))["ignore"]["download_ids"] == full
