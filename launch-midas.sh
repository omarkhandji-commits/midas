#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "MIDAS local launcher"
echo "--------------------"
echo "This installs/starts MIDAS locally, then opens the dashboard."
echo "Keep this terminal open while you use MIDAS. Close it to stop the server."
echo

if command -v python3.11 >/dev/null 2>&1; then
  PY_CMD="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PY_CMD="python"
else
  echo "Python 3.11+ was not found."
  echo "Install Python from https://www.python.org/downloads/ and run this file again."
  exit 1
fi

"$PY_CMD" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
if [ $? -ne 0 ]; then
  echo "MIDAS needs Python 3.11 or newer."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating a private MIDAS Python environment..."
  "$PY_CMD" -m venv .venv
fi

echo "Installing/updating MIDAS dependencies..."
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -e ".[web,llm,multimodal,telegram,sheets,docs]"

echo "Preparing local state..."
".venv/bin/midas" setup

echo
echo "Starting MIDAS..."
echo "Your browser should open automatically. If it does not, copy the Direct link below."
echo
".venv/bin/midas" dashboard --host 127.0.0.1 --port 8765 --base-dir . --show-link
