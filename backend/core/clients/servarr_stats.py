"""Read-only Sonarr/Radarr statistics client for the dashboard.

Every endpoint here is part of the Servarr v3 contract shared by Sonarr v4 and
Radarr v6 (confirmed against each project's published OpenAPI document):

* ``GET /api/v3/series`` (Sonarr): ``monitored`` and ``statistics.{episodeCount,
  episodeFileCount, sizeOnDisk}`` per series.
* ``GET /api/v3/movie`` (Radarr): ``monitored``, ``hasFile`` and ``sizeOnDisk``
  per movie.
* ``GET /api/v3/diskspace``: ``{path, label, freeSpace, totalSpace}`` per mount.
  Preferred over ``/rootfolder``, whose Radarr shape has no ``totalSpace``.
* ``GET /api/v3/queue`` and ``GET /api/v3/wanted/missing``: paging resources
  whose ``totalRecords`` is read with ``pageSize=1``, so no records are sent.

Payloads are parsed defensively: non-dict rows are skipped and missing numbers
count as 0, while a top-level payload of the wrong type raises
:class:`ServarrStatsError` so the dashboard marks the source offline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.clients.servarr import ServarrClient, ServarrClientError
from core.coerce import coerce_int

if TYPE_CHECKING:  # pragma: no cover
    from core.clients.arr_client import ArrClient

# Paging query that returns ``totalRecords`` with a single (ignored) record.
_COUNT_ONLY = {"page": 1, "pageSize": 1}


class ServarrStatsError(ServarrClientError):
    """Raised when a Sonarr/Radarr statistics request cannot be completed."""


class ServarrStatsClient(ServarrClient):
    """Read-only client for the Sonarr/Radarr figures the dashboard shows."""

    error_class = ServarrStatsError
    feature_name = "Dashboard"

    async def _list(self, path: str) -> list[dict[str, Any]]:
        """GET a list endpoint, raising when the payload is not a JSON list."""
        data = await self._request("GET", path)
        if not isinstance(data, list):
            raise self.error_class(f"{self.app} returned an invalid {path} payload")
        return self._as_dicts(data)

    async def _total_records(self, path: str) -> int:
        """Return a paging endpoint's ``totalRecords`` (list length as fallback)."""
        data = await self._request("GET", path, params=_COUNT_ONLY)
        if isinstance(data, dict):
            return coerce_int(data.get("totalRecords"), 0)
        if isinstance(data, list):
            return len(data)
        raise self.error_class(f"{self.app} returned an invalid {path} payload")

    async def library_stats(self) -> dict[str, int]:
        """Return library totals: series/episodes for Sonarr, movies for Radarr.

        Sonarr keys: ``series_total``, ``series_monitored``, ``episodes_total``
        (monitored, aired episodes), ``episodes_with_files``,
        ``size_on_disk_bytes``. Radarr keys: ``movies_total``,
        ``movies_monitored``, ``movies_with_files``, ``size_on_disk_bytes``.
        """
        if self.app == "sonarr":
            return _sonarr_library(await self._list("/api/v3/series"))
        return _radarr_library(await self._list("/api/v3/movie"))

    async def disk_space(self) -> list[dict[str, Any]]:
        """Return ``{path, label, free_bytes, total_bytes}`` per mount, by path.

        Rows without a path are skipped; a path reported twice keeps its first row.
        """
        disks: dict[str, dict[str, Any]] = {}
        for row in await self._list("/api/v3/diskspace"):
            path = row.get("path")
            if not isinstance(path, str) or not path or path in disks:
                continue
            label = row.get("label")
            disks[path] = {
                "path": path,
                "label": label if isinstance(label, str) and label else None,
                "free_bytes": coerce_int(row.get("freeSpace"), 0),
                "total_bytes": coerce_int(row.get("totalSpace"), 0),
            }
        return list(disks.values())

    async def queue_total(self) -> int:
        """Return the number of items in the download queue."""
        return await self._total_records("/api/v3/queue")

    async def missing_total(self) -> int:
        """Return the number of monitored, missing episodes or movies."""
        return await self._total_records("/api/v3/wanted/missing")


def _sonarr_library(series: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate Sonarr series rows into library totals."""
    totals = {
        "series_total": len(series),
        "series_monitored": 0,
        "episodes_total": 0,
        "episodes_with_files": 0,
        "size_on_disk_bytes": 0,
    }
    for row in series:
        if row.get("monitored") is True:
            totals["series_monitored"] += 1
        statistics = row.get("statistics")
        if not isinstance(statistics, dict):
            continue
        totals["episodes_total"] += coerce_int(statistics.get("episodeCount"), 0)
        totals["episodes_with_files"] += coerce_int(
            statistics.get("episodeFileCount"), 0
        )
        totals["size_on_disk_bytes"] += coerce_int(statistics.get("sizeOnDisk"), 0)
    return totals


def _radarr_library(movies: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate Radarr movie rows into library totals."""
    return {
        "movies_total": len(movies),
        "movies_monitored": sum(1 for row in movies if row.get("monitored") is True),
        "movies_with_files": sum(1 for row in movies if row.get("hasFile") is True),
        "size_on_disk_bytes": sum(
            coerce_int(row.get("sizeOnDisk"), 0) for row in movies
        ),
    }


def stats_client_for(source: ArrClient, *, app: str) -> ServarrStatsClient:
    """Build a statistics client from the live Sonarr/Radarr connection fields.

    The caller owns the returned client and must ``aclose()`` it.
    """
    fields = source.connection_fields()
    return ServarrStatsClient(
        app=app, base_url=fields["base_url"], api_key=fields["api_key"]
    )
