#!/usr/bin/env bash
# Auto-Deploy: vom GitHub-Webhook (server/app.py) detached gestartet.
# Holt den neuesten Code, aktualisiert Deps und startet den Web-Dienst neu.
# Generierte Daten/.env sind gitignored -> bleiben unangetastet.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p data
{
  echo "=== deploy $(date -u +%FT%TZ) ==="
  git fetch --quiet origin
  git reset --hard --quiet origin/master
  .venv/bin/pip install -q -r requirements.txt
  # systemd-Units evtl. aktualisiert -> neu rendern (idempotent)
  sudo systemctl daemon-reload 2>/dev/null || true
  # data.json aus vorhandenem Cache neu rechnen, damit build-abhaengige
  # Frontend-Features (z.B. neue Felder) sofort sichtbar sind – nicht erst
  # beim naechsten Tageslauf. Nicht-fatal: ein Build-Hickup blockiert kein Deploy.
  .venv/bin/python pipeline/build.py || echo "build uebersprungen (rc=$?)"
  echo "deployed $(git rev-parse --short HEAD)"
} >> data/deploy.log 2>&1
# Web-Dienst neu starten, damit Server-Code-Aenderungen greifen (Frontend ist statisch)
sudo systemctl restart oaws.service
