#!/usr/bin/env bash
# Run only after the operator approves this release. Never enables the timer.
set -Eeuo pipefail
umask 077
[[ ${1:-} == --apply-approved && ${2:-} =~ ^[0-9a-f]{40}$ ]] || {
  echo 'STOP: explicit release approval and full committed SHA required'; exit 2;
}
cd /home/ubuntu/munongsa
TARGET=$2
[[ $(git rev-parse HEAD) == "$TARGET" && -z $(git status --porcelain) ]] || {
  echo 'STOP: deploy only the reviewed clean commit'; exit 2;
}
[[ $(git branch --show-current) == main ]]
for tool in python3 curl; do command -v "$tool" >/dev/null; done
sudo -n docker info >/dev/null
if systemctl is-active --quiet munongsa-collector.timer || systemctl is-active --quiet munongsa-collector.service; then
  echo 'STOP: existing scheduled collector requires a separate upgrade review'; exit 2
fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=/home/ubuntu/munongsa-deploy-backups/collector-$STAMP
OLD=munongsa-before-collector-$STAMP
TEST=munongsa-check-collector-$STAMP
FAILED=munongsa-failed-collector-$STAMP
TAG=munongsa:collector-${TARGET:0:12}
mkdir -m 700 -p "$BACKUP"
# Inspect in memory. Never write environment values to logs or a JSON report.
sudo -n python3 - "$BACKUP" <<'PY'
import json, subprocess, sys
from pathlib import Path
def get(kind, name):
    return json.loads(subprocess.check_output(['docker', kind, 'inspect', name], stderr=subprocess.PIPE))[0]
c=get('container','munongsa'); h=c['HostConfig']; cfg=c['Config']; image=get('image',c['Image'])
assert c['State']['Running'], 'Existing site is not running'
assert not c['Mounts'], 'Existing mounts require review'
assert cfg.get('Env')==image['Config'].get('Env'), 'Custom environment requires review'
assert h['NetworkMode']=='bridge' and not h['Privileged'] and not h.get('CapAdd'), 'Custom Docker options require review'
assert cfg.get('Cmd')==['nginx','-g','daemon off;'] and cfg.get('Entrypoint')==['/docker-entrypoint.sh'], 'Custom command requires review'
assert h['RestartPolicy']['Name']=='unless-stopped', 'Restart policy requires review'
p=h['PortBindings']; assert set(p)=={'80/tcp'}
assert all(x['HostPort']=='80' and x.get('HostIp','') in ('','0.0.0.0','::') for x in p['80/tcp'])
Path(sys.argv[1],'container.json').write_text(json.dumps({'id':c['Id'],'image':c['Image'],'restart':'unless-stopped','port':80}))
PY
curl --noproxy '*' -fsS --max-time 10 http://127.0.0.1/ > "$BACKUP/home-before.html"
sudo -n docker cp munongsa:/usr/share/nginx/html "$BACKUP/public-before"
sudo -n docker image tag "$(sudo -n docker inspect --format '{{.Image}}' munongsa)" "munongsa:rollback-collector-$STAMP"
# Refuse an unmarked or imported trial DB before making any changes to it.
if [[ -f /var/lib/munongsa/monitor.sqlite3 && ! -f /var/lib/munongsa/runtime.json ]]; then
  echo 'STOP: existing DB needs explicit migration review'; exit 2
fi
curl --noproxy '*' -fsS --max-time 10 http://127.0.0.1/data/support-public.json > "$BACKUP/approved-feed-before.json"
python3 - "$BACKUP/approved-feed-before.json" <<'PY'
import json,sys
from pathlib import Path
feed=json.loads(Path(sys.argv[1]).read_text())
assert feed.get('schema_version')=='munongsa-support-public-v1'
assert isinstance(feed.get('notices'),list)
if not Path('/var/lib/munongsa/monitor.sqlite3').is_file():
    assert not feed['notices'], 'Existing approved public feed requires a reviewed migration; empty DB rollout stopped'
