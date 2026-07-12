"""Tests for Deletarr junk-pattern classification."""

from __future__ import annotations

import pytest

from modules.deletarr.patterns import JunkPatterns


def test_video_and_whitelisted_artwork_are_preserved() -> None:
    assert (
        JunkPatterns.is_junk_file("Movie.mkv", "/media/Movie.mkv")["is_junk"] is False
    )
    assert (
        JunkPatterns.is_junk_file("poster.jpg", "/media/poster.jpg")["is_junk"] is False
    )


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


def test_movie_manager_companion_metadata_examples_are_kept() -> None:
    examples = (
        (
            "Man of War (2026) {tmdb-1705729}",
            "Man of War (2026) {tmdb-1705729} - "
            "[AMZN][WEBDL-1080p][EAC3 5.1][h264]-playWEB",
        ),
        (
            "The Sheep Detectives (2026) {tmdb-1301421}",
            "The Sheep Detectives (2026) {tmdb-1301421} - "
            "[AMZN][WEBDL-1080p][EAC3 Atmos 5.1][h264]-Kitsune",
        ),
        (
            "Lee Cronins The Mummy (2026) {tmdb-1304313}",
            "Lee Cronins The Mummy (2026) {tmdb-1304313} - "
            "[WEBDL-1080p][EAC3 5.1][x264]-CYBER",
        ),
    )

    for folder_name, video_basename in examples:
        companion_names = (
            "folder.jpg",
            f"{folder_name}.jpg",
            f"{video_basename}.xml",
            f"{video_basename}.xml",
        )
        for companion_name in companion_names:
            assert (
                _is_junk(
                    companion_name,
                    video_basenames=[video_basename],
                    folder_name=folder_name,
                )
                is False
            ), companion_name

        assert (
            _is_junk(
                "unrelated.xml",
                video_basenames=[video_basename],
                folder_name=folder_name,
            )
            is True
        )
        assert (
            _is_junk(
                "random.png",
                video_basenames=[video_basename],
                folder_name=folder_name,
            )
            is True
        )


def test_metadata_identity_matching_tolerates_removed_manager_tags() -> None:
    assert (
        _is_junk(
            "Man of War (2026).jpg",
            video_basenames=[
                "Man of War (2026) {tmdb-1705729} - "
                "[AMZN][WEBDL-1080p][EAC3 5.1][h264]-playWEB"
            ],
            folder_name="Man of War (2026) {tmdb-1705729}",
        )
        is False
    )
    assert (
        _is_junk(
            "Man of War (2026)-poster.jpg",
            video_basenames=[],
            folder_name="Man of War (2026) {tmdb-1705729}",
        )
        is False
    )
    assert (
        _is_junk(
            "Other Film (2026).jpg",
            video_basenames=[
                "Man of War (2026) {tmdb-1705729} - "
                "[AMZN][WEBDL-1080p][EAC3 5.1][h264]-playWEB"
            ],
            folder_name="Man of War (2026) {tmdb-1705729}",
        )
        is True
    )


def test_metadata_identity_keys_drop_empty_normalised_key() -> None:
    assert JunkPatterns._metadata_identity_keys("{tmdb-1705729}") == {"{tmdb-1705729}"}


def test_movie_and_tv_name_helpers() -> None:
    assert JunkPatterns.is_junk_folder("Samples") is True
    assert (
        JunkPatterns.video_matches_folder("Anything.mkv", "{tmdb-1234} (2020)") is True
    )
    assert (
        JunkPatterns.video_matches_folder(
            "Example Movie 2020.mkv", "Example Movie (2020)"
        )
        is True
    )
    assert JunkPatterns.video_matches_folder("Other Film.mkv", "Example Movie") is False
    assert JunkPatterns.is_tv_season_folder("Season 01") is True
    assert JunkPatterns.is_tv_specials_folder("Season 00") is True
    assert JunkPatterns.is_tv_specials_folder("[Group] Specials") is True
    assert (
        JunkPatterns.is_valid_tv_episode("Example Show S01E02.mkv", "Example Show")
        is True
    )
    assert JunkPatterns.is_valid_tv_episode("S01E02.mkv", "{tvdb-1} (2020)") is True
    assert JunkPatterns.is_valid_tv_episode("Pilot.mkv", "Example Show") is False


def test_unknown_files_are_preserved() -> None:
    assert JunkPatterns.is_junk_file("movie.srtx", "/media/movie.srtx") == {
        "is_junk": False,
        "reason": None,
    }


def _reason(name: str, **kwargs) -> str | None:
    return JunkPatterns.is_junk_file(name, f"/media/{name}", **kwargs)["reason"]


def _is_junk(name: str, **kwargs) -> bool:
    return JunkPatterns.is_junk_file(name, f"/media/{name}", **kwargs)["is_junk"]


def test_scene_tag_patterns_match_case_insensitively() -> None:
    # These uppercase scene tags were previously dead (re.match on a lower-cased
    # name with no IGNORECASE never matched them).
    assert _reason("RARBG.txt") == "Junk pattern: RARBG"
    assert _reason("Proxies.dat") == "Junk pattern: Proxies"


