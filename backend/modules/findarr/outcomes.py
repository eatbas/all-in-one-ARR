"""Follow up Findarr search commands to learn what each search actually did.

Sending a search command only tells Findarr that Sonarr/Radarr *accepted* it.
Each search is logged with the Arr's command id; at the start of the next run
for that app, Findarr reads every still-pending command back, classifies the
result, rewrites the matching History row, and feeds the result into the retry
backoff (:mod:`modules.findarr.backoff`).

The Arr keeps a command's completion message ("Episode search completed. 2
reports downloaded.") only while the command is in its in-memory list; once it
is persisted, the stored resource has no message. So a finished command is
classified from its message when present, and otherwise from the Arr's grab
history: a ``grabbed`` event for one of the command's searched items between
the command's start and end means the search grabbed a release.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.app_metrics import record_findarr_outcome
from core.coerce import parse_int
from core.logging import get_logger
from modules.findarr import backoff
from modules.findarr.client import FindarrClientError

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from modules.findarr.client import FindarrArrClient

_log = get_logger("findarr")

# Pending commands read back per app per run; older ones are read first, and
# anything beyond this waits for the next run.
PENDING_LOOKUP_LIMIT = 200

# Grace after a command ends during which its grab events are still attributed
# to it (the history row is written as the release is handed to the client).
_GRAB_GRACE = timedelta(minutes=2)

_RUNNING_STATUSES = frozenset({"queued", "started"})
_FAILED_STATUSES = frozenset({"failed", "aborted", "cancelled", "orphaned"})
_REPORTS_DOWNLOADED = re.compile(r"(\d+)\s+reports?\s+downloaded", re.IGNORECASE)


@dataclass(frozen=True)
class SearchOutcome:
    """A classified search result.

    ``outcome`` is stored on the search log (``grabbed``, ``not_found``,
    ``failed`` or ``unknown``); ``history_status`` and ``detail`` replace the
    History row's ``sent`` status and text.
    """

    outcome: str
    history_status: str
    detail: str


@dataclass(frozen=True)
class GrabEvent:
    """One ``grabbed`` history event, reduced to what search matching needs."""

    at: datetime
    episode_id: int | None = None
    series_id: int | None = None
    season_number: int | None = None
    movie_id: int | None = None


@dataclass(frozen=True)
class SearchTargets:
    """The items a search command covered, read from the command's stored body."""

    episode_ids: frozenset[int] = frozenset()
    movie_ids: frozenset[int] = frozenset()
    series_id: int | None = None
    season_number: int | None = None

    def matches(self, event: GrabEvent) -> bool:
        """Whether a grab event is for one of these items."""
        if self.episode_ids or self.movie_ids:
            return (
                event.episode_id in self.episode_ids or event.movie_id in self.movie_ids
            )
        if self.series_id is None or event.series_id != self.series_id:
            return False
        return self.season_number is None or event.season_number == self.season_number


def _int_set(values: Any) -> frozenset[int]:
    if not isinstance(values, list):
        return frozenset()
    return frozenset(
        parsed
        for parsed in (parse_int(value) for value in values)
        if parsed is not None
    )


def search_targets(command: dict[str, Any]) -> SearchTargets | None:
    """Return the items a command searched, or ``None`` when its body has none."""
    body = command.get("body")
    if not isinstance(body, dict):
        return None
    targets = SearchTargets(
        episode_ids=_int_set(body.get("episodeIds")),
        movie_ids=_int_set(body.get("movieIds")),
        series_id=parse_int(body.get("seriesId")),
        season_number=parse_int(body.get("seasonNumber")),
    )
    if not (targets.episode_ids or targets.movie_ids or targets.series_id is not None):
        return None
    return targets


def grab_event(record: dict[str, Any]) -> GrabEvent | None:
    """Parse a history record into a :class:`GrabEvent`, or ``None`` if undated."""
    at = backoff.parse_iso(str(record.get("date") or ""))
    if at is None:
        return None
    episode = record.get("episode")
    season = episode.get("seasonNumber") if isinstance(episode, dict) else None
    return GrabEvent(
        at=at,
        episode_id=parse_int(record.get("episodeId")),
        series_id=parse_int(record.get("seriesId")),
        season_number=parse_int(season),
        movie_id=parse_int(record.get("movieId")),
    )


