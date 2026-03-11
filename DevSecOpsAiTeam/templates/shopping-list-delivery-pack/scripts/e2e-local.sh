#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${APP_PORT:-8080}"

mvn -B -ntp clean test package

java -jar target/shopping-list-app-1.0.0.jar >/tmp/shopping-list-app.log 2>&1 &
APP_PID=$!
trap 'kill ${APP_PID} >/dev/null 2>&1 || true' EXIT

echo "Waiting for app on http://localhost:${APP_PORT} ..."
for _ in {1..45}; do
  if curl -fsS "http://localhost:${APP_PORT}" >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS "http://localhost:${APP_PORT}" | grep -qi "shopping" || {
  echo "Smoke test failed: main page did not contain expected content."
  exit 1
}

echo "E2E smoke passed."
