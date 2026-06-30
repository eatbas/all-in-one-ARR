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

    JUNK_PATTERNS = [
        r".*sample.*",
        r".*proof.*",
        r".*trailer.*",
        r"RARBG.*",
        r".*readme.*",
        r".*YTS.*",
        r".*YIFY.*",
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

        for pattern in cls.JUNK_PATTERNS:
            if re.match(pattern, filename_lower):
                return {
                    "is_junk": True,
                    "reason": f'Junk pattern: {pattern.replace(".*", "")}',
                }

        if any(filename_lower.endswith(ext) for ext in cls.JUNK_EXTENSIONS):
            return {"is_junk": True, "reason": "Junk file extension"}

        file_ext = next(
            (ext for ext in cls.METADATA_EXTENSIONS if filename_lower.endswith(ext)),
            None,
        )
        if file_ext is not None:
            file_basename = filename[: -len(file_ext)]
            if any(file_basename == video_base for video_base in video_basenames):
                return {"is_junk": False, "reason": None}
            if folder_name and file_basename == folder_name:
                return {"is_junk": False, "reason": None}
            return {
                "is_junk": True,
                "reason": "Metadata file not matching video or folder",
            }

        return {"is_junk": False, "reason": None}

    @classmethod
    def is_video_file(cls, filename: str) -> bool:
        """Return whether ``filename`` has a protected video extension."""
        filename_lower = filename.lower()
        return any(filename_lower.endswith(ext) for ext in cls.VIDEO_EXTENSIONS)

    @classmethod
    def is_junk_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` should be flagged as junk."""
        return folder_name.lower() in cls.JUNK_FOLDERS

    @classmethod
    def video_matches_folder(cls, video_filename: str, folder_name: str) -> bool:
        """Return whether a movie filename appears to belong to its folder."""
        folder_clean = folder_name.lower()
        folder_clean = re.sub(r"\{tmdb-\d+\}", "", folder_clean)
        folder_clean = re.sub(r"\(\d{4}\)", "", folder_clean)
        folder_clean = re.sub(r"[{}\[\]()]", "", folder_clean).strip()
        folder_words = [word.strip() for word in folder_clean.split() if len(word.strip()) > 2]
        if not folder_words:
            return True

        video_lower = video_filename.lower()
        matches = sum(1 for word in folder_words if word in video_lower)
        return matches / len(folder_words) >= 0.5

    @classmethod
    def is_tv_season_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` looks like a TV season folder."""
        return bool(re.match(r"^Season \d+$", folder_name, re.IGNORECASE))

    @classmethod
    def is_tv_specials_folder(cls, folder_name: str) -> bool:
        """Return whether ``folder_name`` looks like a TV specials folder."""
        name_lower = folder_name.lower()
        return (
            name_lower == "specials"
            or name_lower == "season 00"
            or "specials" in name_lower
        )

    @classmethod
    def is_valid_tv_episode(cls, filename: str, show_folder_name: str) -> bool:
        """Return whether an episode filename matches the show and SxxExx pattern."""
        if not re.search(r"S\d+E\d+", filename, re.IGNORECASE):
            return False

        clean_show = re.sub(
            r"\{(?:tmdb|tvdb)-\d+\}", "", show_folder_name, flags=re.IGNORECASE
        )
        clean_show = re.sub(r"\(\d{4}\)", "", clean_show).strip()
        show_words = [word.lower() for word in clean_show.split() if len(word) > 2]
        if not show_words:
            return True

        filename_lower = filename.lower()
        matches = sum(1 for word in show_words if word in filename_lower)
        return matches / len(show_words) >= 0.75
