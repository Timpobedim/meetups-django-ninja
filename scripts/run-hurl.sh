#!/usr/bin/env bash
# Прогон Hurl-сценариев против уже запущенного сервера.
# HOST — адрес API (по умолчанию http://localhost:8000). Нужен установленный hurl (https://hurl.dev).
set -euo pipefail

HOST="${HOST:-http://localhost:8000}"
RUN_ID="${RUN_ID:-$(date +%s)}"

hurl --test --color \
  --variable "host=${HOST}" \
  --variable "run=${RUN_ID}" \
  tests/hurl/*.hurl
