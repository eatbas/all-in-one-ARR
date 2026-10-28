"""Async Servarr API helper used by Cleanarr.

Contract relied on (Sonarr 4 / Radarr 6, ``/api/v3``); see the plan's "Assumed
external contracts" and its Manual verification section:

* ``GET /api/v3/queue?page=&pageSize=&includeUnknownSeriesItems=true`` (Sonarr) or
  ``includeUnknownMovieItems=true`` (Radarr) → ``{totalRecords, records[]}``. Each
  record's ``id``, ``downloadId``, ``protocol``, ``downloadClient``, ``title``,
  ``status``, ``trackedDownloadStatus``, ``trackedDownloadState``,
  ``statusMessages[{title, messages[]}]`` and ``outputPath`` are read. The
  ``statusMessages`` shape is verified (Context7, Sonarr
  ``TrackedDownloadStatusMessage``); the other field names are **unverified**.
* ``DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=true&skipRedownload=false``
  removes, blocklists and re-searches; 404 means the item is already gone
  (**unverified** query names).
* ``GET /api/v3/config/downloadclient`` → ``enableCompletedDownloadHandling``,
  ``autoRedownloadFailed``; ``GET /api/v3/downloadclient`` → clients with
  ``implementation`` and ``removeFailedDownloads`` / ``removeCompletedDownloads``
  (**unverified**).

Every field read is isolated here and parsed tolerantly. A record with a
usable ``downloadId`` but no usable ``id`` is kept with ``queue_id`` ``None``:
it cannot be removed itself, but its state and title still protect its
download. A record without a usable ``downloadId`` keeps only its
``outputPath`` as a folder reference, and missing handling fields become
``None``. A malformed record or ``outputPath`` marks the read's references
incomplete, and a record tied to neither a download nor a folder (including
an ``outputPath`` such as ``/`` that names no folder) marks its downloads
incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.clients.servarr import ServarrClient, ServarrClientError
from modules.cleanarr.models import ArrDownloadHandling, ArrQueue, QueueItem
from modules.cleanarr.paths import folder_name

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_QUEUE_PAGE_SIZE = 100

# The per-app flag that includes queue items Sonarr/Radarr could not match to a
# series or movie; those are exactly the stuck imports Cleanarr must see.
_UNKNOWN_ITEMS_PARAM = {
    "sonarr": "includeUnknownSeriesItems",
    "radarr": "includeUnknownMovieItems",
}

_REMOVE_PARAMS = {
    "removeFromClient": "true",
    "blocklist": "true",
    "skipRedownload": "false",
}


class CleanarrClientError(ServarrClientError):
    """Raised when a Sonarr/Radarr API request for Cleanarr cannot be completed."""


def _text(value: Any) -> str:
    """Return a stripped string, or ``""`` for anything else."""
    return value.strip() if isinstance(value, str) else ""


def _flatten_messages(value: Any) -> tuple[str, ...]:
    """Flatten ``statusMessages[{title, messages[]}]`` into one tuple of strings."""
    if not isinstance(value, list):
        return ()
    flattened: list[str] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title"))
        if title:
            flattened.append(title)
        messages = entry.get("messages")
        if isinstance(messages, list):
            flattened.extend(text for text in map(_text, messages) if text)
    return tuple(flattened)


def _queue_id(value: Any) -> int | None:
    """Return a record's ``id`` when it is an integer (not a bool), else ``None``."""
    return None if isinstance(value, bool) or not isinstance(value, int) else value


def _queue_item(app: str, record: dict[str, Any]) -> QueueItem | None:
    """Return a :class:`QueueItem`, or ``None`` without a usable ``downloadId``.

    An unusable ``id`` only makes the item non-actionable (``queue_id``
    ``None``); its download protection fields are still read.
    """
    download_id = _text(record.get("downloadId"))
    if not download_id:
        return None
    return QueueItem(
        app=app,
        queue_id=_queue_id(record.get("id")),
        download_id=download_id,
        protocol=_text(record.get("protocol")).lower(),
        download_client=_text(record.get("downloadClient")),
        title=_text(record.get("title")),
        status=_text(record.get("status")),
        tracked_status=_text(record.get("trackedDownloadStatus")).lower(),
        tracked_state=_text(record.get("trackedDownloadState")),
        messages=_flatten_messages(record.get("statusMessages")),
        output_path=_text(record.get("outputPath")),
    )


def _output_path(record: Any) -> str | None:
    """Return a record's ``outputPath`` (``""`` when absent), or ``None`` when unreadable.

    A record that is not an object, or an ``outputPath`` that is neither a
    string nor ``null``, hides which folder the record refers to.
    """
    if not isinstance(record, dict):
        return None
    value = record.get("outputPath")
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else None


