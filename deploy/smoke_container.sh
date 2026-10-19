#!/usr/bin/env bash
# Smoke-test a built cloud image (CI, .github/workflows/cloud.yml):
#   - the server starts as a non-root user and answers its health check inside the container
#   - from outside the container, every request without a Cloudflare Access token is refused
#   - cloud mode refuses to start at all without the Access settings (fails closed)
set -euo pipefail
IMAGE=${1:?image}
NAME=lacuna-smoke
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -p 127.0.0.1:18765:8765 \
  -e CF_ACCESS_TEAM_DOMAIN=smoke.cloudflareaccess.com -e CF_ACCESS_AUD=smoke "$IMAGE" >/dev/null

for i in $(seq 1 60); do
  if docker exec "$NAME" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)" 2>/dev/null; then
    break
  fi
  [ "$i" = 60 ] && { docker logs "$NAME"; echo "server did not come up"; exit 1; }
  sleep 1
done
echo "health ok inside the container"

[ "$(docker exec "$NAME" id -u)" != 0 ] || { echo "runs as root"; exit 1; }
docker exec "$NAME" ffmpeg -version >/dev/null
docker exec "$NAME" python -c "import sherpa_onnx, anthropic, jwt"
[ "$(docker exec "$NAME" cat /app/VERSION)" != "" ]

for path in / /api/health /api/app /api/episodes /api/auth/status; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:18765$path")
  [ "$code" = 403 ] || { echo "$path answered $code without an Access token"; exit 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Cf-Access-Jwt-Assertion: forged' "http://127.0.0.1:18765$path")
  [ "$code" = 403 ] || { echo "$path answered $code to a forged token"; exit 1; }
done
echo "outside requests without a valid Access token: 403"

if docker run --rm "$IMAGE" timeout 30 python -m lacuna_app --host 0.0.0.0 --no-browser >/tmp/failclosed.log 2>&1; then
  echo "started without Access settings"; exit 1
fi
grep -q CF_ACCESS /tmp/failclosed.log || { cat /tmp/failclosed.log; exit 1; }
echo "refuses to start without Access settings"
docker image inspect "$IMAGE" --format 'image size: {{.Size}} bytes'
