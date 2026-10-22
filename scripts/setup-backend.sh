#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"

echo "Installing pinned Python dependencies from requirements.txt ..."
if ! python3 -m pip install -r requirements.txt; then
  echo ""
  echo "If supabase/pyiceberg failed to build, install build headers then retry:"
  echo "  Fedora/RHEL: sudo dnf install -y python3-devel gcc"
  echo "  Debian/Ubuntu: sudo apt install -y python3-dev build-essential"
  exit 1
fi

python3 -c "from app.main import app; print('Backend import OK')"
