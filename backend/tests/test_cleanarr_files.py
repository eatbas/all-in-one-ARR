"""Tests for Cleanarr's defensive filesystem operations (real ``tmp_path``)."""

from __future__ import annotations

import errno
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from modules.cleanarr import files
from modules.cleanarr.files import (
    delete_files,
    expired_quarantine,
    find_blocked_files,
    orphan_candidates,
    purge,
    quarantine,
    quarantine_names,
    quarantine_original_name,
    quarantine_problem,
    quarantine_stamp,
)
from modules.cleanarr.models import OrphanCandidate

_BLOCKED = frozenset({".exe", ".lnk"})
_NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def _touch(path: Path, *, age: timedelta | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    if age is not None:
        _age(path, age)
    return path


def _age(path: Path, age: timedelta) -> None:
    stamp = (_NOW - age).timestamp()
    os.utime(path, (stamp, stamp), follow_symlinks=False)


# ---- find_blocked_files ----


def test_find_blocked_files_walks_nested_dirs(tmp_path: Path) -> None:
    job = tmp_path / "Job"
    _touch(job / "movie.mkv")
    nested = _touch(job / "sub" / "deep" / "setup.EXE")
    shortcut = _touch(job / "open.lnk")
    found = find_blocked_files(job, tmp_path, _BLOCKED)
    assert sorted(found) == sorted([nested.resolve(), shortcut.resolve()])


def test_find_blocked_files_ignores_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    job = root / "Job"
    job.mkdir(parents=True)
    outside = tmp_path / "outside"
    _touch(outside / "evil.exe")
    (job / "link.exe").symlink_to(outside / "evil.exe")
    (job / "linked-dir").symlink_to(outside, target_is_directory=True)
    assert find_blocked_files(job, root, _BLOCKED) == []


def test_find_blocked_files_single_file_and_missing_job(tmp_path: Path) -> None:
    single = _touch(tmp_path / "virus.exe")
    benign = _touch(tmp_path / "movie.mkv")
    assert find_blocked_files(single, tmp_path, _BLOCKED) == [single.resolve()]
    assert find_blocked_files(benign, tmp_path, _BLOCKED) == []
    assert find_blocked_files(tmp_path / "missing", tmp_path, _BLOCKED) == []


def test_find_blocked_files_respects_max_files(tmp_path: Path) -> None:
    job = tmp_path / "Job"
    for index in range(5):
        _touch(job / f"{index}.exe")
    assert len(find_blocked_files(job, tmp_path, _BLOCKED, max_files=3)) == 3


def test_find_blocked_files_drops_candidates_that_vanish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = tmp_path / "Job"
    _touch(job / "a.exe")
    real = files.resolve_within
    calls: list[Path] = []

    def flaky(path: Path, root: Path) -> Path | None:
        calls.append(path)
        return real(path, root) if len(calls) == 1 else None

    monkeypatch.setattr(files, "resolve_within", flaky)
    assert find_blocked_files(job, tmp_path, _BLOCKED) == []


def test_find_blocked_files_refuses_a_symlinked_job_inside_the_root(
    tmp_path: Path,
) -> None:
    # The link target is inside the completed folder, but it is not the job
    # SABnzbd completed, so nothing behind the link may be examined.
    root = tmp_path / "complete"
    other = root / "Other.Job"
    blocked = _touch(other / "setup.exe")
    (root / "Job").symlink_to(other, target_is_directory=True)
    assert find_blocked_files(root / "Job", root, _BLOCKED) == []
    assert blocked.exists()


def test_find_blocked_files_refuses_a_symlinked_single_file(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    real = _touch(root / "Other" / "virus.exe")
    (root / "virus.exe").symlink_to(real)
    assert find_blocked_files(root / "virus.exe", root, _BLOCKED) == []


def test_find_blocked_files_refuses_a_symlinked_intermediate_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "complete"
    _touch(root / "real-tv" / "Job" / "setup.exe")
    (root / "tv").symlink_to(root / "real-tv", target_is_directory=True)
    assert find_blocked_files(root / "tv" / "Job", root, _BLOCKED) == []


# ---- delete_files ----


def test_delete_files_reports_per_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    good = _touch(root / "a.exe")
    locked = _touch(root / "b.exe")
    outside = _touch(tmp_path / "c.exe")
    link = root / "d.exe"
    link.symlink_to(outside)

    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "b.exe":
            raise PermissionError(errno.EACCES, "Permission denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = delete_files([good, locked, outside, link], root)
    assert result.done == [good]
    assert result.failed == [
        (locked, "Permission denied"),
        (outside, "outside_root"),
        (link, "symlink"),
    ]
    assert not good.exists()
    assert locked.exists() and outside.exists()


# ---- orphan_candidates ----


def _orphans(root: Path, **overrides) -> list[Path]:
    return [candidate.path for candidate in _orphan_candidates(root, **overrides)]


def _orphan_candidates(root: Path, **overrides) -> list[OrphanCandidate]:
    arguments = {
        "completed_root": root,
        "quarantine_dir": root / "_cleanarr_quarantine",
        "container_names": frozenset({"tv"}),
        "referenced_names": frozenset({"Referenced"}),
        "min_age": timedelta(hours=24),
        "now": _NOW,
    }
    arguments.update(overrides)
    return orphan_candidates(**arguments)


def test_orphan_candidates_selection_rules(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    old = timedelta(days=2)
    orphan_file = _touch(root / "Loose.File.mkv", age=old)
    orphan_dir = root / "Old.Job"
    _touch(orphan_dir / "x.mkv", age=old)
    _age(orphan_dir, old)
    _touch(root / "Referenced" / "x.mkv", age=old)
    _age(root / "Referenced", old)
    _touch(root / "Young.Job", age=timedelta(hours=1))
    _touch(root / ".hidden", age=old)
    (root / "_cleanarr_quarantine").mkdir()
    _age(root / "_cleanarr_quarantine", old)
    tv_child = _touch(root / "tv" / "Show.S01E01", age=old)
    _touch(root / "tv" / ".partial", age=old)
    _touch(root / "tv" / "Referenced", age=old)
    (root / "link").symlink_to(orphan_file)

    found = _orphan_candidates(root)
    assert [candidate.path for candidate in found] == sorted(
        [orphan_file, orphan_dir, tv_child.resolve()]
    )
    containers = {candidate.path.name: candidate.container for candidate in found}
    assert containers == {
        "Loose.File.mkv": None,
        "Old.Job": None,
        "Show.S01E01": "tv",
    }


def test_orphan_candidates_excludes_the_quarantine_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    old = timedelta(days=2)
    holder = root / "holder"
    (holder / "q").mkdir(parents=True)
    _age(holder, old)
    assert _orphans(root, quarantine_dir=holder / "q") == []


def test_orphan_candidates_with_a_quarantine_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job", age=timedelta(days=2))
    assert _orphans(root, quarantine_dir=tmp_path / "elsewhere") == [job]


def test_orphan_candidates_with_missing_root_or_unreadable_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _orphans(tmp_path / "missing") == []

    root = tmp_path / "complete"
    entry = _touch(root / "Job", age=timedelta(days=2))
    real_lstat = Path.lstat

    def lstat(self: Path):
        if self == entry:
            raise OSError(errno.EIO, "I/O error")
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    assert _orphans(root) == []


def test_orphan_candidates_skips_an_unreadable_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    _touch(root / "tv" / "Show", age=timedelta(days=2))
    real_iterdir = Path.iterdir

    def iterdir(self: Path):
        if self.name == "tv":
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    assert _orphans(root) == []


# ---- quarantine ----


def test_quarantine_renames_with_stamp_and_clash_suffix(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    q = root / "_q"
    first = _touch(root / "Job")
    second_dir = root / "Folder"
    _touch(second_dir / "x.mkv")

    result = quarantine([first, second_dir], root, q, now=_NOW)
    assert result.done == [first, second_dir]
    assert result.failed == []
    assert result.moved_to == {
        first: q.resolve() / "20261028T120000Z__Job",
        second_dir: q.resolve() / "20261028T120000Z__Folder",
    }
    assert sorted(entry.name for entry in q.iterdir()) == [
        "20261028T120000Z__Folder",
        "20261028T120000Z__Job",
    ]

    again = _touch(root / "Job")
    clashed = quarantine([again], root, q, now=_NOW)
    assert clashed.done == [again]
    assert clashed.moved_to[again].name == "20261028T120000Z__Job-1"
    assert (q / "20261028T120000Z__Job-1").exists()


def test_quarantine_refuses_unsafe_entries(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    q = root / "_q"
    outside = _touch(tmp_path / "outside")
    link = root / "link"
    root.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    missing = root / "missing"
    result = quarantine([outside, link, missing], root, q, now=_NOW)
    assert result.done == []
    assert result.failed == [
        (outside, "outside_root"),
        (link, "symlink"),
        (missing, "outside_root"),
    ]


def test_quarantine_reports_cross_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")
    real_lstat = Path.lstat

    class _Stat:
        st_dev = -1
        st_mode = stat.S_IFREG

    def lstat(self: Path):
        return _Stat() if self == job else real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    result = quarantine([job], root, root / "_q", now=_NOW)
    assert result.failed == [(job, "cross_device")]
    assert job.exists()


def test_quarantine_reports_rename_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    exdev = _touch(root / "A")
    busy = _touch(root / "B")

    def rename(source, target) -> None:
        name = Path(source).name
        if name == "A":
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        raise OSError(errno.EBUSY, "")

    monkeypatch.setattr(files.os, "rename", rename)
    result = quarantine([exdev, busy], root, root / "_q", now=_NOW)
    assert result.failed == [(exdev, "cross_device"), (busy, "OSError")]


def test_quarantine_reports_name_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")
    monkeypatch.setattr(files, "_free_target", lambda _q, _name: None)
    result = quarantine([job], root, root / "_q", now=_NOW)
    assert result.failed == [(job, "name_clash")]


def test_free_target_gives_up_after_the_clash_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "_MAX_NAME_CLASHES", 1)
    _touch(tmp_path / "n")
    _touch(tmp_path / "n-1")
    assert files._free_target(tmp_path, "n") is None


def test_quarantine_fails_everything_when_folder_is_unusable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")
    blocker = _touch(root / "file")
    result = quarantine([job], root, blocker / "q", now=_NOW)
    assert result.failed == [(job, "Not a directory")]

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "qlink").symlink_to(elsewhere, target_is_directory=True)
    result = quarantine([job], root, root / "qlink", now=_NOW)
    assert result.failed == [(job, "symlink")]
    assert list(elsewhere.iterdir()) == []

    result = quarantine([job], root, tmp_path / "outside-q", now=_NOW)
    assert result.failed == [(job, "quarantine_outside_root")]
    assert not (tmp_path / "outside-q").exists()


def test_quarantine_refuses_a_link_inside_the_root_and_its_ancestors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")
    (root / "real-q").mkdir()
    (root / "qlink").symlink_to(root / "real-q", target_is_directory=True)
    assert quarantine([job], root, root / "qlink", now=_NOW).failed == [
        (job, "symlink")
    ]
    # A symlinked ancestor is refused before anything is created through it.
    assert quarantine([job], root, root / "qlink" / "q", now=_NOW).failed == [
        (job, "symlink")
    ]
    assert list((root / "real-q").iterdir()) == []
    assert job.exists()


def test_quarantine_reports_a_folder_it_cannot_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")

    def mkdir(self: Path, *args, **kwargs) -> None:
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", mkdir)
    result = quarantine([job], root, root / "_q", now=_NOW)
    assert result.failed == [(job, "Permission denied")]
    assert job.exists()


def test_quarantine_refuses_a_folder_swapped_for_a_link_after_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    job = _touch(root / "Job")
    monkeypatch.setattr(files, "resolve_within", lambda _path, _root: None)
    assert quarantine([job], root, root / "_q", now=_NOW).failed == [(job, "symlink")]


def test_quarantine_problem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "complete"
    (root / "real").mkdir(parents=True)
    (root / "link").symlink_to(root / "real", target_is_directory=True)
    assert quarantine_problem(root, root / "_q") is None
    assert quarantine_problem(root, root / "real" / "q") is None
    assert quarantine_problem(root, root / "link") == "symlink"
    assert quarantine_problem(root, root / "link" / "q") == "symlink"
    assert quarantine_problem(root, root) == "quarantine_outside_root"
    assert quarantine_problem(root, tmp_path / "q") == "quarantine_outside_root"

    real_lstat = Path.lstat

    def lstat(self: Path):
        if self.name == "real":
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    assert quarantine_problem(root, root / "real" / "q") == "Permission denied"


# ---- expiry and purge ----


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("20261028T120000Z__Job", datetime(2026, 10, 28, 12, tzinfo=UTC)),
        ("20261328T120000Z__Job", None),
        ("20261028T120000Z__", None),
        ("Job", None),
        ("not-a-stamp__Job", None),
    ],
)
def test_quarantine_stamp_parsing(name: str, expected: datetime | None) -> None:
    assert quarantine_stamp(name) == expected


def test_quarantine_original_name() -> None:
    assert quarantine_original_name("20261001T000000Z__Keep.This-1") == "Keep.This-1"
    assert quarantine_original_name("Plain") == ""


def test_expired_quarantine_uses_the_stamp(tmp_path: Path) -> None:
    q = tmp_path / "q"
    old = _touch(q / "20261001T000000Z__Old")
    _touch(q / "20261027T000000Z__New")
    _touch(q / "Unstamped")
    (q / "20261001T000000Z__Link").symlink_to(old)
    expired = expired_quarantine(tmp_path, q, retention=timedelta(days=14), now=_NOW)
    assert expired == [old]
    assert (
        expired_quarantine(
            tmp_path, tmp_path / "missing", retention=timedelta(1), now=_NOW
        )
        == []
    )


def test_quarantine_names_lists_every_entry(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    q = root / "_q"
    _touch(q / "20261001T000000Z__Old")
    _touch(q / "Unstamped")
    assert quarantine_names(root, q) == frozenset(
        {"20261001T000000Z__Old", "Unstamped"}
    )


def test_quarantine_names_is_none_when_it_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "complete"
    root.mkdir()
    # A missing or symlinked folder is never mistaken for an empty quarantine.
    assert quarantine_names(root, root / "_q") is None
    (root / "_q").symlink_to(tmp_path, target_is_directory=True)
    assert quarantine_names(root, root / "_q") is None
    real = root / "real"
    real.mkdir()

    def unreadable(_self: Path):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "iterdir", unreadable)
    assert quarantine_names(root, real) is None


def test_expired_quarantine_refuses_a_symlinked_quarantine(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    root.mkdir()
    outside = tmp_path / "outside"
    _touch(outside / "20200101T000000Z__keep.txt")
    (root / "_q").symlink_to(outside, target_is_directory=True)
    assert expired_quarantine(root, root / "_q", retention=timedelta(1), now=_NOW) == []
    # The completed folder itself is never treated as the quarantine.
    _touch(root / "20200101T000000Z__Job")
    assert expired_quarantine(root, root, retention=timedelta(1), now=_NOW) == []


def test_purge_deletes_files_and_directories(tmp_path: Path) -> None:
    q = tmp_path / "q"
    stamped_file = _touch(q / "20261001T000000Z__File")
    stamped_dir = q / "20261001T000000Z__Dir"
    _touch(stamped_dir / "nested" / "x.mkv")
    result = purge([stamped_file, stamped_dir], tmp_path, q)
    assert result.done == [stamped_file, stamped_dir]
    assert list(q.iterdir()) == []


def test_purge_never_follows_a_symlinked_quarantine(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    root.mkdir()
    outside = tmp_path / "outside"
    keep = _touch(outside / "20200101T000000Z__keep.txt")
    (root / "_q").symlink_to(outside, target_is_directory=True)
    entry = root / "_q" / keep.name
    assert purge([entry, keep], root, root / "_q").failed == [
        (entry, "outside_quarantine"),
        (keep, "outside_quarantine"),
    ]
    assert keep.exists()


def test_purge_refuses_unsafe_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    q = tmp_path / "q"
    q.mkdir()
    target = _touch(tmp_path / "keep.mkv")
    link = q / "20261001T000000Z__Link"
    link.symlink_to(target)
    unstamped = _touch(q / "Plain")
    outside = _touch(tmp_path / "20261001T000000Z__Outside")
    locked = _touch(q / "20261001T000000Z__Locked")

    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.endswith("Locked"):
            raise PermissionError(errno.EACCES, "Permission denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    nested = _touch(q / "20261001T000000Z__Dir" / "20261001T000000Z__Nested")
    result = purge([link, unstamped, outside, locked, nested], tmp_path, q)
    assert result.done == []
    assert result.failed == [
        (link, "symlink"),
        (unstamped, "unstamped"),
        (outside, "outside_quarantine"),
        (locked, "Permission denied"),
        (nested, "outside_quarantine"),
    ]
    assert target.exists() and nested.exists()


def test_purge_refuses_everything_without_a_quarantine_folder(tmp_path: Path) -> None:
    entry = tmp_path / "20261001T000000Z__Job"
    assert purge([entry], tmp_path, tmp_path / "missing").failed == [
        (entry, "outside_quarantine")
    ]


def test_purge_refuses_the_quarantine_folder_itself(tmp_path: Path) -> None:
    q = tmp_path / "20261001T000000Z__q"
    q.mkdir()
    assert purge([q], tmp_path, q).failed == [(q, "outside_quarantine")]
    # The completed folder is never accepted as the quarantine folder.
    entry = _touch(tmp_path / "20261001T000000Z__Job")
    assert purge([entry], tmp_path, tmp_path).failed == [(entry, "outside_quarantine")]
    assert entry.exists()
