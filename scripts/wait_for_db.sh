#!/bin/sh
set -e

MAX_RETRIES="${DB_WAIT_RETRIES:-24}"
SLEEP_INTERVAL="${DB_WAIT_SLEEP:-5}"
DATABASE_HOST="${DATABASE_HOST:-assets-db}"
DATABASE_USER="${DATABASE_USER:-ralph_ng}"
DATABASE_PASSWORD="${DATABASE_PASSWORD:-ralph_ng}"
DATABASE_NAME="${DATABASE_NAME:-ralph_ng}"

i=0

while ! python - <<PY >/dev/null 2>&1
import os
import MySQLdb

host = os.environ["DATABASE_HOST"]
user = os.environ["DATABASE_USER"]
password = os.environ["DATABASE_PASSWORD"]
name = os.environ["DATABASE_NAME"]

conn = MySQLdb.connect(host=host, user=user, passwd=password, database=name)
conn.close()
PY
do
  i=$((i + 1))
  if [ "$i" -ge "$MAX_RETRIES" ]; then
    total_seconds=$((MAX_RETRIES * SLEEP_INTERVAL))
    printf 'Database not available after %d seconds.\n' "$total_seconds" >&2
    exit 1
  fi
  printf 'Waiting for database... (%d/%d)\n' "$i" "$MAX_RETRIES"
  sleep "$SLEEP_INTERVAL"
done
