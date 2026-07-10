#!/usr/bin/env bash
#
# dev.sh — start the full local development environment.
#
# Runs two servers side by side and tears both down together on Ctrl+C:
#   * the Python backend  — uvicorn with auto-reload, from the repo root so
#     `.env`, `data/` and `frontend/dist` resolve exactly as they do in Docker,
#     using the project's virtual environment in `.venv/`.
#   * the frontend        — the Vite dev server, which proxies `/api` and
#     `/webhook` to the backend (see frontend/vite.config.ts).
#
# Configurable via environment variables:
#   BACKEND_HOST   (default 127.0.0.1)
#   BACKEND_PORT   (default 3223)
#
# Runs on any Bash 3.2+ (the version macOS still ships). Run with:  bash dev.sh
set -euo pipefail

# Always operate from the repository root (this script's directory).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-3223}"
# Vite's default dev port (frontend/vite.config.ts pins no `server.port`); freed
# alongside the backend port before start-up and shown in the banner below.
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# --- Locate the virtual environment's Python (Unix vs Windows/Git Bash) -------
# IS_WINDOWS selects the backend reload strategy below: uvicorn's own --reload
# hangs on Windows (see the backend start-up block), so a Windows venv uses a
# watchfiles wrapper instead.
# Locate an existing venv's Python (Unix vs Windows/Git Bash). IS_WINDOWS selects
# the backend reload strategy further below.
VENV_PY=""
IS_WINDOWS=0
if [[ -f "$ROOT_DIR/.venv/bin/python" ]]; then
  VENV_PY="$ROOT_DIR/.venv/bin/python"
  IS_WINDOWS=0