@dataclass
class _QueueReader:
    """Accumulates queue pages into an :class:`ArrQueue`."""

    app: str
    items: list[QueueItem] = field(default_factory=list)
    unparsed_output_paths: list[str] = field(default_factory=list)
    readable: bool = True
    associated: bool = True

    def add(self, records: list[Any]) -> None:
        """Parse one page: records of a download become items, the rest references.

        A record without a usable ``downloadId`` and without an ``outputPath``
        naming a folder (see :func:`~modules.cleanarr.paths.folder_name`; ``/``
        names none) cannot be tied to any download or folder.
        """
        for record in records:
            output_path = _output_path(record)
            self.readable = self.readable and output_path is not None
            item = _queue_item(self.app, record) if isinstance(record, dict) else None
            if item is not None:
                self.items.append(item)
            elif output_path is not None and folder_name(output_path) is not None:
                self.unparsed_output_paths.append(output_path)
            else:
                self.associated = False

    def result(self, *, reached_total: bool) -> ArrQueue:
        """Return the read; each completeness flag needs every page to be complete."""
        return ArrQueue(
            items=tuple(self.items),
            unparsed_output_paths=tuple(self.unparsed_output_paths),
            references_complete=self.readable and reached_total,
            downloads_complete=self.associated and reached_total,
        )


def _optional_bool(value: Any) -> bool | None:
    """Return ``value`` when it is a bool, else ``None``."""
    return value if isinstance(value, bool) else None


def _all_known(values: list[bool | None]) -> bool | None:
    """Return ``all(values)`` over the known values, or ``None`` if none are known."""
    known = [value for value in values if value is not None]
    return all(known) if known else None


class CleanarrArrClient(ServarrClient):
    """Small client for the Sonarr/Radarr endpoints Cleanarr needs."""

    error_class = CleanarrClientError
    feature_name = "Cleanarr"

    async def read_queue(self) -> ArrQueue:
        """Return the whole queue, paging until ``totalRecords`` or an empty page.

        An empty page short of ``totalRecords`` ends the read with its
        references marked incomplete.
        """
        reader = _QueueReader(self.app)
        seen = 0
        page = 1
        while True:
            data = await self._request(
                "GET",
                "/api/v3/queue",
                params={
                    "page": page,
                    "pageSize": _QUEUE_PAGE_SIZE,
                    _UNKNOWN_ITEMS_PARAM.get(self.app, "includeUnknownSeriesItems"): (
                        "true"
                    ),
                },
            )
            records = data.get("records") if isinstance(data, dict) else None
            if not isinstance(records, list):
                raise CleanarrClientError(f"{self.app} queue payload is invalid")
            seen += len(records)
            reader.add(records)
            total = data.get("totalRecords")
            known_total = isinstance(total, int)
            if not records or (known_total and seen >= total):
                return reader.result(reached_total=not known_total or seen >= total)
            page += 1

    async def remove(self, queue_id: int) -> bool:
        """Remove, blocklist and re-search a queue item.

        Returns ``True`` when removed and ``False`` when the Arr answers 404
        (already gone, for example removed by the user or another cleaner).
        Any other failure raises :class:`CleanarrClientError`.
        """
        try:
            await self._request(
                "DELETE", f"/api/v3/queue/{queue_id}", params=_REMOVE_PARAMS
            )
        except CleanarrClientError as exc:
            if exc.status_code == 404:
                return False
            raise
        return True

    async def download_handling(self) -> ArrDownloadHandling:
        """Return the failed/completed download handling relevant to SABnzbd."""
        config = await self._request("GET", "/api/v3/config/downloadclient")
        config = config if isinstance(config, dict) else {}
        clients = [
            client
            for client in self._as_dicts(
                await self._request("GET", "/api/v3/downloadclient")
            )
            if _text(client.get("implementation")).lower() == "sabnzbd"
        ]
        return ArrDownloadHandling(
            completed_handling=_optional_bool(
                config.get("enableCompletedDownloadHandling")
            ),
            redownload_failed=_optional_bool(config.get("autoRedownloadFailed")),
            remove_failed=_all_known(
                [_optional_bool(c.get("removeFailedDownloads")) for c in clients]
            ),
            remove_completed=_all_known(
                [_optional_bool(c.get("removeCompletedDownloads")) for c in clients]
            ),
        )


def client_for(ctx: AppContext, app: str) -> CleanarrArrClient:
    """Build a Cleanarr client from the context's Sonarr or Radarr connection.

    The URL and API key come from the shared context client (managed from the
    dashboard), so Cleanarr never owns its own copy of the credentials.
    """
    source = ctx.sonarr if app == "sonarr" else ctx.radarr
    fields = source.connection_fields()
    return CleanarrArrClient(
        app=app, base_url=fields["base_url"], api_key=fields["api_key"]
    )
