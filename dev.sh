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

# --- Locate the virtual environment's Python (Unix vs Windows/Git Bash) -------
if [[ -f "$ROOT_DIR/.venv/bin/python" ]]; then
  VENV_PY="$ROOT_DIR/.venv/bin/python"
elif [[ -f "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  VENV_PY="$ROOT_DIR/.venv/Scripts/python.exe"
else
  echo "Error: no virtual environment found at .venv/" >&2
  echo "Create one and install the backend (with dev extras) first:" >&2
  echo "  python -m venv .venv" >&2
  echo "  .venv/bin/pip install -e \"./backend[dev]\"   # .venv/Scripts/pip on Windows" >&2
  exit 1
fi

# --- Verify prerequisites -----------------------------------------------------
if ! "$VENV_PY" -c "import uvicorn" >/dev/null 2>&1; then
  echo "Error: uvicorn is not installed in .venv" >&2
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
# Trakt/Jellyseerr credentials are unset. On a first run without real
# credentials, seed a .env from the example with placeholders so the stack
# still comes up in DRY_RUN; the developer replaces them when ready. `.env` is
# git-ignored, so this stays local.
if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "No .env found — creating one for local development."
  if [[ -f "$ROOT_DIR/.env.example" ]]; then
    # Fill only the empty required secrets with a placeholder; keep the rest.
    sed -E 's/^(TRAKT_CLIENT_ID|TRAKT_CLIENT_SECRET|JELLYSEERR_API_KEY)=[[:space:]]*$/\1=changeme/' \
      "$ROOT_DIR/.env.example" > "$ROOT_DIR/.env"
  else
    cat > "$ROOT_DIR/.env" <<'ENV_TEMPLATE'
TRAKT_CLIENT_ID=changeme
TRAKT_CLIENT_SECRET=changeme
JELLYSEERR_URL=http://localhost:5055
JELLYSEERR_API_KEY=changeme
DRY_RUN=true
ENV_TEMPLATE
  fi
  echo "  -> wrote .env with PLACEHOLDER credentials; DRY_RUN stays on, so no" >&2
  echo "     real requests or removals happen. Replace TRAKT_CLIENT_ID/SECRET" >&2
  echo "     and JELLYSEERR_URL/API_KEY with real values to drive the sync loop" >&2
  echo "     (see the README 'Configuration' section)." >&2
fi

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

echo "Starting backend (uvicorn --reload) on http://${BACKEND_HOST}:${BACKEND_PORT} …"
"$VENV_PY" -m uvicorn main:app \
  --app-dir backend \
  --reload \
  --reload-dir backend \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" &
pids+=("$!")

echo "Starting frontend (vite dev server) …"
(cd "$ROOT_DIR/frontend" && npm run dev) &
pids+=("$!")

echo
echo "Dev environment is up — press Ctrl+C to stop both servers."
echo "  Frontend: http://localhost:5173  (proxies /api and /webhook to the backend)"
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
