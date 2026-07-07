"""Deletarr engine: scan, delete, settings, and status operations."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.app_metrics import record_deletarr_delete, record_deletarr_scan
from core.context import SyncAlreadyRunning
from core.logging import get_logger
from modules.deletarr.arr_source import client_for
from modules.deletarr.manifest import (
    LibraryManifest,
    build_movie_manifest,
    build_tv_manifest,
)
from modules.deletarr.models import (
    LIBRARY_LABELS,
    LibraryType,
    ScanItem,
    ScanMode,
    normalise_library_type,
    stats_for,
)
from modules.deletarr.scanner import MediaScanner

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("deletarr")


@dataclass
class LibraryState:
    """Mutable in-memory scan state for one Deletarr library."""

    library_type: LibraryType
    path: str
    results: list[ScanItem] = field(default_factory=list)
    is_scanning: bool = False
    scan_progress: int = 0
    last_scan_at: str | None = None
    last_error: str | None = None
    # How the last scan was produced and whether the matching Arr was reachable.
    scan_mode: ScanMode = "heuristic"
    arr_available: bool = False
    arr_detail: str | None = None


class DeletarrService:
    """Owns Deletarr state and filesystem operations for one app process."""

    def __init__(self, ctx: AppContext) -> None:
        settings = ctx.settings_store.deletarr_settings()
        self._ctx = ctx
        self._states: dict[LibraryType, LibraryState] = {
            "movies": LibraryState("movies", settings["movies_path"]),
            "tv": LibraryState("tv", settings["tv_path"]),
        }

    async def status(self) -> dict:
        """Return settings plus per-library scan status."""
        return {
            "settings": self.settings(),
            "libraries": {
                library_type: self._state_payload(state)
                for library_type, state in self._states.items()
            },
        }

    async def results(self, library_type: str) -> dict:
        """Return current results for one library."""
        state = self._state(normalise_library_type(library_type))
        return {
            "type": state.library_type,
            "path": state.path,
            "scan_mode": state.scan_mode,
            "arr_available": state.arr_available,
            "arr_detail": state.arr_detail,
            "results": [item.to_dict() for item in state.results],
            "stats": stats_for(
                state.results,
                is_scanning=state.is_scanning,
                scan_progress=state.scan_progress,
            ).to_dict(),
        }

    async def scan(self, library_type: str) -> dict:
        """Run a read-only filesystem scan for one library."""
        selected = normalise_library_type(library_type)

        async def run_scan() -> dict:
            state = self._state(selected)
            state.is_scanning = True
            state.scan_progress = 0
            state.last_error = None
            try:
                scanner = MediaScanner([state.path])
                manifest = await self._resolve_manifest(selected, state)
                if manifest is not None and manifest.folders:
                    await asyncio.to_thread(scanner.scan_arr, manifest)
                    state.scan_mode = "arr"
                else:
                    await asyncio.to_thread(scanner.scan, selected)
                    state.scan_mode = "heuristic"
                state.results = scanner.get_sorted_results()
                state.scan_progress = 100
                state.last_scan_at = _now_iso()
                record_deletarr_scan(
                    library=selected,
                    mode=state.scan_mode,
                    status="success",
                    results_count=len(state.results),
                )
                detail = (
                    f"Found {len(state.results)} junk item(s) in "
                    f"{LIBRARY_LABELS[selected]} ({state.scan_mode} scan)."
                )
                self._ctx.db.add_activity("Deletarr scan completed", detail)
                return await self.results(selected)
            except Exception as exc:
                state.last_error = str(exc)
                record_deletarr_scan(
                    library=selected,
                    mode=state.scan_mode,
                    status="error",
                )
                self._ctx.db.add_activity(
                    "Deletarr scan failed",
                    f"{LIBRARY_LABELS[selected]} scan failed: {exc}",
                )
                raise
            finally:
                state.is_scanning = False

        try:
            return await self._ctx.deletarr_gate.try_run(run_scan)
        except SyncAlreadyRunning:
            raise

    async def delete(self, library_type: str, paths: list[str]) -> dict:
        """Delete reviewed scan-result paths from one library."""
        selected = normalise_library_type(library_type)

        async def run_delete() -> dict:
            state = self._state(selected)
            tracked: set[str] = set()
            if state.scan_mode == "arr":
                manifest = await self._build_manifest(selected, state.path)
                if manifest.available:
                    tracked = manifest.media_paths
            result = await asyncio.to_thread(self._delete_sync, state, paths, tracked)
            record_deletarr_delete(
                library=selected,
                deleted=int(result["deleted"]),
                failed=int(result["failed"]),
                freed_bytes=int(result["freed_bytes"]),
            )
            self._ctx.db.add_activity(
                "Deletarr delete completed",
                (
                    f"Deleted {result['deleted']} item(s) from "
                    f"{LIBRARY_LABELS[selected]}, freeing {result['freed_formatted']}."
                ),
            )
            return result

        try:
            return await self._ctx.deletarr_gate.try_run(run_delete)
        except SyncAlreadyRunning:
            raise

    def settings(self) -> dict[str, str]:
        """Return current Deletarr path settings."""
        return self._ctx.settings_store.deletarr_settings()

    async def update_settings(
        self,
        *,
        movies_path: str | None = None,
        tv_path: str | None = None,
        use_arr_source: bool | None = None,
    ) -> dict:
        """Persist path/source settings and update live state paths."""
        settings = self._ctx.settings_store.update_deletarr_settings(
            movies_path=movies_path,
            tv_path=tv_path,
            use_arr_source=use_arr_source,
        )
        self._states["movies"].path = settings["movies_path"]
        self._states["tv"].path = settings["tv_path"]
        self._ctx.db.add_activity("Deletarr settings saved", "Deletarr paths updated")
        return await self.status()

    async def _resolve_manifest(
        self, selected: LibraryType, state: LibraryState
    ) -> LibraryManifest | None:
        """Build the Arr manifest for a scan, honouring the ``use_arr_source`` toggle.

        Returns the manifest when the matching Arr is reachable, or ``None`` so the
        caller falls back to the heuristic scan. Records reachability on ``state``.
        """
        settings = self._ctx.settings_store.deletarr_settings()
        if not settings.get("use_arr_source", True):
            state.arr_available = False
            state.arr_detail = "Arr source disabled"
            return None
        manifest = await self._build_manifest(selected, state.path)
        state.arr_available = manifest.available
        state.arr_detail = manifest.detail
        return manifest if manifest.available else None

    async def _build_manifest(
        self, selected: LibraryType, local_root: str
    ) -> LibraryManifest:
        """Fetch and translate the Radarr/Sonarr keep-set for one library."""
        client = client_for(self._ctx, selected)
        try:
            if selected == "movies":
                return await build_movie_manifest(client, local_root)
            return await build_tv_manifest(client, local_root)
        finally:
            await client.aclose()

    def _delete_sync(
        self, state: LibraryState, paths: list[str], tracked: set[str] | None = None
    ) -> dict:
        tracked = tracked or set()
        current = {item.path: item for item in state.results}
        deleted: list[str] = []
        failed: list[dict[str, str]] = []
        total_freed = 0

        for path in paths:
            item = current.get(path)
            if item is None:
                failed.append({"path": path, "error": "Not in scan results"})
                continue

            normalised = os.path.normpath(path)
            if normalised in tracked or self._covers_tracked(normalised, tracked):
                failed.append({"path": path, "error": "Now tracked by Radarr/Sonarr"})
                continue

            validation_error = self._validate_delete_path(state.path, path)
            if validation_error is not None:
                failed.append({"path": path, "error": validation_error})
                continue

            try:
                if os.path.isfile(path):
                    size = os.path.getsize(path)
                    os.remove(path)
                elif os.path.isdir(path):
                    size = self._folder_size(path)
                    shutil.rmtree(path)
                else:
                    failed.append({"path": path, "error": "Path no longer exists"})
                    continue
                total_freed += size
                deleted.append(path)
                _log.info("deleted Deletarr item: %s", path)
            except Exception as exc:
                failed.append({"path": path, "error": str(exc)})

        if deleted:
            deleted_set = set(deleted)
            state.results = [
                item for item in state.results if item.path not in deleted_set
            ]

        return {
            "success": len(failed) == 0,
            "deleted": len(deleted),
            "failed": len(failed),
            "freed_bytes": total_freed,
            "freed_mb": round(total_freed / (1024 * 1024), 2),
            "freed_formatted": format_size(total_freed),
            "deleted_paths": deleted,
            "errors": failed,
        }

    @staticmethod
    def _covers_tracked(path: str, tracked: set[str]) -> bool:
        """Whether ``path`` is a directory that contains a currently-tracked file.

        The exact-match case is handled by the caller's ``in tracked`` check; this
        catches deleting a whole folder that the Arr has begun tracking a file
        inside of between scan and delete.
        """
        candidate = Path(path)
        return any(Path(entry).is_relative_to(candidate) for entry in tracked)

    @staticmethod
    def _validate_delete_path(root: str, path: str) -> str | None:
        try:
            root_path = Path(root).resolve(strict=True)
        except OSError:
            return "Configured library path does not exist"
        try:
            candidate = Path(path).resolve(strict=True)
        except OSError:
            return "Path no longer exists"
        try:
            candidate.relative_to(root_path)
        except ValueError:
            return "Path is outside configured library"
        return None

    @staticmethod
    def _folder_size(folder_path: str) -> int:
        total_size = 0
        for dirpath, _, filenames in os.walk(folder_path):
            for filename in filenames:
                try:
                    total_size += os.path.getsize(os.path.join(dirpath, filename))
                except OSError:
                    continue
        return total_size

    def _state(self, library_type: LibraryType) -> LibraryState:
        return self._states[library_type]

    @staticmethod
    def _state_payload(state: LibraryState) -> dict:
        return {
            "type": state.library_type,
            "path": state.path,
            "last_scan_at": state.last_scan_at,
            "last_error": state.last_error,
            "scan_mode": state.scan_mode,
            "arr_available": state.arr_available,
            "arr_detail": state.arr_detail,
            "results_count": len(state.results),
            "stats": stats_for(
                state.results,
                is_scanning=state.is_scanning,
                scan_progress=state.scan_progress,
            ).to_dict(),
        }


def format_size(bytes_size: int) -> str:
    """Format a byte count for Deletarr API responses."""
    size = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
