#!/usr/bin/env bash
#
# Cut a SemVer release for all-in-one-ARR.
#
# Derives the current version from the latest `vX.Y.Z` git tag, computes the next
# version from the requested bump level, updates the in-repo version manifests,
# commits them, creates an annotated `vX.Y.Z` tag, and pushes the branch and tag
# to `origin`. GitHub Actions (.github/workflows/docker-publish.yml) then publishes
# the Docker image and, after the tag build succeeds, creates the GitHub Release.
# The tag push builds `erenatbas/aio-arr:X.Y.Z` (+ `:X.Y`) and also refreshes
# `:latest`; pushes to the branch no longer trigger the workflow.
#
# Usage:
#   scripts/release.sh [major|minor|patch] [flags]
#
#   (no level)  patch bump   e.g. 1.6.0 -> 1.6.1   (default)
#   patch       patch bump   e.g. 1.6.0 -> 1.6.1
#   minor       minor bump   e.g. 1.6.0 -> 1.7.0
#   major       major bump   e.g. 1.6.0 -> 2.0.0
#
# Flags:
#   --dry-run       Show the computed version and planned actions; change nothing.
#   --skip-checks   Skip the local ./scripts/check.sh pre-flight (Ruff lint + format,
#                   mypy, Prettier, tests, build). CI re-runs the same gates on the
#                   pushed tag, so they still gate the Docker publish.
#   -y, --yes       Do not prompt for confirmation before committing/pushing.
#   -h, --help      Show this help and exit.
#
# Environment:
#   RELEASE_BRANCH  Branch a release must be cut from (default: main).
#
# If no `vX.Y.Z` tag exists yet, the first release establishes the baseline 1.0.0.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RELEASE_BRANCH="${RELEASE_BRANCH:-main}"
REMOTE="origin"

level="patch"
dry_run=false
skip_checks=false
assume_yes=false

usage() {
  cat <<'EOF'
Cut a SemVer release: bump the version, commit, tag vX.Y.Z, and push for the Docker release.

Usage: scripts/release.sh [major|minor|patch] [flags]

  (no level)  patch bump   e.g. 1.6.0 -> 1.6.1   (default)
  minor       minor bump   e.g. 1.6.0 -> 1.7.0
  major       major bump   e.g. 1.6.0 -> 2.0.0

Flags:
  --dry-run       Show the computed version and planned actions; change nothing.
  --skip-checks   Skip the local scripts/check.sh pre-flight (Ruff, mypy, Prettier,
                  tests, build). CI re-runs these gates on the pushed tag.
  -y, --yes       Do not prompt for confirmation before committing/pushing.
  -h, --help      Show this help and exit.

Environment:
  RELEASE_BRANCH  Branch a release must be cut from (default: main).
EOF
}

die() {
  echo "release: $*" >&2
  exit 1
}

# ---- Parse arguments -------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    major|minor|patch) level="$arg" ;;
    --dry-run) dry_run=true ;;
    --skip-checks) skip_checks=true ;;
    -y|--yes) assume_yes=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "release: unknown argument '$arg'" >&2; echo >&2; usage; exit 2 ;;
  esac
done

# ---- Preconditions (always) ------------------------------------------------
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git work tree"

echo "==> Fetching tags from $REMOTE"
git fetch --tags --quiet "$REMOTE"

# ---- Determine current and next version ------------------------------------
latest_tag="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n1)"

if [[ -z "$latest_tag" ]]; then
  # No release yet: this run establishes the 1.0.0 baseline regardless of level.
  new_version="1.0.0"
  current_desc="none"
else
  [[ "$latest_tag" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] \
    || die "latest tag '$latest_tag' is not a plain vX.Y.Z version"
  major="${BASH_REMATCH[1]}"
  minor="${BASH_REMATCH[2]}"
  patch="${BASH_REMATCH[3]}"
  current_desc="$latest_tag"
  # 10# forces base-10 so a component is never misread as octal.
  case "$level" in
    major) new_version="$((10#$major + 1)).0.0" ;;
    minor) new_version="${major}.$((10#$minor + 1)).0" ;;
    patch) new_version="${major}.${minor}.$((10#$patch + 1))" ;;
  esac
fi

new_tag="v${new_version}"

