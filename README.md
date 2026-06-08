# OAWS Aktien-Tracker

Listet **jede im Podcast „Ohne Aktien wird schwer" (OAWS) vorgestellte Aktie** und
vergleicht den **Kurs am Vorstellungstag** mit dem **heutigen Kurs**. Ergebnis: ein
statisches, sortierbares Dashboard mit Kennzahlen.

> **Keine Anlageberatung. Alle Daten ohne Gewähr.**

„Vorgestellt" = in der Folgenbeschreibung steht `Firmenname (WKN: XXXXXX)`.
News-Ticker-Erwähnungen ohne WKN zählen nicht. Sentiment (bullish/bearish/Short)
ist egal.

## Schnellstart

```bash
make setup     # venv + Abhängigkeiten
make update    # Pipeline (Episoden → Extraktion → Ticker → Kurse → build)
make serve     # Dashboard unter http://localhost:8000
make test      # Golden-Fixtures der WKN-Extraktion
```

`make update` ist **inkrementell**: Episoden werden über `guid` entdoppelt, der
Ticker-Cache (`data/wkn_map.json`) und Kurs-Cache (`data/prices.json`) respektiert.

### Slice-first (empfohlen beim ersten Lauf)

Der RSS-Feed liefert das volle Archiv (1400+ Folgen, ~1600 Aktien). Für einen
schnellen ersten End-to-End-Lauf nur die jüngsten Vorstellungen auflösen, dann
das Vollarchiv nachziehen:

```bash
make episodes && make extract
.venv/bin/python pipeline/resolve_tickers.py --since-days 90
.venv/bin/python pipeline/fetch_prices.py   --since-days 90
make build
# später: Vollarchiv (ohne --since-days), läuft länger
.venv/bin/python pipeline/resolve_tickers.py
.venv/bin/python pipeline/fetch_prices.py
make build
```

## Pipeline

| Skript | Aufgabe | Output |
|---|---|---|
| `fetch_episodes.py` | RSS-Feed via iTunes-Lookup → Episoden | `data/episodes.json` |
| `extract_stocks.py` | `(Firma, WKN)` aus Beschreibungen (Regex, §8) | `data/mentions.json` |
| `resolve_tickers.py` | WKN → Yahoo-Ticker (Override → OpenFIGI → yfinance-Validierung) | `data/wkn_map.json` |
| `fetch_prices.py` | Entry-Close (≤ Vorstellungstag) + heutiger Close + Währung | `data/prices.json` |
| `build.py` | Δ abs./%, Tage, Aggregate | `public/data.json`, `public/meta.json` |

## Ticker-Resolution (`data/wkn_map.json`)

Dreistufig, selbstkorrigierend:

1. **Override-Map** (manuell, `"source":"override"`) gewinnt immer — hier landen Korrekturen.
2. **OpenFIGI** (`ID_WERTPAPIER` = WKN) liefert Kandidaten; alle plausiblen Yahoo-Symbole
   werden per **yfinance** validiert, das **liquideste** (= Primärnotierung) gewinnt.
   So landet z. B. Hensoldt auf `HAG.DE` (Xetra/EUR) statt auf einem US-OTC-Graumarkt.
3. Nicht auflösbar → `resolved:false`, in der Tabelle „n/a", aus Rankings ausgeschlossen.

Eine WKN falsch aufgelöst? Eintrag in `wkn_map.json` mit `"source":"override"` setzen —
er wird beim nächsten Lauf nicht überschrieben.

Optional `OPENFIGI_API_KEY` in `.env`/Umgebung für höheres Rate-Limit.

## Konfiguration

- **Entry-Kurs-Regel:** `--mode on_or_before` (Default, letzter Close ≤ Tag) oder
  `--mode on_or_after` (erster Close ≥ Tag, realistischer Listener-Fill) in `fetch_prices.py`.
- **Δ% in Heimatwährung** des Tickers — keine FX-Umrechnung (beide Punkte gleiche Notierung).

## Deploy

Statischer Host (`public/`). Tägliches Refresh via Cron/GitHub Actions: `make update`.
Für Self-Hosting auf Proxmox siehe `MIGRATE-TO-NODE1.md`.
