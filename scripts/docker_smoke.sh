#!/usr/bin/env bash
# Checks the running compose stack the way an outsider and the admin would see it.
set -euo pipefail

BASE=http://127.0.0.1:8000
fail() { echo "FAILED: $1" >&2; exit 1; }
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

[ "$(status "$BASE/healthz")" = 200 ] || fail "health check"
[ "$(status "$BASE/api/catalog/items")" = 401 ] || fail "API must require a login"
[ "$(status -X POST "$BASE/api/folders" -H 'Content-Type: application/json' -d '{"name":"x"}')" = 401 ] \
  || fail "writes must require a login"
[ "$(status "$BASE/" -H 'Host: evil.example')" = 400 ] || fail "unknown Host must be refused"
curl -s "$BASE/" | grep -q '<title>Wiredbench' || fail "frontend must be served"
curl -s -D - -o /dev/null "$BASE/" | grep -qi '^content-security-policy:' || fail "CSP header"

[ "$(docker compose exec -T wiredbench id -u)" = 10001 ] || fail "must run as non-root"
if docker compose exec -T wiredbench sh -c 'touch /app/x' 2>/dev/null; then fail "filesystem must be read-only"; fi

PASSWORD=$(docker compose exec -T wiredbench cat /data/initial-admin-password | tr -d '\r\n')
JAR=$(mktemp)
BODY=$(python3 -c 'import json,sys; print(json.dumps({"username":"admin","password":sys.argv[1]}))' "$PASSWORD")
[ "$(status -c "$JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "$BODY")" = 200 ] \
  || fail "admin login"
[ "$(status -b "$JAR" "$BASE/api/settings")" = 200 ] || fail "admin read"
rm -f "$JAR"

docker compose restart wiredbench >/dev/null
for _ in $(seq 1 30); do
  [ "$(status "$BASE/healthz" || true)" = 200 ] && break
  sleep 1
done
[ "$(status "$BASE/healthz")" = 200 ] || fail "restart"
docker compose exec -T wiredbench test -s /data/wiredbench.db || fail "data must survive a restart"

echo "Smoke test passed."
