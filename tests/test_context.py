"""Tests for core.context."""

from __future__ import annotations

from core.context import DryRunFlag
from tests.conftest import make_ctx


def test_dry_run_flag_is_callable() -> None:
    flag = DryRunFlag(True)
    assert flag() is True
    flag.value = False
    assert flag() is False


def test_set_dry_run_updates_flag_and_property(db) -> None:
    ctx = make_ctx(db=db, dry_run=True)
    assert ctx.dry_run is True
    returned = ctx.set_dry_run(False)
    assert returned is False
    assert ctx.dry_run is False
    assert ctx.dry_run_flag.value is False
