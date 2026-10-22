#!/usr/bin/env bash
# Remove local build artifacts and legacy folders.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Removing build artifacts..."
rm -rf dist .next-local

if [[ -d frontend ]]; then
  echo "Removing legacy frontend/ (may need sudo if Docker created root-owned files)..."
  rm -rf frontend 2>/dev/null || sudo rm -rf frontend
fi

echo "Done."
