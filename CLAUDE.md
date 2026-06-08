# oaws — Projekt-Notizen für Claude Code

OAWS Aktien-Tracker. Build-Runbook: `oaws-tracker-anleitung.md`. Deployment: `MIGRATE-TO-NODE1.md`.
Bedienung/Architektur: `README.md`.

## Kommandos

```bash
make setup     # venv + Abhängigkeiten
make update    # volle Pipeline (Episoden→Extraktion→Ticker→Kurse→build)  ← Backfill, läuft lange
make build     # nur neu rechnen aus vorhandenen Caches
make serve     # http://localhost:8000
make test      # Golden-Fixtures der WKN-Extraktion
```

Slice-first (schneller Erstlauf): `resolve_tickers.py`/`fetch_prices.py` mit `--since-days 90`.

## Konventionen für dieses Repo

- **Ticker falsch aufgelöst?** Eintrag in `data/wkn_map.json` mit `"source":"override"` setzen — wird nie überschrieben.
- **Kurs-Layer** (yfinance) ist hinter Funktionen gekapselt (`fetch_prices.py`) — austauschbar halten.
- **Δ% in Heimatwährung** des Tickers, keine FX-Umrechnung.
- Caches (`data/cache/`, `.env`) sind gitignored; `data/wkn_map.json` ist committed (Override-Map + Cache).

## Linear

Projekt **oaws** (Team Kolja Sagorski, Key `KOL`): https://linear.app/sagorski/project/oaws-88b11ca44c7d
Build-Issue: **KOL-22** — https://linear.app/sagorski/issue/KOL-22
