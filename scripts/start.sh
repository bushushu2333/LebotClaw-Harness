#!/bin/sh
set -eu
LEBOT_PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$LEBOT_PROJECT_DIR"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e '.[documents,browser,secure-keys]'
  .venv/bin/python -m playwright install chromium
fi
exec .venv/bin/python -m lebotclaw_harness web --open "$@"
