"""Tests for Cleanarr path mapping and the symlink-refusing root checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.cleanarr.paths import (
    category_container_names,
    container_categories,
    folder_name,
    reroot,
    resolve_within,
    split_under,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/data/complete/tv/Job1", "Job1"),
        ("/data/complete/tv/Job1/", "Job1"),
        ("/data/complete/tv/Job1/.", "Job1"),
        ("Job1", "Job1"),
        ("", None),
        ("/", None),
        ("//", None),
        (".", None),
        ("..", None),
        ("/data/complete/..", None),
    ],
)
def test_folder_name_needs_a_usable_last_component(
    path: str, expected: str | None
) -> None:
    assert folder_name(path) == expected


@pytest.mark.parametrize(
    ("remote", "remote_root", "local_root", "expected"),
    [
        ("/data/complete/tv/Job", "/data/complete", "/downloads/complete", "/downloads/complete/tv/Job"),
        ("/data/complete/", "/data/complete", "/downloads/complete/", "/downloads/complete"),
        ("/data/complete/Job/", "/data/complete/", "/dl", "/dl/Job"),
        ("/data/complete2/Job", "/data/complete", "/dl", None),
        ("/data/complete/../etc", "/data/complete", "/dl", None),
        ("/other/Job", "/data/complete", "/dl", None),
        ("relative/Job", "/data/complete", "/dl", None),
        ("/data/complete/Job", "relative", "/dl", None),
        ("/data/complete/Job", "/", "/dl", "/dl/data/complete/Job"),
    ],
)  # fmt: skip
def test_reroot(
    remote: str, remote_root: str, local_root: str, expected: str | None
) -> None:
    assert reroot(remote, remote_root, local_root) == expected


def test_category_container_names() -> None:
    names = category_container_names(
        ["tv", "/data/complete/movies", "/elsewhere/x", "a/b", "..", "/tv/", ""],
        "/data/complete",
    )
    assert names == frozenset({"tv", "movies"})
    assert category_container_names(["/data/complete"], "/data/complete") == frozenset()


def test_container_categories_maps_folders_to_category_names() -> None:
    categories = container_categories(
        [
            ("tv", "tv"),
            ("anime", "tv"),
            ("movies", "/data/complete/films"),
            ("away", "/elsewhere/x"),
            ("", "music"),
        ],
        "/data/complete",
    )
    assert categories == {
        "tv": frozenset({"tv", "anime"}),
        "films": frozenset({"movies"}),
    }


def test_resolve_within_accepts_real_paths_inside_root(tmp_path: Path) -> None:
    (tmp_path / "job").mkdir()
    target = tmp_path / "job" / "file.mkv"
    target.write_text("x")
    assert resolve_within(target, tmp_path) == target.resolve()
    assert resolve_within(tmp_path, tmp_path) == tmp_path.resolve()


def test_resolve_within_accepts_paths_written_under_a_linked_root(
    tmp_path: Path,
) -> None:
    # The configured root itself may be a link (a mount alias); only what lies
    # below it is checked.
    real = tmp_path / "real"
    (real / "job").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert resolve_within(alias / "job", alias) == (real / "job").resolve()
    assert resolve_within(real / "job", alias) == (real / "job").resolve()


def test_resolve_within_rejects_missing_and_escaping_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    escape = root / "escape"
    escape.symlink_to(outside)
    assert resolve_within(root / "missing", root) is None
    assert resolve_within(escape, root) is None
    assert resolve_within(outside, root) is None
    assert resolve_within(outside, tmp_path / "no-root") is None
    assert resolve_within(root / ".." / "outside.txt", root) is None
    assert resolve_within(Path("relative"), root) is None


def test_resolve_within_rejects_links_that_stay_inside_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    target = root / "target"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "file.exe").write_text("x")
    (root / "link").symlink_to(target, target_is_directory=True)
    (root / "file-link").symlink_to(target / "sub" / "file.exe")
    assert resolve_within(root / "link", root) is None
    assert resolve_within(root / "link" / "sub" / "file.exe", root) is None
    assert resolve_within(root / "file-link", root) is None
    assert resolve_within(target / "sub" / "file.exe", root) is not None


def test_split_under_is_lexical(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    assert split_under(root / "a" / "b", root) == (root.resolve(), ("a", "b"))
    assert split_under(root, root) == (root.resolve(), ())
    assert split_under(tmp_path / "other", root) is None
    assert split_under(root / "a", tmp_path / "missing") is None
