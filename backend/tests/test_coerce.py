"""Tests for core.coerce."""

from __future__ import annotations

import pytest

from core.coerce import stripped_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("  padded  ", "padded"),
        ("\t\nTabbed\r\n", "Tabbed"),
        # Unicode whitespace (no-break space, em space, ideographic space).
        (" Unicode 　", "Unicode"),
        # Internal whitespace is preserved.
        ("  Two  Words ", "Two  Words"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_stripped_text_strips_strings(raw: str, expected: str) -> None:
    assert stripped_text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, 0, 42, 1.5, True, False, b" bytes ", ["a"], {"a": "b"}, ("a",), object()],
)
def test_stripped_text_rejects_non_strings_without_stringifying(raw: object) -> None:
    assert stripped_text(raw) == ""


def test_stripped_text_accepts_str_subclasses() -> None:
    class Label(str):
        pass

    result = stripped_text(Label("  sub  "))
    assert result == "sub"
