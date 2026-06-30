"""Typed Deletarr scan models shared by the scanner and engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LibraryType = Literal["movies", "tv"]
ItemKind = Literal["file", "folder"]

LIBRARY_TYPES: tuple[LibraryType, ...] = ("movies", "tv")
LIBRARY_LABELS: dict[LibraryType, str] = {
    "movies": "Movies",
    "tv": "TV Shows",
}


def normalise_library_type(value: str) -> LibraryType:
    """Return a supported library type or raise ``ValueError``."""
    if value in LIBRARY_TYPES:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported library type: {value}")


@dataclass(frozen=True)
class VideoReference:
    """A protected video file shown as context for junk sidecars."""

    name: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "size": self.size}


@dataclass
class ScanItem:
    """One file or folder that Deletarr has flagged for review."""

    path: str
    name: str
    type: ItemKind
    size: int
    reason: str
    parent: str
    movie_folder: str | None = None
    movie_folder_path: str | None = None
    is_checked: bool = True
    videos_in_folder: list[VideoReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "name": self.name,
            "type": self.type,
            "size": self.size,
            "reason": self.reason,
            "parent": self.parent,
            "movie_folder": self.movie_folder,
            "movie_folder_path": self.movie_folder_path,
            "is_checked": self.is_checked,
            "videos_in_folder": [video.to_dict() for video in self.videos_in_folder],
        }


@dataclass(frozen=True)
class ScanStats:
    """Aggregate statistics for one Deletarr library."""

    total_files: int
    total_folders: int
    total_size: int
    is_scanning: bool
    scan_progress: int

    def to_dict(self) -> dict[str, object]:
        return {
            "total_files": self.total_files,
            "total_folders": self.total_folders,
            "total_size": self.total_size,
            "is_scanning": self.is_scanning,
            "scan_progress": self.scan_progress,
        }


def stats_for(items: list[ScanItem], *, is_scanning: bool, scan_progress: int) -> ScanStats:
    """Build aggregate scan statistics for ``items``."""
    files = [item for item in items if item.type == "file"]
    folders = [item for item in items if item.type == "folder"]
    return ScanStats(
        total_files=len(files),
        total_folders=len(folders),
        total_size=sum(item.size for item in items),
        is_scanning=is_scanning,
        scan_progress=scan_progress,
    )
