#!/bin/bash
set -euo pipefail
if [[ "$1" == apt ]]; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates gnupg python3
  install -m 644 /repo/steward/gpg.key /usr/share/keyrings/loomx-steward.asc
  echo 'deb [signed-by=/usr/share/keyrings/loomx-steward.asc] file:/repo/steward/apt stable main' > /etc/apt/sources.list.d/loomx-steward.list
  apt-get update
  apt-get install -y steward
  apt-get install -y --only-upgrade steward
else
  dnf install -y python3
  sed 's|https://loomx-ai.github.io/packages/steward|file:///repo/steward|g' /repo/steward/steward.repo > /etc/yum.repos.d/loomx-steward.repo
  dnf install -y steward
  dnf upgrade -y steward
fi
version=$(python3 -c 'import json; print(json.load(open("/repo/steward/releases.json"))["latest"])')
test "$(steward --version)" = "steward version $version"
mkdir -p /tmp/steward-smoke
cd /tmp/steward-smoke
steward server start --addr 127.0.0.1:8585 > /tmp/steward-smoke.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
python3 - <<'PY'
import json, time, urllib.request
for attempt in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8585/api/providers/catalog', timeout=2) as response:
            assert response.status == 200
            json.load(response)
        break
    except OSError:
        time.sleep(0.5)
else:
    raise RuntimeError(open('/tmp/steward-smoke.log').read())
with urllib.request.urlopen('http://127.0.0.1:8585') as response:
    assert '<script' in response.read().decode()
PY
steward server status
steward server stop
wait "$pid"
if [[ "$1" == apt ]]; then apt-get remove -y steward; else dnf remove -y steward; fi
test -f "$HOME/.steward/steward.db"
test ! -e .steward
echo 'PASS: signed repository install, upgrade, server, uninstall, and preserved data'
