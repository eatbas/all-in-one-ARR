#!/usr/bin/env python3
"""Build the backend wheel and verify it ships and discovers every module.

``backend/pyproject.toml`` lists its packages explicitly, so a package missing
from that list builds without error but is absent from the wheel (and from the
Docker image's ``pip install .``). This script builds the wheel from a fresh
copy of the backend sources in a temporary directory, checks that it contains
every Python source file under ``core/`` and ``modules/``, installs it into a
separate temporary directory, and then, from outside the source tree, runs
module discovery against the installed copy and imports each discovered module.

Nothing is written to the repository: the source copy, the wheel, the installed
copy and the working directory of the import check all live in one temporary
directory.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PACKAGE_ROOTS = ("core", "modules")

# Run in the installed copy: discover the modules, import each one and report
# where both the registry and every module were imported from.
_DISCOVERY_PROBE = """
import importlib
import json

from core import registry

names = registry.discover_module_names()
files = {name: importlib.import_module(f"modules.{name}").__file__ for name in names}
print(json.dumps({"registry": registry.__file__, "modules": files}))
"""


def _source_files() -> set[str]:
    """Return the wheel-relative paths of every backend package source file."""
    return {
        path.relative_to(BACKEND).as_posix()
        for root in PACKAGE_ROOTS
        for path in (BACKEND / root).rglob("*.py")
        if "__pycache__" not in path.parts
    }


def _source_module_names() -> set[str]:
    """Return the module packages directly under ``backend/modules``."""
    return {init.parent.name for init in (BACKEND / "modules").glob("*/__init__.py")}


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``command``, echoing it, and raise if it fails."""
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        check=True,
        text=True,
        cwd=cwd,
        env=env,
        capture_output=capture_output,
    )


def copy_sources(destination: Path) -> Path:
    """Copy the files the wheel is built from into ``destination``.

    Building in place would let setuptools reuse a stale ``backend/build/lib``
    (still holding a package since dropped from the list) and would leave
    ``build/`` and ``*.egg-info`` behind in the repository.
    """
    destination.mkdir(parents=True)
    shutil.copy2(BACKEND / "pyproject.toml", destination / "pyproject.toml")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for root in PACKAGE_ROOTS:
        shutil.copytree(BACKEND / root, destination / root, ignore=ignore)
    return destination


def build_wheel(source: Path, output: Path) -> Path:
    """Build the wheel (without dependencies) from ``source`` into ``output``."""
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(output),
            str(source),
        ]
    )
    wheels = sorted(output.glob("aio_arr-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one aio_arr wheel in {output}, found {wheels}")
    return wheels[0]


def check_wheel_contents(wheel: Path) -> None:
    """Fail unless the wheel holds exactly the backend package source files."""
    with zipfile.ZipFile(wheel) as archive:
        shipped = {
            name
            for name in archive.namelist()
            if name.endswith(".py") and name.split("/", 1)[0] in PACKAGE_ROOTS
        }
    expected = _source_files()
    missing = sorted(expected - shipped)
    unexpected = sorted(shipped - expected)
    if missing or unexpected:
        raise SystemExit(
            f"{wheel.name} does not match the source tree.\n"
            f"Missing: {missing}\nUnexpected: {unexpected}\n"
            "Update [tool.setuptools] packages in backend/pyproject.toml."
        )
    print(f"{wheel.name} contains all {len(expected)} backend source files.")


def check_installed_discovery(wheel: Path, work_dir: Path) -> None:
    """Install ``wheel`` outside the repository and discover its modules there."""
    site = work_dir / "site"
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(site),
            str(wheel),
        ]
    )
    # PYTHONPATH puts the installed copy ahead of any editable install in the
    # virtual environment, whose third-party dependencies are still used.
    env = {**os.environ, "PYTHONPATH": str(site)}
    probe = _run(
        [sys.executable, "-c", _DISCOVERY_PROBE],
        cwd=work_dir,
        env=env,
        capture_output=True,
    )
    report = json.loads(probe.stdout)
    imported = [report["registry"], *report["modules"].values()]
    outside = [path for path in imported if not Path(path).is_relative_to(site)]
    if outside:
        raise SystemExit(f"Imported from outside the installed wheel: {outside}")
    discovered = set(report["modules"])
    expected = _source_module_names()
    if discovered != expected:
        raise SystemExit(
            "Installed module discovery does not match the source tree.\n"
            f"Missing: {sorted(expected - discovered)}\n"
            f"Unexpected: {sorted(discovered - expected)}"
        )
    print(
        f"The installed wheel discovered and imported {len(discovered)} modules: "
        + ", ".join(sorted(discovered))
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aio-arr-dist-") as tmp:
        work_dir = Path(tmp)
        source = copy_sources(work_dir / "source")
        wheel = build_wheel(source, work_dir / "wheels")
        check_wheel_contents(wheel)
        check_installed_discovery(wheel, work_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
