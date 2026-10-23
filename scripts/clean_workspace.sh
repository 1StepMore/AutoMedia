#!/usr/bin/env bash
# Workspace hygiene cleaner (tooling for issue #288).
#
# Removes untracked run-artifact clutter from the repo root — test-project
# directories like `20261022_test-topic/`, plus `.coverage` / `.hypothesis` /
# coverage artefacts — WITHOUT touching any tracked file.  Every path it
# deletes is matched by an explicit pattern below; nothing else is ever
# removed.
#
# Default is --dry-run: print what would go, delete nothing.  Pass --yes
# (or answer `y`) to actually delete.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="dry-run"
if [[ "${1:-}" == "--yes" ]]; then
  MODE="delete"
elif [[ "${1:-}" != "--dry-run" ]]; then
  echo "usage: $(basename "$0") [--dry-run|--yes]" >&2
  exit 2
fi

# Explicit artifact patterns — date-prefixed test project dirs plus known
# untracked run detritus.  Keep this list literal: no glob expansion games.
candidates=""
while IFS= read -r d; do
  candidates="${candidates:+$candidates
}$d"
done < <(find . -maxdepth 1 -type d -name "202[0-9]*" -printf "%f\n" || true)
for extra in .coverage coverage.xml test-results.xml; do
  if [[ -e "$extra" ]]; then
    candidates="$candidates
$extra"
  fi
done

if [[ -z "$candidates" ]]; then
  echo "workspace is clean — nothing to do"
  exit 0
fi

total=0
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  # Never touch anything git tracks.
  if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    echo "SKIP (tracked): $path"
    continue
  fi
  total=$((total + 1))
  if [[ "$MODE" == "delete" ]]; then
    rm -rf "$path"
    echo "removed: $path"
  else
    echo "would remove: $path"
  fi
done <<< "$candidates"

if [[ "$MODE" == "dry-run" ]]; then
  echo "dry-run: $total candidate(s); rerun with --yes to delete"
else
  echo "deleted $total path(s)"
fi
