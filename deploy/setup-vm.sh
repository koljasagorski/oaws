#!/usr/bin/env bash
# Idempotentes Setup des OAWS-Trackers in einer Debian-VM (User admin).
# Aufruf in der VM:  cd ~/oaws && OAWS_ADMIN_PASSWORD='...' bash deploy/setup-vm.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(id -un)"
cd "$APP_DIR"
echo "== OAWS setup in $APP_DIR als $RUN_USER =="

# 1) Zeitzone (Timer laeuft in System-TZ)
sudo timedatectl set-timezone Europe/Berlin || true

# 2) System-Pakete
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip rsync ca-certificates

# 3) venv + Python-Deps
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# 4) .env initialisieren (Secrets erzeugen, falls noch nicht vorhanden)
touch .env && chmod 600 .env
ensure_env() { grep -q "^$1=" .env || echo "$1=$2" >> .env; }
SESSION_SECRET="$(.venv/bin/python -c 'import secrets;print(secrets.token_hex(32))')"
ensure_env SESSION_SECRET "$SESSION_SECRET"
ensure_env OPENFIGI_API_KEY ""
if ! grep -q '^ADMIN_PASSWORD_HASH=' .env; then
  PW="${OAWS_ADMIN_PASSWORD:-$(.venv/bin/python -c 'import secrets;print(secrets.token_urlsafe(12))')}"
  HASH="$(.venv/bin/python -c "import sys;sys.path.insert(0,'server');from app import hash_password;print(hash_password('$PW'))")"
  echo "ADMIN_PASSWORD_HASH=$HASH" >> .env
  echo ">>> ADMIN-PASSWORT: $PW   (bitte merken und im Panel aendern)"
fi
chmod 600 .env

# 5) config.json (Default: Vollarchiv, 08:00)
[ -f data/config.json ] || .venv/bin/python -c "import sys;sys.path.insert(0,'pipeline');from common import save_config;save_config({'entry_mode':'on_or_before','scope_days':None,'schedule':'08:00'})"

# 6) systemd-Units aus Templates rendern
render() { sed -e "s#__APP_DIR__#$APP_DIR#g" -e "s#__USER__#$RUN_USER#g" "deploy/$1" | sudo tee "/etc/systemd/system/$1" >/dev/null; }
render oaws.service
render oaws-update.service
sudo cp deploy/oaws-update.timer /etc/systemd/system/oaws-update.timer
sudo cp deploy/oaws-set-schedule /usr/local/bin/oaws-set-schedule
sudo chmod +x /usr/local/bin/oaws-set-schedule

# 7) gewuenschte Cron-Zeit aus config.json in den Timer schreiben
SCHED="$(.venv/bin/python -c "import sys;sys.path.insert(0,'pipeline');from common import load_config;print(load_config()['schedule'])")"
sudo /usr/local/bin/oaws-set-schedule "$SCHED" || true

# 8) Dienste aktivieren
sudo systemctl daemon-reload
sudo systemctl enable --now oaws.service
sudo systemctl enable --now oaws-update.timer

echo "== fertig. Status: =="
sleep 2
systemctl --no-pager --full status oaws.service | head -6 || true
systemctl --no-pager list-timers oaws-update.timer || true
curl -s http://127.0.0.1:8000/healthz && echo
