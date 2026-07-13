#!/usr/bin/env bash
#
# Locate or create the repository's Python virtual environment on POSIX and
# Windows/Git Bash. Call ensure_project_venv with the repository root; it sets
# VENV_PY and IS_WINDOWS for the calling script.

python_command_is_compatible() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 14) else 1)' \
    >/dev/null 2>&1
}

locate_project_venv_python() {
  local root_dir="$1"

  VENV_PY=""
  IS_WINDOWS=0
  if [[ -f "$root_dir/.venv/bin/python" ]]; then
    VENV_PY="$root_dir/.venv/bin/python"
  elif [[ -f "$root_dir/.venv/Scripts/python.exe" ]]; then
    VENV_PY="$root_dir/.venv/Scripts/python.exe"
    IS_WINDOWS=1
  fi
}

create_project_venv() {
  local root_dir="$1"
  local candidate
  local -a bootstrap_python=()

  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if ! python_command_is_compatible "$PYTHON_BIN"; then
      echo "Error: PYTHON_BIN='$PYTHON_BIN' is not an executable Python 3.14+ interpreter." >&2
      return 1
    fi
    bootstrap_python=("$PYTHON_BIN")
  else
    for candidate in python3.14 python3; do
      if python_command_is_compatible "$candidate"; then
        bootstrap_python=("$candidate")
        break
      fi
    done

    if [[ "${#bootstrap_python[@]}" -eq 0 ]] && python_command_is_compatible py -3.14; then
      bootstrap_python=(py -3.14)
    elif [[ "${#bootstrap_python[@]}" -eq 0 ]] && python_command_is_compatible py -3; then
      bootstrap_python=(py -3)
    elif [[ "${#bootstrap_python[@]}" -eq 0 ]] && python_command_is_compatible python; then
      bootstrap_python=(python)
    fi
  fi

  if [[ "${#bootstrap_python[@]}" -eq 0 ]]; then
    echo "Error: no suitable Python interpreter found (need Python 3.14+ on PATH)." >&2
    echo "  Tried: python3.14, python3, py -3.14, py -3, python." >&2
    echo "  Install Python 3.14+ or set PYTHON_BIN to its executable path." >&2
    return 1
  fi

  if ! "${bootstrap_python[@]}" -m venv "$root_dir/.venv"; then
    echo "Error: failed to create the virtual environment at '$root_dir/.venv'." >&2
    return 1
  fi
}

ensure_project_venv() {
  local root_dir="$1"
  local existing_version

  locate_project_venv_python "$root_dir"
  if [[ -n "$VENV_PY" ]] \
     && ! { python_command_is_compatible "$VENV_PY" \
            && "$VENV_PY" -m pip --version >/dev/null 2>&1; }; then
    existing_version="$("$VENV_PY" -V 2>&1 || true)"
    echo "Existing .venv is unusable (need Python 3.14+ with pip; found ${existing_version:-unknown}); rebuilding…"
    rm -rf "${root_dir:?}/.venv"
    VENV_PY=""
  fi

  if [[ -z "$VENV_PY" ]]; then
    echo "No usable virtual environment at .venv/ — creating one now…"
    if ! create_project_venv "$root_dir"; then
      return 1
    fi
    locate_project_venv_python "$root_dir"
  fi

  if [[ -z "$VENV_PY" ]] \
     || ! python_command_is_compatible "$VENV_PY" \
     || ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "Error: .venv was not created with a usable Python 3.14+ interpreter and pip." >&2
    return 1
  fi
}
