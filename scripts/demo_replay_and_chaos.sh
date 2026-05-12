#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$(pwd)"

echo "== Replay search =="
python replay_browser/search_replays.py

echo
echo "== Replay diff =="
python replay_browser/replay_diff_viewer.py

echo
echo "== Chaos scenarios =="
find chaos -maxdepth 1 -type f | sort

echo
echo "== Dashboard artifacts =="
find dashboard -maxdepth 1 -type f | sort
