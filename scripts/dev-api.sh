#!/usr/bin/env bash
set -euo pipefail

cd /workspace

export PYTHONPATH="/workspace/apps/api:/workspace/apps/runner${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "pyproject.toml" ]; then
  echo "未找到 /workspace/pyproject.toml" >&2
  exit 1
fi

exec python -m uvicorn platform_api.main:app --host 0.0.0.0 --port 8000