def _command_window(command: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """Return the span in which a finished command's grabs were written."""
    start = backoff.parse_iso(
        str(command.get("started") or command.get("queued") or "")
    )
    end = backoff.parse_iso(str(command.get("ended") or ""))
    if start is None or end is None:
        return None
    return start, end + _GRAB_GRACE


def _grabbed_count(command: dict[str, Any], grabs: list[GrabEvent]) -> int | None:
    """Count grabs a finished command made; ``None`` when it cannot be told."""
    message = str(command.get("message") or "")
    match = _REPORTS_DOWNLOADED.search(message)
    if match is not None:
        return int(match.group(1))
    targets = search_targets(command)
    window = _command_window(command)
    if targets is None or window is None:
        return None
    start, end = window
    return sum(
        1 for event in grabs if start <= event.at <= end and targets.matches(event)
    )


def _status(command: dict[str, Any]) -> str:
    return str(command.get("status") or "").lower()


def is_running(command: dict[str, Any] | None) -> bool:
    """Whether a command is still queued or running (a purged one is not)."""
    return command is not None and _status(command) in _RUNNING_STATUSES


def classify(
    command: dict[str, Any] | None, app_label: str, grabs: list[GrabEvent]
) -> SearchOutcome:
    """Classify a finished command resource (see :func:`is_running`).

    ``command`` is ``None`` when the Arr no longer holds the command (purged
    from its command history), which leaves the result unknown.
    """
    if command is None:
        return SearchOutcome(
            "unknown",
            "unknown",
            f"{app_label} no longer has this search command; result unknown",
        )
    status = _status(command)
    message = str(command.get("message") or "").strip()
    if status in _FAILED_STATUSES:
        return SearchOutcome(
            "failed",
            "error",
            f"{app_label} search {status}: {message or 'no detail given'}",
        )
    grabbed = _grabbed_count(command, grabs) if status == "completed" else None
    if grabbed is None:
        return SearchOutcome(
            "unknown",
            "unknown",
            f"{app_label} search {status or 'state unknown'}: result not reported",
        )
    if grabbed > 0:
        return SearchOutcome(
            "grabbed", "grabbed", f"{app_label} grabbed {grabbed} release(s)"
        )
    return SearchOutcome("not_found", "not_found", f"{app_label} found no new release")


def _apply_backoff(
    ctx: AppContext,
    search: dict[str, Any],
    outcome: SearchOutcome,
    *,
    app: str,
    retry_state: dict[str, dict[str, Any]],
    base_hours: int,
) -> None:
    """Move a unit's retry state on from a resolved outcome.

    ``grabbed`` resets the no-result count; ``not_found`` extends it (doubling
    the wait); ``failed`` says nothing about release availability, so the unit
    becomes due again straight away. ``unknown`` keeps the delay set when the
    search was sent. Units pruned since the search are left alone.
    """
    entry = retry_state.get(search["item_id"])
    if entry is None or outcome.outcome == "unknown":
        return
    searched_at = backoff.parse_iso(search["ts"]) or datetime.now(UTC)
    attempts = int(entry["attempts"])
    if outcome.outcome == "grabbed":
        attempts = 0
        next_eligible = backoff.next_eligible_at(searched_at, 0, base_hours)
    elif outcome.outcome == "not_found":
        attempts += 1
        next_eligible = backoff.next_eligible_at(searched_at, attempts, base_hours)
    else:
        next_eligible = searched_at.isoformat()
    ctx.db.findarr_set_retry(
        app=app,
        mode=search["mode"],
        item_id=search["item_id"],
        attempts=attempts,
        next_eligible_at=next_eligible,
    )
    entry["attempts"] = attempts


async def _finished_commands(
    client: FindarrArrClient, pending: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Read back each pending command; keep the finished (or purged) ones.

    A lookup that fails (the Arr dropped mid-run) ends the pass; the remaining
    searches stay pending for the next run.
    """
    finished: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for search in pending:
        try:
            command = await client.command(int(search["command_id"]))
        except FindarrClientError as exc:
            _log.warning(
                "Findarr could not read %s command results: %s", client.app, exc
            )
            break
        if not is_running(command):
            finished.append((search, command))
    return finished


async def _grabs_for(
    client: FindarrArrClient,
    finished: list[tuple[dict[str, Any], dict[str, Any] | None]],
) -> list[GrabEvent]:
    """Fetch the grab events covering every finished command, in one request."""
    starts = [
        window[0]
        for _, command in finished
        if command is not None and (window := _command_window(command)) is not None
    ]
    if not starts:
        return []
    records = await client.grabs_since(min(starts).isoformat())
    return [event for event in (grab_event(record) for record in records) if event]


async def resolve_pending(
    ctx: AppContext, client: FindarrArrClient, app: str, *, base_hours: int
) -> int:
    """Resolve this app's finished searches; return how many were resolved.

    Failing to read the commands or the grab history leaves every search
    pending for the next run instead of failing the run.
    """
    pending = ctx.db.findarr_pending_searches(app=app, limit=PENDING_LOOKUP_LIMIT)
    if not pending:
        return 0
    finished = await _finished_commands(client, pending)
    try:
        grabs = await _grabs_for(client, finished)
    except FindarrClientError as exc:
        _log.warning("Findarr could not read %s grab history: %s", app, exc)
        return 0
    app_label = app.capitalize()
    retry_states: dict[str, dict[str, dict[str, Any]]] = {}
    for search, command in finished:
        outcome = classify(command, app_label, grabs)
        mode = search["mode"]
        if mode not in retry_states:
            retry_states[mode] = ctx.db.findarr_retry_state(app=app, mode=mode)
        _apply_backoff(
            ctx,
            search,
            outcome,
            app=app,
            retry_state=retry_states[mode],
            base_hours=base_hours,
        )
        ctx.db.findarr_resolve_search(
            search_id=int(search["id"]),
            outcome=outcome.outcome,
            history_id=search["history_id"],
            history_status=outcome.history_status,
            history_detail=outcome.detail,
        )
        record_findarr_outcome(app=app, mode=mode, outcome=outcome.outcome)
    return len(finished)
