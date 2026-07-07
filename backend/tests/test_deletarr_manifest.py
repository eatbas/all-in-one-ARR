"""Tests for the Deletarr Radarr/Sonarr manifest builder and path translation."""

from __future__ import annotations

import os

from modules.deletarr.manifest import (
    _basename_without_ext,
    _collect_roots,
    _reroot,
    build_movie_manifest,
    build_tv_manifest,
)
from tests.conftest import FakeDeletarrArr


def _n(path: str) -> str:
    return os.path.normpath(path)


def test_reroot_translates_relative_to_matching_root() -> None:
    assert _reroot(
        "/data/movies/Inception (2010)/Inception.mkv",
        ["/data/movies"],
        "/media/movies",
    ) == _n("/media/movies/Inception (2010)/Inception.mkv")


def test_reroot_uses_shared_library_mount_and_preserves_categories() -> None:
    # Several category roots share the parent /data/movies, so that parent is the
    # library mount and the category segment survives translation onto the local
    # root (order-independent).
    roots = ["/data/movies/archive", "/data/movies/collections"]
    assert _reroot(
        "/data/movies/collections/A Film (2020)/A.mkv", roots, "/media/movies"
    ) == _n("/media/movies/collections/A Film (2020)/A.mkv")
    assert _reroot(
        "/data/movies/archive/B (2001)", list(reversed(roots)), "/media/movies"
    ) == _n("/media/movies/archive/B (2001)")


def test_reroot_handles_single_root_exact_and_unresolved() -> None:
    # A single root is its own mount — the unchanged flat-library behaviour.
    assert _reroot("/a/b/c/film.mkv", ["/a/b"], "/local") == _n("/local/c/film.mkv")
    # A path equal to the mount maps onto the local root itself.
    assert _reroot("/a/b", ["/a/b"], "/local") == _n("/local")
    # A path outside the mount is unresolved.
    assert _reroot("/other/x.mkv", ["/a/b"], "/local") is None
    # No usable roots at all is unresolved.
    assert _reroot("/a/b/film.mkv", [], "/local") is None
    assert _reroot("/a/b/film.mkv", [""], "/local") is None
    # Roots on different mounts share no prefix — unresolved (heuristic fallback).
    assert _reroot("/a/b/film.mkv", ["/a/b", "/x/y"], "/local") is None
    # An empty root string is ignored; the remaining root still resolves.
    assert _reroot("/a/b/film.mkv", ["", "/a"], "/local") == _n("/local/b/film.mkv")


def test_basename_without_ext_handles_both_forms() -> None:
    assert _basename_without_ext("Movie.mkv") == "Movie"
    assert _basename_without_ext("Movie") == "Movie"


def test_collect_roots_gathers_from_items_and_root_folders() -> None:
    roots = _collect_roots(
        [{"rootFolderPath": "/r1"}, {"rootFolderPath": ""}],
        [{"path": "/r2"}, {"path": ""}],
    )
    assert set(roots) == {"/r1", "/r2"}


async def test_movie_manifest_maps_files_and_skips_fileless_and_unresolved() -> None:
    client = FakeDeletarrArr(
        movies=[
            {
                "path": "/movies/A (2020)",
                "rootFolderPath": "/movies",
                "movieFile": {"path": "/movies/A (2020)/A.mkv"},
            },
            {"path": "/movies/B (2021)", "rootFolderPath": "/movies"},  # fileless
            {
                "path": "/movies/D (2022)",
                "rootFolderPath": "/movies",
                "movieFile": {"path": "/nope/D.mkv"},  # file path unresolvable
            },
            {"path": "/other/C", "rootFolderPath": "/movies"},  # unresolved folder
            {"rootFolderPath": "/movies"},  # no path
        ],
        root_folders=[{"path": "/movies"}],
    )
    manifest = await build_movie_manifest(client, "/media/movies")

    assert manifest.available is True
    managed = _n("/media/movies/A (2020)")
    assert set(manifest.folders) == {managed}
    folder = manifest.folder_for(managed)
    assert folder is not None
    assert folder.media_paths == frozenset({_n("/media/movies/A (2020)/A.mkv")})
    assert folder.media_basenames == frozenset({"A"})
    assert manifest.is_known_folder(_n("/media/movies/B (2021)")) is True
    # Folder resolves but its file does not: known, yet not a cleanable folder.
    assert manifest.is_known_folder(_n("/media/movies/D (2022)")) is True
    assert manifest.folder_for(_n("/media/movies/D (2022)")) is None
    assert manifest.is_known_folder(_n("/media/movies/nope")) is False
    assert manifest.media_paths == {_n("/media/movies/A (2020)/A.mkv")}