PY
sudo -n install -d -m 700 -o ubuntu -g ubuntu /var/lib/munongsa
sudo -n install -d -m 755 -o ubuntu -g ubuntu /var/lib/munongsa-public
python3 -m venv .venv-collector
.venv-collector/bin/python -m pip install --no-input --only-binary=:all: --retries 0 --timeout 15 --no-cache-dir --disable-pip-version-check -r deploy/collector/requirements.txt
# Initializes an empty review DB and a valid empty feed on the first release.
# Existing approved rows require a private, explicitly maintained rights manifest.
.venv-collector/bin/python -B scripts/run_support_collection.py --export-only
sudo -n install -m 644 deploy/collector/munongsa-collector.service /etc/systemd/system/
sudo -n install -m 644 deploy/collector/munongsa-collector.timer /etc/systemd/system/
sudo -n systemd-analyze verify /etc/systemd/system/munongsa-collector.service /etc/systemd/system/munongsa-collector.timer
sudo -n systemctl daemon-reload
# Apply public file permissions only; never touch private state or data/source.
python3 - <<'PY'
from pathlib import Path
files=[Path('index.html')]+[p for p in Path('assets').rglob('*') if p.is_file()]
files += [Path('data')/(n+'.json') for n in ('smart-agriculture-catalog','crop-cultivation-records','support-programs','support-public','support-review','finance-products','equipment-catalog')]
for p in files: p.chmod(0o644)
for p in [Path('assets'),Path('data')]+[p for p in Path('assets').rglob('*') if p.is_dir()]: p.chmod(0o755)
PY
sudo -n docker build -t "$TAG" .
sudo -n docker run -d --name "$TEST" -p 127.0.0.1:18080:80 \
  --mount type=bind,src=/var/lib/munongsa-public,dst=/srv/munongsa-public,readonly \
  --mount type=bind,src=/home/ubuntu/munongsa/deploy/collector/nginx.conf,dst=/etc/nginx/conf.d/default.conf,readonly "$TAG" >/dev/null
SWAPPED=0
rollback() {
  code=$?; trap - EXIT
  if [[ $code != 0 && $SWAPPED == 1 ]]; then
    sudo -n docker stop munongsa >/dev/null || true
    sudo -n docker rename munongsa "$FAILED" || true
    sudo -n docker rename "$OLD" munongsa
    sudo -n docker start munongsa >/dev/null
    echo 'Previous container restored; collector timer remains disabled'
  fi
  sudo -n docker stop "$TEST" >/dev/null 2>&1 || true
  exit "$code"
}
trap rollback EXIT
ready() {
  .venv-collector/bin/python -B - "$1" <<'PY'
import sys, time, urllib.request, urllib.error
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(12):
    try:
        with opener.open(sys.argv[1],timeout=3) as r:
            assert r.status==200
            r.read(1)
        break
    except urllib.error.HTTPError as e:
        if e.code not in (502,503,504): raise SystemExit('Permanent HTTP error')
    except (OSError, ConnectionError): pass
    if attempt==11: raise SystemExit('HTTP readiness timeout')
    time.sleep(1)
PY
}
sudo -n docker exec "$TEST" nginx -t
for path in / /assets/support-public.js /data/support-public.json /data/support-review.json; do ready "http://127.0.0.1:18080$path"; done
.venv-collector/bin/python -B - <<'PY'
import hashlib,json,urllib.request
from pathlib import Path
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
names=('smart-agriculture-catalog','crop-cultivation-records','support-programs','support-public','support-review','finance-products','equipment-catalog')
for name in names:
    with opener.open('http://127.0.0.1:18080/data/'+name+'.json',timeout=5) as response:
        data=response.read(4*1024*1024+1)
        assert len(data)<=4*1024*1024
        obj=json.loads(data)
    if name=='support-public':
        assert obj['schema_version']=='munongsa-support-public-v1'
        assert hashlib.sha256(data).digest()==hashlib.sha256(Path('/var/lib/munongsa-public/support-public.json').read_bytes()).digest()
for private in ('work/','scripts/support_monitor.py','.env','monitor.sqlite3','publication-rights.json'):
    try:
        opener.open('http://127.0.0.1:18080/'+private,timeout=5)
        raise AssertionError('Private path exposed')
    except urllib.error.HTTPError as error:
        assert error.code in (403,404)
PY
sudo -n docker stop munongsa >/dev/null
# The EXIT trap can restore either the renamed or still original container.
if ! sudo -n docker rename munongsa "$OLD"; then sudo -n docker start munongsa >/dev/null; exit 1; fi
SWAPPED=1
sudo -n docker run -d --name munongsa --restart unless-stopped -p 80:80 \
  --mount type=bind,src=/var/lib/munongsa-public,dst=/srv/munongsa-public,readonly \
  --mount type=bind,src=/home/ubuntu/munongsa/deploy/collector/nginx.conf,dst=/etc/nginx/conf.d/default.conf,readonly "$TAG" >/dev/null
for path in / /data/support-public.json /assets/support-public.js; do ready "http://127.0.0.1$path"; done
SWAPPED=0
printf 'Local server checks passed. Previous container: %s\nPrivate backup: %s\nTimer NOT enabled. External PC/mobile verification still required.\n' "$OLD" "$BACKUP"
