"""Typed SABnzbd history and configuration reads used by Cleanarr.

Kept in ``core`` (next to :mod:`core.bandwidth_types`) so
:mod:`core.clients.sabnzbd` can return them without importing from
``modules``; :mod:`modules.cleanarr.models` re-exports them.

Contract relied on (SABnzbd 4.x JSON API; see the plan's "Assumed external
contracts"):

* ``mode=history`` → ``{"history": {"slots": [...], "noofslots": N}}``; each slot
  carries ``nzo_id``, ``name``, ``status`` (``Completed``/``Failed``/…),
  ``category`` and ``storage`` (the job's final path). ``storage`` is
  **unverified** and listed under Manual verification.
* ``mode=get_config`` → ``{"config": {"misc": {...}, "categories": [...]}}``
  (verified via Context7: ``get_dconfig`` and ``categories[].dir``; each
  category also carries its ``name``). The
  ``misc`` keys ``complete_dir``, ``unwanted_extensions``,
  ``action_on_unwanted_extensions`` and ``pause_on_pwrar`` (0 off, 1 pause,
  2 abort) are **unverified**.

Parsing is tolerant: integers may arrive as strings, the extension list as a
comma-separated string or a list, and categories as a list or a name-keyed dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SabHistoryJob:
    """One SABnzbd history slot, reduced to the fields Cleanarr reads."""

    nzo_id: str
    name: str
    status: str
    category: str
    storage: str


@dataclass(frozen=True)
class SabHistory:
    """SABnzbd history jobs plus whether they are the whole history.

    ``complete`` is ``False`` when paging stopped at the job cap, SABnzbd's
    reported total could not be reached, or a slot's ``storage`` was
    malformed, so the jobs must not be treated as an exhaustive reference set.
    ``unparsed_storage`` keeps the ``storage`` of slots that could not become
    a job (no usable ``nzo_id``): their folders are still referenced.
    """

    jobs: tuple[SabHistoryJob, ...]
    complete: bool
    unparsed_storage: tuple[str, ...] = ()


@dataclass(frozen=True)
class SabConfig:
    """The SABnzbd settings Cleanarr checks and maps paths with.

    ``category_folders`` holds ``(name, dir)`` pairs for every category with
    a folder, so a category folder can be traced back to its category names.
    """

    complete_dir: str
    unwanted_extensions: tuple[str, ...]
    unwanted_action: int | None
    encrypted_rar_action: int | None
    category_dirs: tuple[str, ...]
    category_folders: tuple[tuple[str, str], ...] = ()


def _text(value: Any) -> str:
    """Return a stripped string, or ``""`` for non-strings."""
    return value.strip() if isinstance(value, str) else ""


def _optional_int(value: Any) -> int | None:
    """Return an int from an int or numeric string; ``None`` otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _extensions(value: Any) -> tuple[str, ...]:
    """Return lower-case ``.ext`` entries from a list or comma-separated string."""
    if isinstance(value, str):
        entries: list[Any] = value.split(",")
    elif isinstance(value, list):
        entries = value
    else:
        return ()
    result: list[str] = []
    for entry in entries:
        text = _text(entry).lower()
        if not text:
            continue
        extension = text if text.startswith(".") else f".{text}"
        if extension not in result:
            result.append(extension)
    return tuple(result)


def _category_folders(value: Any) -> tuple[tuple[str, str], ...]:
    """Return ``(name, dir)`` for every SABnzbd category with a non-empty ``dir``."""
    if isinstance(value, dict):
        categories: list[Any] = list(value.values())
    elif isinstance(value, list):
        categories = value
    else:
        return ()
    pairs = (
        (_text(category.get("name")), _text(category.get("dir")))
        for category in categories
        if isinstance(category, dict)
    )
    return tuple(dict.fromkeys(pair for pair in pairs if pair[1]))


def history_slot_storage(slot: dict[str, Any]) -> str | None:
    """Return a history slot's ``storage`` path, or ``None`` when it is malformed.

    A missing or ``null`` value is ``""`` (no folder); any other non-string
    hides which folder the slot refers to, so it is ``None``.
    """
    value = slot.get("storage")
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else None


def parse_history_job(slot: dict[str, Any]) -> SabHistoryJob | None:
    """Return a :class:`SabHistoryJob`, or ``None`` when the slot has no ``nzo_id``."""
    nzo_id = _text(slot.get("nzo_id"))
    if not nzo_id:
        return None
    return SabHistoryJob(
        nzo_id=nzo_id,
        name=_text(slot.get("name")),
        status=_text(slot.get("status")),
        category=_text(slot.get("category")),
        storage=_text(slot.get("storage")),
    )


def parse_history_slots(slots: list[dict[str, Any]]) -> SabHistory:
    """Parse one page of history slots into jobs and leftover references.

    A slot without a usable ``nzo_id`` cannot become a job, but its
    ``storage`` is kept in ``unparsed_storage``. ``complete`` is ``False``
    when any slot's ``storage`` was malformed (see
    :func:`history_slot_storage`), so the page is not an exhaustive
    reference set.
    """
    jobs: list[SabHistoryJob] = []
    unparsed: list[str] = []
    readable = True
    for slot in slots:
        storage = history_slot_storage(slot)
        readable = readable and storage is not None
        job = parse_history_job(slot)
        if job is not None:
            jobs.append(job)
        elif storage:
            unparsed.append(storage)
    return SabHistory(
        jobs=tuple(jobs), complete=readable, unparsed_storage=tuple(unparsed)
    )


def parse_config(data: Any) -> SabConfig | None:
    """Return a :class:`SabConfig` from a ``get_config`` body, or ``None``."""
    if not isinstance(data, dict) or not isinstance(data.get("config"), dict):
        return None
    config = data["config"]
    misc = config.get("misc")
    misc = misc if isinstance(misc, dict) else {}
    folders = _category_folders(config.get("categories"))
    return SabConfig(
        complete_dir=_text(misc.get("complete_dir")),
        unwanted_extensions=_extensions(misc.get("unwanted_extensions")),
        unwanted_action=_optional_int(misc.get("action_on_unwanted_extensions")),
        encrypted_rar_action=_optional_int(misc.get("pause_on_pwrar")),
        category_dirs=tuple(dict.fromkeys(directory for _name, directory in folders)),
        category_folders=folders,
    )
