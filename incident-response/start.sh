#!/bin/sh
set -eu

if [ -n "${OPENAI_API_KEY:-}" ]; then
  printf '%s' "$OPENAI_API_KEY" | codex login --with-api-key >/dev/null
fi

exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8001
