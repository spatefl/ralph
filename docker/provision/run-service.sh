#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sirius-ralph}"
RALPH_PORT="${RALPH_PORT:-8005}"
MAX_DB_WAIT_SECONDS="${MAX_DB_WAIT_SECONDS:-120}"
VENV_BIN="${APP_DIR}/venv/bin"
cd "${APP_DIR}"

start_time=$(date +%s)
until "${VENV_BIN}/ralph" check --database default --fail-level ERROR >/dev/null 2>&1; do
  current_time=$(date +%s)
  if (( current_time - start_time > MAX_DB_WAIT_SECONDS )); then
    echo "Database not available after ${MAX_DB_WAIT_SECONDS}s, aborting." >&2
    exit 1
  fi
  echo "Waiting for database to become available..."
  sleep 5
done

"${VENV_BIN}/ralph" migrate --noinput

if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_EMAIL:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  "${VENV_BIN}/ralph" shell <<'PY'
import os
from django.contrib.auth import get_user_model

username = os.environ["DJANGO_SUPERUSER_USERNAME"]
email = os.environ["DJANGO_SUPERUSER_EMAIL"]
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]
User = get_user_model()
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
PY
fi

exec "${VENV_BIN}/dev_ralph" runserver --insecure 0.0.0.0:${RALPH_PORT}