elif [[ -f "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  VENV_PY="$ROOT_DIR/.venv/Scripts/python.exe"
  IS_WINDOWS=1
fi

# A usable venv must satisfy backend/pyproject.toml `requires-python` (>=3.14)
# and ship pip. A stale 3.11/3.12 venv cannot resolve the backend deps — pytest 9
# needs pytest-asyncio wheels that dropped older Python, so pip backtracks through
# every aio-arr/pytest-asyncio version and dies with "ResolutionImpossible" — and a
# uv-created venv has no pip. Rebuild it rather than fail with an opaque error.
if [[ -n "$VENV_PY" ]] \
   && ! { "$VENV_PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 14) else 1)' \
          && "$VENV_PY" -m pip --version; } >/dev/null 2>&1; then
  echo "Existing .venv is unusable (need Python 3.14+ with pip; found $("$VENV_PY" -V 2>&1)); rebuilding…"
  rm -rf "${ROOT_DIR:?}/.venv"
  VENV_PY=""
fi

if [[ -z "$VENV_PY" ]]; then
  echo "No usable virtual environment at .venv/ — creating one now…"
  # Pick an interpreter that satisfies `requires-python` (>=3.14). Prefer an
  # explicit python3.14, then generic launchers — python3, the Windows `py`
  # launcher (`py -3.14`/`py -3`), or a bare python — verifying the version so a
  # too-old system default (e.g. macOS's `python3` = 3.11) is never used to build
  # the venv. `py` is preferred over a bare `python` because it unambiguously
  # resolves to a real Python 3 rather than a Microsoft Store stub.
  BOOTSTRAP_PY=""
  for candidate in python3.14 python3 "py -3.14" "py -3" python; do
    if $candidate -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 14) else 1)' >/dev/null 2>&1; then
      BOOTSTRAP_PY="$candidate"
      break
    fi
  done
  if [[ -z "$BOOTSTRAP_PY" ]]; then
    echo "Error: no suitable Python interpreter found (need Python 3.14+ on PATH)." >&2
    echo "  Tried: python3.14, python3, py -3.14, py -3, python. Install Python 3.14+ and re-run: bash dev.sh" >&2
    exit 1
  fi
  $BOOTSTRAP_PY -m venv "$ROOT_DIR/.venv"
  # Determine the pip path (Unix vs Windows/Git Bash).
  if [[ -f "$ROOT_DIR/.venv/bin/pip" ]]; then
    VENV_PIP="$ROOT_DIR/.venv/bin/pip"
    VENV_PY="$ROOT_DIR/.venv/bin/python"
    IS_WINDOWS=0
  else
    VENV_PIP="$ROOT_DIR/.venv/Scripts/pip.exe"
    VENV_PY="$ROOT_DIR/.venv/Scripts/python.exe"
    IS_WINDOWS=1
  fi
  echo "Installing backend (with dev extras)…"
  "$VENV_PIP" install -e "./backend[dev]"
  echo "  ✔ Virtual environment created and backend installed."
fi

# --- Verify prerequisites -----------------------------------------------------
if ! "$VENV_PY" - <<'PY' >/dev/null 2>&1; then
from importlib import metadata
from pathlib import Path
import re
import sys
import tomllib

ROOT_DIR = Path.cwd()
PYPROJECT = ROOT_DIR / "backend" / "pyproject.toml"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+")


def normalise_requirement_name(requirement: str) -> str:
    match = NAME_PATTERN.match(requirement)
    if match is None:
        raise ValueError(f"Cannot parse requirement name from {requirement!r}")
    return re.sub(r"[-_.]+", "-", match.group(0)).lower()


def find_metadata_path(distribution: metadata.Distribution) -> Path | None:
    for distribution_file in distribution.files or ():
        if distribution_file.name == "METADATA":
            return Path(distribution.locate_file(distribution_file))
    return None


try:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    expected_dependencies = {
        normalise_requirement_name(requirement)
        for requirement in project.get("dependencies", [])
    }
    distribution = metadata.distribution(project["name"])
    installed_dependencies = {
        normalise_requirement_name(requirement)
        for requirement in distribution.requires or []
        if "extra ==" not in requirement
    }
    metadata_path = find_metadata_path(distribution)
except Exception:
    sys.exit(1)

if not expected_dependencies <= installed_dependencies:
    sys.exit(1)

if (
    metadata_path is None
    or not metadata_path.exists()
    or PYPROJECT.stat().st_mtime > metadata_path.stat().st_mtime
):
    sys.exit(1)
PY
  echo "Backend dependencies are out of date — running pip install…"
  "$VENV_PY" -m pip install -e "./backend[dev]"
fi

if ! "$VENV_PY" -c "import prometheus_client, uvicorn" >/dev/null 2>&1; then
  echo "Error: backend dependencies are missing from .venv" >&2
  echo "  \"$VENV_PY\" -m pip install -e \"./backend[dev]\"" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm was not found on PATH; install Node.js to run the frontend." >&2
  exit 1
fi

# Install frontend dependencies so `npm run dev` can start. Reinstall when the
# manifest is newer than the last install (npm records `node_modules/.package-
# lock.json`); otherwise a dependency bump leaves config-time imports such as
# `vitest/config` (used by vite.config.ts) unresolved and the dev server fails.
FRONTEND_DIR="$ROOT_DIR/frontend"
NODE_MODULES_MARKER="$FRONTEND_DIR/node_modules/.package-lock.json"
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing frontend dependencies (first run)…"
  (cd "$FRONTEND_DIR" && npm install)
elif [[ "$FRONTEND_DIR/package.json" -nt "$NODE_MODULES_MARKER" \
     || "$FRONTEND_DIR/package-lock.json" -nt "$NODE_MODULES_MARKER" ]]; then
  echo "Frontend dependencies are out of date — running npm install…"
  (cd "$FRONTEND_DIR" && npm install)
fi

# The backend's Settings() fails fast (and the server exits) when the required
# Trakt/Seer credentials are unset. On a first run without real
# credentials, seed a .env from the example with placeholders so the stack
# still comes up; the developer replaces them when ready. `.env` is
# git-ignored, so this stays local.
if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "No .env found — creating one for local development."
  if [[ -f "$ROOT_DIR/.env.example" ]]; then
    # Fill only the empty required secrets with a placeholder; keep the rest.
    sed -E 's/^(TRAKT_CLIENT_ID|TRAKT_CLIENT_SECRET|SEER_API_KEY)=[[:space:]]*$/\1=changeme/' \
      "$ROOT_DIR/.env.example" > "$ROOT_DIR/.env"
  else
    cat > "$ROOT_DIR/.env" <<'ENV_TEMPLATE'
TRAKT_CLIENT_ID=changeme
TRAKT_CLIENT_SECRET=changeme
SEER_URL=http://localhost:5055
SEER_API_KEY=changeme
ENV_TEMPLATE
  fi
  echo "  -> wrote .env with PLACEHOLDER credentials. Replace TRAKT_CLIENT_ID/SECRET" >&2
  echo "     and SEER_URL/API_KEY with real values to drive the sync loop" >&2
  echo "     (see the README 'Configuration' section)." >&2
fi

# --- Free the dev ports left bound by a previous run --------------------------
# A hard exit — or a Ctrl+C that does not fully reap the children, which happens
# on Windows where uvicorn/Vite can be orphaned — leaves a server holding its
# port, so the next start fails to bind. Stop whatever is still listening on the
# backend/frontend ports first so re-running `bash dev.sh` restarts a clean stack.
free_port() {
  local port="$1" label="$2" pids pid
  if [[ "$IS_WINDOWS" == 1 ]]; then
    # netstat columns: Proto Local-Address Foreign-Address State PID. Keep the
    # PID (last column) of every LISTENING socket whose local address ends in
    # ":PORT" (matches 127.0.0.1, 0.0.0.0 and [::1] forms alike).
    pids="$(netstat -ano 2>/dev/null \
      | awk -v port="$port" \
          '$1 == "TCP" && $4 == "LISTENING" && $2 ~ (":" port "$") { print $NF }' \
      | sort -u || true)"
  else
    # lsof is the portable port→owner lookup on macOS/Linux; without it this
    # yields nothing and start-up proceeds unchanged.
    pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
  fi
  [[ -z "$pids" ]] && return 0
  echo "Port $port ($label) is busy — stopping leftover process(es): $(echo $pids | tr '\n' ' ')"
  for pid in $pids; do
    if [[ "$IS_WINDOWS" == 1 ]]; then
      taskkill //PID "$pid" //T //F >/dev/null 2>&1 || true
    else
      kill "$pid" 2>/dev/null || true
    fi
  done
  # Give the OS a moment to release the socket before we rebind it.
  sleep 1 || true
}

free_port "$BACKEND_PORT" backend
free_port "$FRONTEND_PORT" frontend

# --- Start both servers and shut them down together ---------------------------
pids=()
cleaned=0

cleanup() {
  [[ "$cleaned" == 1 ]] && return
  cleaned=1
  trap - INT TERM
  printf '\nStopping dev servers…\n'
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo "Starting backend on http://${BACKEND_HOST}:${BACKEND_PORT} …"
if [[ "$IS_WINDOWS" == 1 ]]; then
  # uvicorn's own --reload restart hangs on Windows: on a change it signals the
  # worker with CTRL_C_EVENT and then joins it with no timeout, but the spawned
  # worker never receives the event, so the reloader blocks forever and the
  # server stops applying edits. Wrap a plain uvicorn with watchfiles (ships
  # with uvicorn[standard]) instead — it restarts the whole process and
  # escalates to a hard kill if the child does not stop, so it reloads
  # reliably. watchfiles' subprocess needs a native Windows path for the
  # interpreter, so translate the venv Python out of its /c/... Git Bash form.
  PY_WIN="$(cygpath -w "$VENV_PY" 2>/dev/null || printf '%s' "$VENV_PY")"
  "$VENV_PY" -m watchfiles --filter python \
    "$PY_WIN -m uvicorn main:app --app-dir backend --host $BACKEND_HOST --port $BACKEND_PORT" \
    backend &
else
  # macOS/Linux: uvicorn's native worker reload works and is faster.
  "$VENV_PY" -m uvicorn main:app \
    --app-dir backend \
    --reload \
    --reload-dir backend \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" &
fi
pids+=("$!")

echo "Starting frontend (vite dev server) …"
(cd "$ROOT_DIR/frontend" && npm run dev) &
pids+=("$!")

echo
echo "Dev environment is up — press Ctrl+C to stop both servers."
echo "  Frontend: http://localhost:${FRONTEND_PORT}  (proxies /api and /webhook to the backend)"
echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo

# Exit as soon as either server stops, then tear the other one down. `wait -n`
# would be ideal but needs Bash 4.3+; macOS ships Bash 3.2, so poll the child
# PIDs portably instead. A Ctrl+C during the sleep fires the trap, which kills
# both PIDs — the next check then sees them gone and breaks out.
while :; do
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || break 2
  done
  sleep 1 || true
done
cleanup
