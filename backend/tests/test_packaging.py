"""Tests that the distribution declares every package in the source tree.

``pyproject.toml`` lists its setuptools packages explicitly, so a new module
package that is not added there is silently left out of the wheel (and of the
Docker image's ``pip install .``): module discovery then cannot find it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from core.registry import discover_module_names

_BACKEND = Path(__file__).resolve().parents[1]


def _declared_packages() -> set[str]:
    """Return the ``[tool.setuptools] packages`` listed in ``pyproject.toml``."""
    with (_BACKEND / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    return set(config["tool"]["setuptools"]["packages"])


def _source_packages() -> set[str]:
    """Return every importable package under ``core/`` and ``modules/``."""
    return {
        ".".join(init.parent.relative_to(_BACKEND).parts)
        for root in ("core", "modules")
        for init in (_BACKEND / root).rglob("__init__.py")
    }


def test_declared_packages_match_the_source_tree() -> None:
    assert _declared_packages() == _source_packages()


@pytest.mark.parametrize("name", discover_module_names())
def test_every_discovered_module_is_distributed(name: str) -> None:
    assert f"modules.{name}" in _declared_packages()