async def test_movie_manifest_preserves_category_folders_across_multiple_roots() -> None:
    # Mirrors a real Radarr with several category root folders nested under a
    # shared parent that maps onto Deletarr's single local movies mount.
    client = FakeDeletarrArr(
        movies=[
            {
                "path": "/data/media/movies/collections/A View (1985)",
                "rootFolderPath": "/data/media/movies/collections",
                "movieFile": {
                    "path": "/data/media/movies/collections/A View (1985)/A.mkv"
                },
            },
            {
                "path": "/data/media/movies/animations/archive/Toy (1995)",
                "rootFolderPath": "/data/media/movies/animations/archive",
                "movieFile": {
                    "path": "/data/media/movies/animations/archive/Toy (1995)/Toy.mkv"
                },
            },
        ],
        root_folders=[
            {"path": "/data/media/movies/collections"},
            {"path": "/data/media/movies/animations/archive"},
        ],
    )
    manifest = await build_movie_manifest(client, "/media/movies")

    collections = _n("/media/movies/collections/A View (1985)")
    animations = _n("/media/movies/animations/archive/Toy (1995)")
    assert set(manifest.folders) == {collections, animations}
    folder = manifest.folder_for(collections)
    assert folder is not None
    assert folder.media_paths == frozenset(
        {_n("/media/movies/collections/A View (1985)/A.mkv")}
    )
    # The intermediate category containers are recognised as ancestors, not orphans.
    assert manifest.contains_managed_descendant(_n("/media/movies/collections")) is True
    assert manifest.contains_managed_descendant(_n("/media/movies/animations")) is True
    assert (
        manifest.contains_managed_descendant(_n("/media/movies/animations/archive"))
        is True
    )
    # A sibling category with no tracked movie is not treated as a container.
    assert manifest.contains_managed_descendant(_n("/media/movies/turkish")) is False


async def test_movie_manifest_unavailable_on_error() -> None:
    manifest = await build_movie_manifest(FakeDeletarrArr(fail=("movies",)), "/media/movies")
    assert manifest.available is False
    assert manifest.detail is not None and "boom" in manifest.detail
    assert manifest.folders == {}


async def test_tv_manifest_maps_episode_files_and_skips_edge_cases() -> None:
    client = FakeDeletarrArr(
        series=[
            {"id": 1, "path": "/tv/Show (2019)", "rootFolderPath": "/tv"},
            {"id": 2, "path": "/tv/Empty", "rootFolderPath": "/tv"},  # no files
            {"id": 3, "path": "/other/Z", "rootFolderPath": "/tv"},  # unresolved
            {"path": "/tv/NoId", "rootFolderPath": "/tv"},  # missing id
        ],
        episode_files={
            1: [
                {"path": "/tv/Show (2019)/Season 01/Show S01E01.mkv"},
                {"path": "/other/x.mkv"},  # unresolved episode
                {},  # no path
            ],
        },
        root_folders=[{"path": "/tv"}],
    )
    manifest = await build_tv_manifest(client, "/media/tv")

    show = _n("/media/tv/Show (2019)")
    assert set(manifest.folders) == {show}
    folder = manifest.folder_for(show)
    assert folder is not None
    assert folder.media_paths == frozenset(
        {_n("/media/tv/Show (2019)/Season 01/Show S01E01.mkv")}
    )
    assert manifest.is_known_folder(_n("/media/tv/Empty")) is True


async def test_tv_manifest_unavailable_on_series_error() -> None:
    manifest = await build_tv_manifest(FakeDeletarrArr(fail=("series",)), "/media/tv")
    assert manifest.available is False


async def test_tv_manifest_unavailable_on_episode_error() -> None:
    client = FakeDeletarrArr(
        series=[{"id": 1, "path": "/tv/Show", "rootFolderPath": "/tv"}],
        root_folders=[{"path": "/tv"}],
        fail=("episode_files",),
    )
    manifest = await build_tv_manifest(client, "/media/tv")
    assert manifest.available is False
    assert manifest.detail is not None and "boom" in manifest.detail