@pytest.mark.parametrize("token", ["YTS", "YTS.MX", "YTS.LT", "YIFY"])
@pytest.mark.parametrize("ext", [".xml", ".jpg", ".png"])
def test_yts_yify_matching_companion_is_kept(token: str, ext: str) -> None:
    """A sidecar whose basename matches the protected video or folder is kept."""
    folder_name = f"GameStop (2026) {{tmdb-12345}} - {token}"
    video_basename = f"{folder_name} - [WEBDL-1080p][AAC 2.0][x264]"

    # Exact-basename companion containing the release provenance token.
    assert (
        _is_junk(
            f"{video_basename}{ext}",
            video_basenames=[video_basename],
            folder_name=folder_name,
        )
        is False
    )
    # Folder-matching companion containing the release provenance token.
    assert (
        _is_junk(
            f"{folder_name}{ext}",
            video_basenames=[video_basename],
            folder_name=folder_name,
        )
        is False
    )


@pytest.mark.parametrize("token", ["YTS", "YTS.MX", "YTS.LT", "YIFY"])
@pytest.mark.parametrize("ext", [".xml", ".jpg", ".png"])
def test_yts_yify_unrelated_metadata_is_reviewable(token: str, ext: str) -> None:
    """Unrelated metadata containing YTS/YIFY tokens remains a review candidate."""
    folder_name = "GameStop (2026) {tmdb-12345}"
    video_basename = (
        "GameStop (2026) {tmdb-12345} - [WEBDL-1080p][AAC 2.0][x264]-YTS.MX"
    )
    name = f"unrelated-{token}{ext}"

    assert (
        _is_junk(name, video_basenames=[video_basename], folder_name=folder_name)
        is True
    )
    assert (
        _reason(name, video_basenames=[video_basename], folder_name=folder_name)
        == "Metadata file not matching video or folder"
    )


def test_yts_yify_artwork_suffix_and_promotional_files() -> None:
    """Artwork suffixes and promotional/www/extension rules stay unchanged."""
    folder_name = "GameStop (2026) {tmdb-12345}"
    video_basename = (
        "GameStop (2026) {tmdb-12345} - [WEBDL-1080p][AAC 2.0][x264]-YTS.MX"
    )

    # Artwork suffix with a matching stem is kept.
    assert (
        _is_junk(
            f"{folder_name}-poster.jpg",
            video_basenames=[video_basename],
            folder_name=folder_name,
        )
        is False
    )

    # Promotional www.* artwork remains junk.
    assert _is_junk("www.YTS.MX.jpg") is True
    assert "www" in _reason("www.YTS.MX.jpg")

    # Concrete junk extensions remain junk.
    assert _reason("YTS.txt") == "Junk file extension"

    # Arbitrary unknown files are preserved rather than risk deleting a companion.
    assert _is_junk("YIFY.data") is False


def test_recognised_artwork_is_kept() -> None:
    assert (
        _is_junk("fanart.jpg", video_basenames=["Movie"], folder_name="Movie") is False
    )
    assert _is_junk("banner.PNG") is False
    assert _is_junk("poster.bmp") is False
    assert _is_junk("season01-poster.jpg") is False
    assert _is_junk("season-all.png") is False
    assert _is_junk("Movie-poster.jpg", video_basenames=["Movie"]) is False
    assert _is_junk("folder name-fanart.png", folder_name="Folder Name") is False
    # Case-insensitive video/folder match.
    assert _is_junk("Movie.JPG", video_basenames=["movie"]) is False
    # Still junk when nothing matches.
    assert (
        _is_junk("unknown-poster.jpg", video_basenames=["Movie"], folder_name="Other")
        is True
    )
    assert (
        _is_junk("random.png", video_basenames=["Movie"], folder_name="Other") is True
    )


def test_episode_signatures_accept_common_formats() -> None:
    def valid(name: str) -> bool:
        return JunkPatterns.is_valid_tv_episode(name, "Show")

    assert valid("Show S01E02.mkv") is True
    assert valid("Show S1E1.mkv") is True
    assert valid("Show S01 E02.mkv") is True
    assert valid("Show 1x05.mkv") is True
    assert valid("The Daily Show 2024.06.01.mkv") is True
    assert valid("One Piece - 1071.mkv") is True
    assert valid("Chernobyl Part 1.mkv") is False
    assert valid("Pilot.mkv") is False


def test_season_folder_recognises_variants() -> None:
    for name in (
        "Season 01",
        "Season 1 (2019)",
        "Season 01 - Complete",
        "Saison 1",
        "Staffel 2",
        "Series 3",
        "S01",
        "Season1",
        "Season.01",
    ):
        assert JunkPatterns.is_tv_season_folder(name) is True, name
    for name in ("Specials", "Featurettes", "Extras", "Season"):
        assert JunkPatterns.is_tv_season_folder(name) is False, name


def test_specials_folder_recognises_zero_and_localised() -> None:
    for name in (
        "Specials",
        "Season 0",
        "Season 00",
        "Season000",
        "[Group] Specials",
        "Especiales",
        "Especiais",
    ):
        assert JunkPatterns.is_tv_specials_folder(name) is True, name
    for name in ("Season 1", "Season 10"):
        assert JunkPatterns.is_tv_specials_folder(name) is False, name


def test_video_matches_folder_uses_year_and_strips_tags() -> None:
    match = JunkPatterns.video_matches_folder
    # A matching year is sufficient even with imdb/edition tags present.
    assert (
        match("Seven.1995.mkv", "Se7en (1995) {imdb-tt0114369} {edition-Directors}")
        is True
    )
    assert (
        match("The Matrix 1999.mkv", "The Matrix (1999) {edition-Remastered}") is True
    )
    # No year: distinctive words still match after stop-word removal.
    assert match("matrix.reloaded.mkv", "The Matrix Reloaded") is True
    # No year, wrong movie.
    assert match("Other Film.mkv", "Example Movie") is False
    # Everything strips away -> unconditional keep.
    assert match("whatever.mkv", "{tmdb-1234} (2020)") is True
