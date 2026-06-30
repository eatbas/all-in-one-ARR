"""Tests for Deletarr junk-pattern classification."""

from __future__ import annotations

from modules.deletarr.patterns import JunkPatterns


def test_video_and_whitelisted_artwork_are_preserved() -> None:
    assert JunkPatterns.is_junk_file("Movie.mkv", "/media/Movie.mkv")["is_junk"] is False
    assert JunkPatterns.is_junk_file("poster.jpg", "/media/poster.jpg")["is_junk"] is False


def test_common_junk_extensions_and_patterns_are_flagged() -> None:
    nfo = JunkPatterns.is_junk_file("Movie.nfo", "/media/Movie.nfo")
    sample = JunkPatterns.is_junk_file("movie.sample.jpg", "/media/movie.sample.jpg")
    assert nfo == {"is_junk": True, "reason": "Junk file extension"}
    assert sample["is_junk"] is True
    assert "sample" in sample["reason"]


def test_metadata_must_match_video_or_folder_name() -> None:
    matching_video = JunkPatterns.is_junk_file(
        "Movie.jpg",
        "/media/Movie.jpg",
        video_basenames=["Movie"],
        folder_name="Other",
    )
    matching_folder = JunkPatterns.is_junk_file(
        "Folder Name.png",
        "/media/Folder Name.png",
        video_basenames=[],
        folder_name="Folder Name",
    )
    unrelated = JunkPatterns.is_junk_file(
        "random.png",
        "/media/random.png",
        video_basenames=["Movie"],
        folder_name="Folder Name",
    )

    assert matching_video["is_junk"] is False
    assert matching_folder["is_junk"] is False
    assert unrelated == {
        "is_junk": True,
        "reason": "Metadata file not matching video or folder",
    }


def test_movie_and_tv_name_helpers() -> None:
    assert JunkPatterns.is_junk_folder("Samples") is True
    assert JunkPatterns.video_matches_folder("Anything.mkv", "{tmdb-1234} (2020)") is True
    assert JunkPatterns.video_matches_folder("Example Movie 2020.mkv", "Example Movie (2020)") is True
    assert JunkPatterns.video_matches_folder("Other Film.mkv", "Example Movie") is False
    assert JunkPatterns.is_tv_season_folder("Season 01") is True
    assert JunkPatterns.is_tv_specials_folder("Season 00") is True
    assert JunkPatterns.is_tv_specials_folder("[Group] Specials") is True
    assert JunkPatterns.is_valid_tv_episode("Example Show S01E02.mkv", "Example Show") is True
    assert JunkPatterns.is_valid_tv_episode("S01E02.mkv", "{tvdb-1} (2020)") is True
    assert JunkPatterns.is_valid_tv_episode("Pilot.mkv", "Example Show") is False


def test_unknown_files_are_preserved() -> None:
    assert JunkPatterns.is_junk_file("movie.srtx", "/media/movie.srtx") == {
        "is_junk": False,
        "reason": None,
    }
