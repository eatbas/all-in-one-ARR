"""Tests for resolving Findarr search outcomes from Arr commands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modules.findarr import outcomes
from modules.findarr.client import FindarrClientError
from modules.findarr.outcomes import GrabEvent
from tests.conftest import make_ctx

_STARTED = "2026-10-13T19:56:22Z"
_ENDED = "2026-10-13T19:56:37Z"
_DURING = datetime(2026, 10, 13, 19, 56, 30, tzinfo=UTC)


def _stored(body: dict, **overrides) -> dict:
    """A persisted command resource: finished, with a body but no message."""
    command = {
        "status": "completed",
        "message": None,
        "queued": _STARTED,
        "started": _STARTED,
        "ended": _ENDED,
        "body": body,
    }
    command.update(overrides)
    return command


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            None,
            (
                "unknown",
                "unknown",
                "Sonarr no longer has this search command; result unknown",
            ),
        ),
        (
            {
                "status": "completed",
                "message": "Episode search completed. 2 reports downloaded.",
            },
            ("grabbed", "grabbed", "Sonarr grabbed 2 release(s)"),
        ),
        (
            {
                "status": "completed",
                "message": "Season search completed. 1 report downloaded.",
            },
            ("grabbed", "grabbed", "Sonarr grabbed 1 release(s)"),
        ),
        (
            {
                "status": "completed",
                "message": "Episode search completed. 0 reports downloaded.",
            },
            ("not_found", "not_found", "Sonarr found no new release"),
        ),
        (
            {"status": "failed", "message": "Indexer unavailable"},
            ("failed", "error", "Sonarr search failed: Indexer unavailable"),
        ),
        (
            {"status": "aborted"},
            ("failed", "error", "Sonarr search aborted: no detail given"),
        ),
        (
            {"status": "completed", "message": "Completed"},
            ("unknown", "unknown", "Sonarr search completed: result not reported"),
        ),
        (
            {},
            ("unknown", "unknown", "Sonarr search state unknown: result not reported"),
        ),
    ],
)
def test_classify_maps_command_results(command, expected) -> None:
    result = outcomes.classify(command, "Sonarr", [])
    assert (result.outcome, result.history_status, result.detail) == expected


@pytest.mark.parametrize(
    ("body", "event", "outcome"),
    [
        ({"episodeIds": [7]}, GrabEvent(at=_DURING, episode_id=7), "grabbed"),
        ({"episodeIds": [7]}, GrabEvent(at=_DURING, episode_id=8), "not_found"),
        (
            {"seriesId": 5, "seasonNumber": 2},
            GrabEvent(at=_DURING, series_id=5, season_number=2),
            "grabbed",
        ),
        (
            {"seriesId": 5, "seasonNumber": 2},
            GrabEvent(at=_DURING, series_id=5, season_number=1),
            "not_found",
        ),
        ({"seriesId": 5}, GrabEvent(at=_DURING, series_id=5), "grabbed"),
        ({"seriesId": 5}, GrabEvent(at=_DURING, series_id=6), "not_found"),
        ({"movieIds": [3]}, GrabEvent(at=_DURING, movie_id=3), "grabbed"),
        # A grab outside the command's run (plus grace) belongs to something else.
        (
            {"episodeIds": [7]},
            GrabEvent(at=_DURING + timedelta(hours=1), episode_id=7),
            "not_found",
        ),
    ],
)
def test_classify_uses_grab_history_once_the_message_is_gone(
    body: dict, event: GrabEvent, outcome: str
) -> None:
    assert outcomes.classify(_stored(body), "Sonarr", [event]).outcome == outcome


@pytest.mark.parametrize(
    "command",
    [
        _stored({}),
        _stored({"episodeIds": ["x"]}),
        {"status": "completed", "body": "junk", "started": _STARTED, "ended": _ENDED},
        _stored({"episodeIds": [7]}, ended=None),
    ],
)
def test_classify_reports_unknown_when_targets_or_timing_are_missing(
    command: dict,
) -> None:
    event = GrabEvent(at=_DURING, episode_id=7)
    assert outcomes.classify(command, "Sonarr", [event]).outcome == "unknown"


def test_is_running_and_grab_event_parsing() -> None:
    assert outcomes.is_running({"status": "Queued"}) is True
    assert outcomes.is_running({"status": "started"}) is True
    assert outcomes.is_running({"status": "completed"}) is False
    assert outcomes.is_running(None) is False
    assert outcomes.grab_event({"date": "not a date"}) is None
    assert outcomes.grab_event(
        {
            "date": "2026-10-13T19:56:30Z",
            "episodeId": 7,
            "seriesId": 5,
            "episode": {"seasonNumber": 2},
        }
    ) == GrabEvent(at=_DURING, episode_id=7, series_id=5, season_number=2)
    assert outcomes.grab_event(
        {"date": "2026-10-13T19:56:30Z", "movieId": 3}
    ) == GrabEvent(at=_DURING, movie_id=3)


class _CommandClient:
    app = "sonarr"

    def __init__(
        self,
        commands: dict,
        *,
        grabs: list[dict] | None = None,
        error_on: int | None = None,
        history_error: bool = False,
    ) -> None:
        self.commands = commands
        self.grabs = grabs or []
        self.error_on = error_on
        self.history_error = history_error
        self.requested: list[int] = []
        self.grabs_requested: list[str] = []

    async def command(self, command_id: int):
        self.requested.append(command_id)
        if command_id == self.error_on:
            raise FindarrClientError("sonarr down")
        return self.commands.get(command_id)

    async def grabs_since(self, since_iso: str) -> list[dict]:
        self.grabs_requested.append(since_iso)
        if self.history_error:
            raise FindarrClientError("history down")
        return self.grabs


def _sent(db, item_id: str, command_id: int, *, attempts: int = 0) -> int:
    history_id = db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id=item_id,
        title=item_id,
        status="sent",
        detail="pending",
    )
    db.findarr_mark_searched(
        app="sonarr",
        mode="missing",
        item_id=item_id,
        title=item_id,
        next_eligible_at="2999-01-01T00:00:00+00:00",
    )
    db.findarr_set_retry(
        app="sonarr",
        mode="missing",
        item_id=item_id,
        attempts=attempts,
        next_eligible_at="2999-01-01T00:00:00+00:00",
    )
    db.findarr_log_search(
        app="sonarr",
        mode="missing",
        item_id=item_id,
        command_id=command_id,
        history_id=history_id,
    )
    return history_id


def _hours_from_now(value: str) -> float:
    delta = datetime.fromisoformat(value) - datetime.now(UTC)
    return delta / timedelta(hours=1)


async def test_resolve_pending_applies_outcomes_to_history_and_backoff(db) -> None:
    ctx = make_ctx(db=db)
    _sent(db, "grab", 1, attempts=3)
    _sent(db, "miss", 2, attempts=1)
    _sent(db, "fail", 3, attempts=2)
    _sent(db, "gone", 4, attempts=1)
    _sent(db, "busy", 5)
    _sent(db, "stored", 6)
    client = _CommandClient(
        {
            1: {"status": "completed", "message": "1 reports downloaded"},
            2: {"status": "completed", "message": "0 reports downloaded"},
            3: {"status": "failed", "message": "boom"},
            5: {"status": "started"},
            6: _stored({"episodeIds": [66]}),
        },
        grabs=[{"date": "2026-10-13T19:56:30Z", "episodeId": 66}, {"date": None}],
    )
    resolved = await outcomes.resolve_pending(ctx, client, "sonarr", base_hours=24)
    assert resolved == 5
    # One history read covers every finished command, from the earliest start.
    assert client.grabs_requested == ["2026-10-13T19:56:22+00:00"]

    statuses = {row["item_id"]: row["status"] for row in db.findarr_recent_history()}
    assert statuses == {
        "grab": "grabbed",
        "miss": "not_found",
        "fail": "error",
        "gone": "unknown",
        "busy": "sent",
        "stored": "grabbed",
    }
    retry = db.findarr_retry_state(app="sonarr", mode="missing")
    # Grabbed resets the count; a miss doubles the wait (2 misses → 48h).
    assert retry["grab"]["attempts"] == 0
    assert 23 < _hours_from_now(retry["grab"]["next_eligible_at"]) <= 24
    assert retry["miss"]["attempts"] == 2
    assert 47 < _hours_from_now(retry["miss"]["next_eligible_at"]) <= 48
    # A failed command is due again at once; unknown keeps the sent-time delay.
    assert retry["fail"]["attempts"] == 2
    assert _hours_from_now(retry["fail"]["next_eligible_at"]) <= 0
    assert retry["gone"]["next_eligible_at"] == "2999-01-01T00:00:00+00:00"
    # The running command stays pending for the next run.
    pending = db.findarr_pending_searches(app="sonarr", limit=10)
    assert [row["item_id"] for row in pending] == ["busy"]


async def test_resolve_pending_is_a_no_op_without_pending_searches(db) -> None:
    client = _CommandClient({})
    assert (
        await outcomes.resolve_pending(make_ctx(db=db), client, "sonarr", base_hours=24)
        == 0
    )
    assert client.requested == []


async def test_resolve_pending_skips_history_when_no_command_has_a_window(db) -> None:
    ctx = make_ctx(db=db)
    _sent(db, "1", 1)
    client = _CommandClient({})
    assert await outcomes.resolve_pending(ctx, client, "sonarr", base_hours=24) == 1
    assert client.grabs_requested == []
    assert db.findarr_recent_history()[0]["status"] == "unknown"


async def test_resolve_pending_skips_backoff_for_pruned_units(db) -> None:
    ctx = make_ctx(db=db)
    _sent(db, "1", 1)
    db.findarr_reset_state()
    client = _CommandClient(
        {1: {"status": "completed", "message": "0 reports downloaded"}}
    )
    assert await outcomes.resolve_pending(ctx, client, "sonarr", base_hours=24) == 1
    assert db.findarr_retry_state(app="sonarr", mode="missing") == {}
    assert db.findarr_recent_history()[0]["status"] == "not_found"


async def test_resolve_pending_stops_on_lookup_error(db) -> None:
    ctx = make_ctx(db=db)
    _sent(db, "1", 1)
    _sent(db, "2", 2)
    client = _CommandClient({}, error_on=1)
    assert await outcomes.resolve_pending(ctx, client, "sonarr", base_hours=24) == 0
    # The failing lookup ends the pass; nothing else is requested this run.
    assert client.requested == [1]
    assert len(db.findarr_pending_searches(app="sonarr", limit=10)) == 2


async def test_resolve_pending_keeps_searches_pending_when_history_fails(db) -> None:
    ctx = make_ctx(db=db)
    _sent(db, "1", 1)
    client = _CommandClient({1: _stored({"episodeIds": [1]})}, history_error=True)
    assert await outcomes.resolve_pending(ctx, client, "sonarr", base_hours=24) == 0
    assert len(db.findarr_pending_searches(app="sonarr", limit=10)) == 1
    assert db.findarr_recent_history()[0]["status"] == "sent"
