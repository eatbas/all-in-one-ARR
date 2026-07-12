"""Patterns for identifying junk files in media collections."""

from __future__ import annotations

import re
from typing import Any


class JunkPatterns:
    """Rules copied from the standalone Deletarr app and made import-local."""

    JUNK_EXTENSIONS = {
        ".nfo",
        ".txt",
        ".url",
        ".htm",
        ".html",
        ".exe",
        ".bat",
        ".sh",
        ".torrent",
        ".sfv",
        ".md5",
        ".nzb",
        ".srr",
        ".idx",
        ".sub",
        ".lnk",
    }

    METADATA_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".xml",
    }

    JUNK_FOLDERS = {
        "sample",
        "samples",
        "proof",
        "extras",
        "bonus",
    }

    IGNORED_FOLDERS = {
        "@eaDir",
        "#recycle",
        ".git",
        ".DS_Store",
    }

    # Concrete junk/name-spam patterns. Release-group/source provenance tokens such
    # as YTS or YIFY are deliberately excluded: they describe where a release came
    # from, not whether a companion file is disposable. Matching metadata identity
    # is evaluated before these patterns, so a legitimate video/folder sidecar is
    # preserved even if its name contains one of those tokens.
    JUNK_PATTERNS = [
        r".*sample.*",
        r".*proof.*",
        r".*trailer.*",
        r"RARBG.*",
        r".*readme.*",
        r".*www\..*",
        r".*Proxies.*",
    ]

    VIDEO_EXTENSIONS = {
        ".mkv",
        ".mp4",
        ".avi",
        ".m4v",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".mpg",
        ".mpeg",
        ".m2ts",
        ".ts",
    }

    WHITELIST = {
        "folder.jpg",
        "folder.jpeg",
        "folder.png",
        "poster.jpg",
        "poster.jpeg",
        "poster.png",
    }

    @classmethod
    def is_junk_file(
        cls,
        filename: str,
        filepath: str,
        video_basenames: list[str] | None = None,
        folder_name: str | None = None,
    ) -> dict[str, Any]:
        """Return whether ``filename`` should be reviewed for deletion."""
        del filepath  # kept for source parity and future path-aware rules
        filename_lower = filename.lower()
        video_basenames = video_basenames or []

        if cls.is_video_file(filename):
            return {"is_junk": False, "reason": None}

        if filename_lower in cls.WHITELIST:
            return {"is_junk": False, "reason": None}

        # Recognised metadata extensions (images, XML sidecars) are evaluated before
        # generic junk patterns. A file whose basename matches the protected video or
        # folder is a tracked companion and must not be discarded merely because its
        # name also contains a release provenance token.
        file_ext = next(
            (ext for ext in cls.METADATA_EXTENSIONS if filename_lower.endswith(ext)),
            None,
        )
        metadata_basename: str | None = None
        if file_ext is not None:
            metadata_basename = filename[: -len(file_ext)]
            if cls._is_kept_metadata(metadata_basename, video_basenames, folder_name):
                return {"is_junk": False, "reason": None}

        for pattern in cls.JUNK_PATTERNS:
            # ``re.IGNORECASE`` so uppercase scene tags (RARBG/Proxies) still match
            # after ``filename`` has been lower-cased.
            if re.match(pattern, filename_lower, re.IGNORECASE):
                return {
                    "is_junk": True,
                    "reason": f"Junk pattern: {pattern.replace('.*', '')}",
                }

        if any(filename_lower.endswith(ext) for ext in cls.JUNK_EXTENSIONS):
            return {"is_junk": True, "reason": "Junk file extension"}

        if metadata_basename is not None:
            return {
                "is_junk": True,
                "reason": "Metadata file not matching video or folder",
            }

        return {"is_junk": False, "reason": None}

    # Artwork the media managers (Kodi/Plex/Jellyfin/Emby) create with a fixed name
    # rather than the title, plus the "<title>-<suffix>" sidecar convention.
    ARTWORK_NAMES = {
        "fanart",
        "banner",
        "backdrop",
        "clearart",
        "clearlogo",
        "logo",
        "disc",
        "discart",
        "landscape",
        "thumb",
        "keyart",
        "characterart",
        "cover",
        "poster",
        "folder",
    }

    ARTWORK_SUFFIXES = {
        "poster",
        "fanart",
        "banner",
        "thumb",
        "landscape",
        "clearlogo",
        "clearart",
        "logo",
        "disc",
        "discart",
        "backdrop",
        "keyart",
    }

    _SEASON_ARTWORK = re.compile(
        r"^season(?:\d{1,3}|-all|-specials)(?:-(?:poster|banner|fanart|landscape))?$"
    )

    @classmethod
    def _is_kept_metadata(
        cls,
        file_basename: str,
        video_basenames: list[str],
        folder_name: str | None,
    ) -> bool:
        """Return whether an image/xml sidecar is a recognised companion to keep.

        Comparisons are case-insensitive. A file is kept when its basename matches a
        video basename or the folder name, is a recognised metadata identity for
        either, is a well-known artwork name (e.g. ``fanart``), a season-poster style
        name, or follows the ``<title>-<suffix>`` artwork convention (e.g.
        ``Movie-poster``). Identity matching takes precedence over generic junk
        patterns, so a Radarr-generated XML sidecar whose basename equals the
        protected video is kept even when the name contains release provenance such
        as ``YTS`` or ``YIFY``. This is intentionally not a blanket image/XML
        exemption: unrelated metadata remains reviewable.
        """
        base_keys = cls._metadata_identity_keys(file_basename)
        videos = {
            key
            for video in video_basenames
            for key in cls._metadata_identity_keys(video)
        }
        folder_keys = (
            cls._metadata_identity_keys(folder_name)
            if folder_name is not None
            else set()
        )

        if base_keys & videos:
            return True
        if base_keys & folder_keys:
            return True
        base = file_basename.lower()
        if base in cls.ARTWORK_NAMES:
            return True
        if cls._SEASON_ARTWORK.match(base):
            return True
        for suffix in cls.ARTWORK_SUFFIXES:
            marker = f"-{suffix}"
            if base.endswith(marker):
                stem = base[: -len(marker)]
                stem_keys = cls._metadata_identity_keys(stem)
                if stem_keys & videos or stem_keys & folder_keys:
                    return True
        return False

    @classmethod
    def _metadata_identity_keys(cls, name: str) -> set[str]:
        """Return conservative comparison keys for companion metadata names."""
        lowered = name.lower().strip()
        keys = {lowered}

        without_brace_tags = re.sub(r"\{[^}]*\}", "", lowered)
        without_brace_tags = cls._collapse_metadata_separators(without_brace_tags)
        if without_brace_tags:
            keys.add(without_brace_tags)

        return keys

    @staticmethod
    def _collapse_metadata_separators(name: str) -> str:
        """Collapse separator noise left after removing media-manager tags."""
        collapsed = re.sub(r"\s+", " ", name)
        collapsed = re.sub(r"\s+([)\]])", r"\1", collapsed)
        collapsed = re.sub(r"([(])\s+", r"\1", collapsed)
        collapsed = re.sub(r"\s*-\s*", " - ", collapsed)
        collapsed = re.sub(r"(?:\s+-\s+)+$", "", collapsed)
        return collapsed.strip(" ._-")

    @classmethod
    def is_video_file(cls, filename: str) -> bool:
        """Return whether ``filename`` has a protected video extension."""
        filename_lower = filename.lower()
        return any(filename_lower.endswith(ext) for ext in cls.VIDEO_EXTENSIONS)

    @classmethod
    def is_junk_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` should be flagged as junk."""
        return folder_name.lower() in cls.JUNK_FOLDERS

    # Common title stop-words dropped before word-overlap so a terse scene name
    # still clears the bar (e.g. "LOTR" for "The Lord of the Rings").
    _STOP_WORDS = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "over",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "by",
        "at",
    }

    @classmethod
    def video_matches_folder(cls, video_filename: str, folder_name: str) -> bool:
        """Return whether a movie filename appears to belong to its folder."""
        folder_clean = folder_name.lower()
        video_lower = video_filename.lower()

        # A matching release year is a near-certain identity signal, so accept it
        # before any word matching (handles abbreviated/foreign/tagged names).
        year_match = re.search(r"\b(?:19|20)\d{2}\b", folder_clean)
        if year_match and year_match.group(0) in video_lower:
            return True

        # Strip every brace tag ({tmdb-..}/{imdb-..}/{edition-..}) and the year so
        # they cannot pad the denominator, then drop stop-words.
        folder_clean = re.sub(r"\{[^}]*\}", "", folder_clean)
        folder_clean = re.sub(r"\(\d{4}\)", "", folder_clean)
        folder_clean = re.sub(r"[{}\[\]()]", "", folder_clean).strip()
        folder_words = [
            word
            for word in folder_clean.split()
            if len(word) > 2 and word not in cls._STOP_WORDS
        ]
        if not folder_words:
            return True

        matches = sum(1 for word in folder_words if word in video_lower)
        return matches / len(folder_words) >= 0.5

    # Localised "season" words plus the short "S01" form; trailing text after the
    # number is tolerated (e.g. "Season 01 - Title", "Season 1 (2019)", "Staffel 1").
    _SEASON_FOLDER = re.compile(
        r"^(?:season|series|saison|staffel|temporada|stagione|seizoen|sezon)"
        r"[ ._-]*\d{1,3}\b",
        re.IGNORECASE,
    )
    _SEASON_SHORT = re.compile(r"^s\d{1,3}$", re.IGNORECASE)
    _SPECIALS_FOLDER = re.compile(r"^season[ ._-]*0+$", re.IGNORECASE)

    @classmethod
    def is_tv_season_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` looks like a TV season folder.

        Accepts the English ``Season NN`` plus common localised words, the short
        ``S01`` form, no-space/underscore variants, and trailing suffixes.
        """
        return bool(
            cls._SEASON_FOLDER.match(folder_name)
            or cls._SEASON_SHORT.match(folder_name)
        )

    @classmethod
    def is_tv_specials_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` looks like a TV specials folder.

        Recognises any all-zero season number (``Season 0``, ``Season 00``), the
        word ``specials`` in any variant that contains it, and the localised
        ``especiales``/``especiais`` spellings.
        """
        name_lower = folder_name.lower()
        return (
            "specials" in name_lower
            or "especiales" in name_lower
            or "especiais" in name_lower
            or bool(cls._SPECIALS_FOLDER.match(folder_name))
        )

    # Episode-number signatures Sonarr/Jellyfin actually produce. A filename
    # carrying any of these is treated as a validly-named episode; the show name is
    # no longer required to match, so terse/abbreviated but correct names are kept
    # instead of being flagged (a video is never worth an auto-delete on a fuzzy
    # name miss).
    _EPISODE_SIGNATURES = (
        re.compile(r"s\d{1,4}[ ._-]?e\d{1,4}", re.IGNORECASE),  # S01E01, S1E1, S01 E01
        re.compile(r"\b\d{1,2}x\d{2,3}\b", re.IGNORECASE),  # 1x05, 12x005
        re.compile(r"\b\d{4}[ ._-]\d{1,2}[ ._-]\d{1,2}\b"),  # 2024-06-01 daily
        re.compile(r"[ ._]-[ ._]?\d{1,4}\b"),  # "Show - 1071" anime absolute
    )

    @classmethod
    def is_valid_tv_episode(cls, filename: str, show_folder_name: str) -> bool:
        """Return whether a filename carries a recognised episode signature.

        Accepts ``SxxExx``, ``NxNN``, date-based (daily), and the ``Show - 1071``
        absolute-numbering convention. The show name is not required to match, so a
        correctly-numbered but terse filename is kept rather than flagged.
        """
        del show_folder_name  # kept for source parity; no longer used for matching
        return any(pattern.search(filename) for pattern in cls._EPISODE_SIGNATURES)