# ---- Guard against an existing target tag ----------------------------------
if git rev-parse -q --verify "refs/tags/${new_tag}" >/dev/null; then
  die "tag ${new_tag} already exists locally"
fi
if remote_tag="$(git ls-remote --tags "$REMOTE" "refs/tags/${new_tag}")"; then
  [[ -z "$remote_tag" ]] || die "tag ${new_tag} already exists on $REMOTE"
else
  die "could not query tags on $REMOTE"
fi

echo "==> Release: ${current_desc} -> ${new_tag}  (level: ${level}, branch: ${RELEASE_BRANCH})"

# ---- Dry run stops here (no mutations) -------------------------------------
if [[ "$dry_run" == true ]]; then
  cat <<EOF

Dry run — no changes made. A real release would:
  1. update backend/pyproject.toml and frontend/package.json to ${new_version}
  2. git commit -m "chore(release): ${new_tag}"
  3. git tag -a ${new_tag} -m "Release ${new_tag}"
  4. git push --follow-tags ${REMOTE} ${RELEASE_BRANCH}
     -> CI publishes docker.io/erenatbas/aio-arr:${new_version} (+ :X.Y and :latest)
     -> CI creates the GitHub Release after the tag build succeeds
EOF
  exit 0
fi

# ---- Real-release preconditions --------------------------------------------
current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$RELEASE_BRANCH" ]]; then
  die "must release from '$RELEASE_BRANCH' (on '$current_branch'). Override with RELEASE_BRANCH=..."
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  die "working tree is not clean; commit or stash changes before releasing"
fi

# ---- Optional pre-flight checks --------------------------------------------
if [[ "$skip_checks" == true ]]; then
  echo "==> Skipping local checks (--skip-checks); CI still gates the publish"
else
  echo "==> Running local checks (scripts/check.sh); pass --skip-checks to skip"
  ./scripts/check.sh
fi

# ---- Confirm ---------------------------------------------------------------
if [[ "$assume_yes" != true && "${CI:-}" != "true" ]]; then
  if [[ ! -t 0 ]]; then
    die "refusing to release non-interactively without --yes"
  fi
  read -r -p "Release ${new_tag} and push to ${REMOTE}/${RELEASE_BRANCH}? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || die "aborted by user"
fi

# ---- Update version manifests ----------------------------------------------
echo "==> Updating frontend/package.json (+ lockfile)"
( cd frontend && npm version "$new_version" --no-git-tag-version --allow-same-version >/dev/null )

echo "==> Updating backend/pyproject.toml"
# Guard: exactly one top-level version to bump (the [project] version). The file
# also carries [tool.ruff]/[tool.mypy] config; none of those lines start with
# `version = "`, but a future section must not silently gain a second one.
# `|| true`: grep -c exits 1 on zero matches, which would abort the script here
# under `set -e` before the guard below could report it — keep going so the
# `-eq 1` check handles 0/1/N uniformly with a clear message.
version_lines="$(grep -cE '^version = "' backend/pyproject.toml || true)"
[[ "$version_lines" -eq 1 ]] \
  || die "expected exactly one version line in backend/pyproject.toml, found ${version_lines}"
perl -0pi -e "s/^version = \"[^\"]*\"/version = \"${new_version}\"/m" backend/pyproject.toml
grep -qxF "version = \"${new_version}\"" backend/pyproject.toml \
  || die "failed to update version in backend/pyproject.toml"

# ---- Commit, tag, push -----------------------------------------------------
echo "==> Committing release"
git add backend/pyproject.toml frontend/package.json frontend/package-lock.json
git commit -m "chore(release): ${new_tag}"

echo "==> Tagging ${new_tag}"
git tag -a "$new_tag" -m "Release ${new_tag}"

echo "==> Pushing ${RELEASE_BRANCH} and ${new_tag} to ${REMOTE}"
git push --follow-tags "$REMOTE" "$RELEASE_BRANCH"

cat <<EOF

Pushed ${new_tag}. CI will publish the image and GitHub Release after its checks pass.
  Actions: https://github.com/eatbas/all-in-one-ARR/actions
  Release: https://github.com/eatbas/all-in-one-ARR/releases/tag/${new_tag}
  Image:   docker.io/erenatbas/aio-arr:${new_version}  (and :latest)
EOF
