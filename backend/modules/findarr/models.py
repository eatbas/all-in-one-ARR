"""Shared Findarr domain models."""

from __future__ import annotations

from dataclasses import dataclass

APP_NAMES = ("sonarr", "radarr")
MODES = ("missing", "upgrade")


@dataclass(frozen=True)
class FindarrItem:
    """One Sonarr/Radarr item eligible for a Findarr search."""

    app: str
    mode: str
    item_id: str
    title: str
    monitored: bool
    is_future: bool


@dataclass(frozen=True)
class Compatibility:
    """Connected Servarr application compatibility result."""

    ok: bool
    app_name: str
    version: str
    detail: str


@dataclass
class ModeResult:
    """Result of one app/mode processing slice."""

    app: str
    mode: str
    scanned: int = 0
    selected: int = 0
    processed: int = 0
    skipped: int = 0
    detail: str = ""


@dataclass
class RunResult:
    """Aggregate Findarr run result."""

    status: str
    detail: str
    processed: int = 0
    results: list[ModeResult] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "processed": self.processed,
            "results": [item.__dict__ for item in self.results or []],
        }
