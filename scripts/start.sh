#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if command -v desktop-assistant >/dev/null 2>&1; then
  desktop-assistant "$@"
else
  python -m desktop_assistant "$@"
fi
