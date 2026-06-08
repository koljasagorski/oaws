# Anleitung für Claude Code: OAWS Aktien-Tracker

> Build-Runbook. Speicherbar als `CLAUDE.md` im Repo-Root oder als `docs/ANLEITUNG.md`.
> Prosa Deutsch, Code/Identifier Englisch. Inkrementell bauen: erst ein funktionierender vertikaler Slice (letzte 90 Tage), dann Backfill.

---

## 1. Ziel

Eine Seite, die **jede im Podcast „Ohne Aktien wird schwer" (OAWS) vorgestellte Aktie** auflistet und für jede Aktie den **Kurs am Tag der Vorstellung** mit dem **heutigen Kurs** vergleicht. Ergebnis: eine sortierbare Tabelle (größter Gewinner / Verlierer etc.) plus Kennzahlen-Übersicht. Täglich aktualisierbar.

**Kein Anlageberatungs-Produkt.** Disclaimer im Footer. Daten „ohne Gewähr".

---

## 2. Der zentrale Mechanismus (zuerst lesen)

OAWS ist der tägliche Börsenpodcast von Noah Leidinger / OMR (Apple-Podcast-ID `1542785062`). Jede Folge hat einen News-Ticker am Anfang **ohne** Kennnummern und danach 1–2 Deep-Dive-Aktien. Die Deep-Dives stehen in der Episodenbeschreibung **fast immer** so:

```
Firmenname (WKN: XXXXXX)
```

Reale Beispiele (als Golden-Fixtures verwenden, siehe §9):

| Datum (pubDate) | Firma | WKN |
|---|---|---|
| 2026-04-22 | D'Ieteren | A1H5AN |
| 2026-05-13 | IMAX | 896801 |
| 2026-05-15 | Sandoz | A3ETYB |
| 2026-05-15 | Markel | 885036 |
| 2026-05-21 | Daktronics | 923255 |
| 2026-05-29 | Amazon | 906866 |
| 2025-01 | Dick's Sporting Goods | 662541 |
| 2025-01 | Academy Sports + Outdoors | A2QDZ9 |
| — | OHB | 593612 |
| — | Versant Media | A41RUQ |
| — | Bread Financial | 934251 |

**Die WKN ist der Anker.** Sie ist eindeutig (6 Zeichen, Ziffern oder Großbuchstaben, kein I/O), trennt zuverlässig „vorgestellt" von „nur erwähnt" und gibt uns einen maschinenlesbaren Weg zum Ticker. Das ist genau die Definition von „vorgestellt", die wir wollen — neutral, unabhängig davon ob bullish, bearish oder Short besprochen.

---

## 3. Datenquellen

**A) Episoden (primär): RSS-Feed.**
Feed-URL nicht raten — über die iTunes-Lookup-API auflösen:
```
GET https://itunes.apple.com/lookup?id=1542785062&entity=podcast
→ Feld "feedUrl"
```
Den Feed mit `feedparser` parsen. Pro Episode brauchen wir: `title`, `published_parsed` (UTC), und den Beschreibungstext (`summary` + ggf. `content[0].value` zusammenführen — die WKN steckt in einem davon).

**Caveat Archiv-Tiefe:** Der Feed liefert evtl. nicht alle 1.000+ Folgen. Strategie: nimm, was der Feed hergibt (das ist viel), bau die Pipeline **idempotent/inkrementell** (Dedup über `guid`), sodass ältere Folgen später nachgezogen werden können. Optionaler Phase-X-Ausbau für Vollarchiv: Podcast Index API (podcastindex.org, free Key) oder die OAWS-Transkript-DB auf oaws.de.

**B) WKN → Ticker: OpenFIGI** (free, API-Key empfohlen für höheres Rate-Limit).
```
POST https://api.openfigi.com/v3/mapping
Header: X-OPENFIGI-APIKEY: <key>, Content-Type: application/json
Body:   [{"idType":"ID_WERTPAPIER","idValue":"923255"}]
→ data[].ticker, .name, .exchCode, .securityType2, .marketSector
```
`ID_WERTPAPIER` = WKN. Wir nutzen OpenFIGI als **Backstop**; primäre Quelle der Wahrheit ist die Override-Map + yfinance-Validierung (§6).

**C) Kurse: `yfinance`** (Python). Historischer Close nahe Vorstellungstag + letzter Close. Währung pro Ticker mitspeichern (`fast_info.currency`).

---

## 4. Tech-Stack (gesetzt)

- **Pipeline:** Python 3.11+, `feedparser`, `requests`, `yfinance`, `pandas`, `python-dateutil`, `zoneinfo`.
- **Frontend:** statisch, kein Build-Zwang für v1. `index.html` + `app.js` + `styles.css`. Tailwind via CDN, sortierbare Tabelle entweder handgerollt (JS-Sort, keine Dependency) oder `grid.js`. Daten kommen aus generierter `data.json`.
- **Deploy:** statischer Host (Cloudflare Pages / beliebig). Tägliches Refresh via GitHub Actions Cron *oder* Cron auf eigenem Host (`make update`).
- **Design:** funktional spezifiziert (§7). Optik (dunkles Daten-Dashboard, Charcoal/Cyan o. ä.) → Entscheidung liegt beim Auftraggeber, nicht vorab festlegen. Für Umsetzung das `frontend-design`-Skill nutzen.

### Repo-Struktur
```
oaws-tracker/
  pipeline/
    fetch_episodes.py     # RSS → data/episodes.json  (date, title, text, guid)
    extract_stocks.py     # episodes → data/mentions.json (wkn, name, date, ep_title, guid)
    resolve_tickers.py    # wkn → data/wkn_map.json  (Override → yfinance-Check → OpenFIGI)
    fetch_prices.py       # mentions + map → Kurse (entry + now)
    build.py              # Orchestrierung: Deltas + Aggregate → public/data.json + meta.json
  data/
    wkn_map.json          # committet: WKN → {name, yahoo, isin?, currency, exchange, source}
    cache/                # rohe RSS-/Kurs-Caches (gitignored)
  public/
    index.html
    app.js
    styles.css
    data.json             # generiert
  requirements.txt
  Makefile                # setup / episodes / extract / resolve / prices / build / update / serve
  README.md
```

---

## 5. Phasen

**Phase 0 – Setup.** Repo, venv, `requirements.txt`, `Makefile`, `.gitignore` (`data/cache/`, `.env`). `.env`: `OPENFIGI_API_KEY`. README mit „make update".

**Phase 1 – Episoden holen.** `fetch_episodes.py`: Feed-URL via iTunes-Lookup auflösen, mit `feedparser` parsen, pro Episode `{guid, title, text, published_utc}` nach `data/episodes.json`. `text` = Beschreibung + Content gemerged, **HTML-Entities dekodiert** (`html.unescape`, z. B. `&#x27;` → `'`).

**Phase 2 – Aktien extrahieren.** `extract_stocks.py`: pro Episode alle `(name, wkn)`-Paare via Regex (§8), `published_utc` → Berliner Datum. Output `data/mentions.json` als Liste von `{wkn, name, presented_date, ep_title, guid}`. Eine Zeile pro Vorstellung (Mehrfachnennungen einer Aktie = mehrere Zeilen).

**Phase 3 – Ticker auflösen.** `resolve_tickers.py`: für jede **unique WKN** einen Yahoo-Ticker bestimmen (§6), cachen in `data/wkn_map.json`. Nur fehlende WKNs neu auflösen (Cache respektieren).

**Phase 4 – Kurse holen.** `fetch_prices.py`: pro Mention Entry-Close (§8 Datums-Logik) + letzter Close + Währung. Fehlende/delistete Ticker → `null`, Flag `resolved=false`.

**Phase 5 – Berechnung.** `build.py`: `abs_delta`, `pct_delta` (Heimatwährung, §8), `days_held`. Aggregate berechnen (§7). Schreibe `public/data.json` (Zeilen) + `meta.json` (`as_of`, Episodenzahl, Anzahl ungelöster WKNs). 

**Phase 6 – Frontend.** Tabelle + Kennzahlen-Cards aus `data.json` (§7).

**Phase 7 – Update/Deploy.** `make update` = Phasen 1→5 inkrementell + Frontend liest neu. Cron täglich. Deploy statisch.

---

## 6. Ticker-Resolution (selbstkorrigierend, dreistufig)

Reihenfolge pro WKN, Ergebnis in `wkn_map.json` cachen mit `source`:

1. **Override-Map** (manuell gepflegt im selben File): Hat ein Mensch den Ticker gesetzt → gewinnt immer. Hier landen Korrekturen.
2. **Wissens-Resolution + yfinance-Validierung:** Aus `name` den wahrscheinlichen Yahoo-Ticker ableiten (du kennst die meisten: Daktronics→`DAKT`, Markel→`MKL`, Amazon→`AMZN`, IMAX→`IMAX`, Sandoz→`SDZ.SW`, D'Ieteren→`DIE.BR`, OHB→`OHB.DE`, Academy→`ASO`, Dick's→`DKS`). **Validierung ist die Ground Truth:** `yfinance.Ticker(sym).history(period="5d")` liefert Daten → Symbol gültig, Währung übernehmen. Leer → verwerfen, Stufe 3.
3. **OpenFIGI `ID_WERTPAPIER`** als Backstop: WKN posten, aus `data[]` Kandidaten mit `marketSector=="Equity"` und `securityType2 in ("Common Stock","Depositary Receipt")` wählen, Ticker zu Yahoo-Symbol mappen, wieder per yfinance validieren.

Was nirgends auflösbar ist → in Tabelle als „n/a" listen, aber aus Rankings ausschließen. `meta.json` zählt ungelöste WKNs, damit man die Override-Map gezielt nachpflegen kann.

> Warum nicht nur OpenFIGI? Exchange-Codes → Yahoo-Suffix ist fehleranfällig. Bei ~paar hundert Aktien ist die yfinance-validierte Map robuster und stabil.

---

## 7. Tabellen- & Frontend-Spezifikation

**Tabellen-Spalten:** Firma · WKN · Ticker · Vorstellungsdatum · Folgen-Titel · Kurs (Vorstellung) · Kurs (heute) · Währung · Δ abs. · **Δ %** · Tage gehalten.

**Sortierbar** nach jeder Spalte; Default: Δ % absteigend. **Filter:** Textsuche (Firma), Jahr, „nur auflösbare", optional Währung. Δ %: grün positiv / rot negativ.

**Kennzahlen-Cards (oben):**
- Größter Gewinner / größter Verlierer (Firma + Δ %).
- Anteil Gewinner vs. Verlierer (%).
- Median- und Durchschnitts-Δ % aller auflösbaren Vorstellungen.
- „Gleichgewichtetes Depot": Durchschnitts-Δ % über alle Vorstellungen (= hätte man jede vorgestellte Aktie zur Vorstellung gekauft).
- Anzahl Folgen / Anzahl Vorstellungen / Stand (`as_of`).

**Zwei Sichten (Toggle):**
- **Alle Vorstellungen** (eine Zeile je Folge — Mehrfachnennungen sichtbar).
- **Erstnennung** (dedupliziert je WKN auf das früheste Datum).

**Optionaler Stretch:** Spalte „Δ % vs. Markt" — Benchmark-Return über denselben Zeitraum (`^GSPC` für US, `URTH`/MSCI World global) gegenrechnen, um zu zeigen ob die Vorstellung den Markt geschlagen hätte.

---

## 8. Kernlogik — Code für die kniffligen Stellen

### 8.1 WKN-Extraktion (streng auf `WKN:` ankern)
```python
import re, html

WKN_RE = re.compile(r"([A-Za-zÄÖÜäöü0-9&.\-'’ ]{2,60}?)\s*\(WKN:\s*([A-HJ-NP-Z0-9]{6})\)")

def extract(text: str):
    text = html.unescape(text or "")
    out = []
    for m in WKN_RE.finditer(text):
        name = m.group(1).strip(" -–·,").strip()
        wkn  = m.group(2).upper()
        out.append({"name": name, "wkn": wkn})
    return out
```
Nur Treffer **mit** `(WKN: …)` zählen — niemals beliebige 6-Zeichen-Tokens. Das filtert den News-Ticker automatisch raus.

### 8.2 pubDate → Berliner Handelsdatum
```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def berlin_date(published_parsed):
    dt_utc = datetime(*published_parsed[:6], tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo("Europe/Berlin")).date()
```
Folge erscheint ~03:00 Berlin; das **Datum in Berlin** ist die „Vorstellung".

### 8.3 Entry-Kurs = letzter Close ≤ Vorstellungstag (konfigurierbar)
```python
import yfinance as yf
import pandas as pd

def entry_close(sym, presented_date):
    # Fenster, um Wochenenden/Feiertage abzufangen
    start = (pd.Timestamp(presented_date) - pd.Timedelta(days=10)).date()
    end   = (pd.Timestamp(presented_date) + pd.Timedelta(days=2)).date()
    h = yf.Ticker(sym).history(start=start, end=end, auto_adjust=False)
    if h.empty:
        return None
    h.index = h.index.date
    le = [d for d in h.index if d <= presented_date]
    if not le:
        return None
    return float(h.loc[max(le), "Close"])
```
**Entscheidung:** letzter Close **am oder vor** dem Vorstellungstag = „Kurs am Tag der Vorstellung" (das Kursumfeld, über das gesprochen wurde). Als einzelne Funktion halten, damit die Regel per Flag umschaltbar ist (z. B. auf „erster Close ≥ Tag" = realistischer Listener-Fill).

### 8.4 Aktueller Kurs + %-Berechnung
```python
def latest_close(sym):
    h = yf.Ticker(sym).history(period="5d", auto_adjust=False)
    return float(h["Close"].iloc[-1]) if not h.empty else None

def pct(entry, now):
    return None if not entry else round((now / entry - 1) * 100, 2)
```
**%-Vergleich in der Heimatwährung des Tickers** — beide Punkte sind dieselbe Notierung/Währung, also kein FX-Umrechnen nötig und korrekt.

### 8.5 OpenFIGI (Backstop)
```python
import requests

def figi_lookup(wkn, api_key=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    r = requests.post("https://api.openfigi.com/v3/mapping",
                      json=[{"idType": "ID_WERTPAPIER", "idValue": wkn}],
                      headers=headers, timeout=20)
    r.raise_for_status()
    data = (r.json()[0] or {}).get("data", [])
    eq = [d for d in data if d.get("marketSector") == "Equity"
          and d.get("securityType2") in ("Common Stock", "Depositary Receipt")]
    return (eq or data or [None])[0]
```

---

## 9. Golden-Fixtures (Extraktion sofort testen)

Lege `tests/fixtures.py` an. Für jeden String muss `extract()` exakt das `(name, wkn)`-Paar liefern. Diese stammen aus echten Folgenbeschreibungen:

```python
CASES = [
    ("… Bread Financial (WKN: 934251) steckt hinter den Kreditkarten …",
        [("Bread Financial", "934251")]),
    ("IMAX (WKN: 896801) hat eins der smartesten Geschäftsmodelle …",
        [("IMAX", "896801")]),
    ("Großaktionär D&#x27;Ieteren (WKN: A1H5AN) hält 50% …",
        [("D'Ieteren", "A1H5AN")]),           # HTML-Entity muss dekodiert sein
    ("Sandoz (WKN: A3ETYB) kopiert die größten Blockbuster … "
     "Markel (WKN: 885036) will das nächste Berkshire sein.",
        [("Sandoz", "A3ETYB"), ("Markel", "885036")]),  # zwei pro Folge
    ("Daktronics (WKN: 923255) ist da ein Hidden Champion.",
        [("Daktronics", "923255")]),
    ("Amazon (WKN: 906866) profitiert doppelt von Anthropic.",
        [("Amazon", "906866")]),
    ("OHB (WKN: 593612) gründet mit Helsing ein Joint Venture …",
        [("OHB", "593612")]),
    ("Dick's Sporting Goods (WKN: 662541) ist die beste Sport-Aktie … "
     "Academy Sports + Outdoors (WKN: A2QDZ9) will das ändern.",
        [("Dick's Sporting Goods", "662541"),
         ("Academy Sports + Outdoors", "A2QDZ9")]),
]
# Negativ: Ein News-Ticker-Satz ohne (WKN: …) darf 0 Treffer liefern.
NEGATIVE = "Rheinmetall bekommt Milliarden-Auftrag. Okta springt dank KI."
```

---

## 10. Definition „vorgestellt" (explizit)

Eine Aktie gilt als vorgestellt, **genau dann wenn** in der Episodenbeschreibung ein `Firmenname (WKN: XXXXXX)` vorkommt. News-Ticker-Erwähnungen ohne WKN zählen **nicht**. Sentiment (bullish/bearish/Short) spielt keine Rolle. Transkript-Mining ist **nicht** Teil des MVP (würde „erwähnt" statt „vorgestellt" liefern) — optionaler Ausbau für Sentiment.

---

## 11. Edge Cases (alle behandeln)

- Mehrere WKNs in einer Folge → mehrere Zeilen.
- Gleiche Aktie mehrfach vorgestellt → mehrere Zeilen (Erstnennungs-Sicht dedupliziert).
- Vorstellungstag = Wochenende/Feiertag → §8.3 fällt auf letzten Handelstag zurück.
- Nicht-USD/EUR-Währungen → %-Logik bleibt korrekt (keine Umrechnung).
- WKN für Warrant/Index/ETF (kommt im News-Teil selten vor) → über `securityType2`-Filter / leere yfinance-Daten aussortieren.
- Delisted / Merger / Umbenennung → `null`, Flag `resolved=false`, aus Ranking raus, in Tabelle als „n/a".
- HTML-Entities in Beschreibung (`&#x27;`, `&amp;`) → `html.unescape` vor Regex.
- yfinance liefert für `start==end` nichts → immer ein Mehrtage-Fenster ziehen.

---

## 12. Acceptance Criteria (Definition of Done)

1. `make update` läuft fehlerfrei durch und erzeugt `public/data.json` + `public/meta.json`.
2. Alle Fixtures in §9 grün (inkl. Negativfall = 0 Treffer und Entity-Dekodierung).
3. `data.json` enthält ≥ 1 Zeile pro auflösbarer Vorstellung mit Entry-Kurs, Heute-Kurs, Δ %, Tagen.
4. Frontend: sortierbare Tabelle (Default Δ % absteigend), funktionierende Filter, beide Sichten (Alle/Erstnennung), Kennzahlen-Cards stimmen mit den Daten überein.
5. Größter Gewinner/Verlierer in den Cards = tatsächliche Extremwerte der auflösbaren Zeilen.
6. `meta.json` zeigt `as_of`, Episodenzahl und Zahl ungelöster WKNs.
7. Re-Run ist inkrementell (keine Doppel-Zeilen über `guid`), Ticker-Cache wird respektiert.
8. Footer-Disclaimer „keine Anlageberatung, Daten ohne Gewähr" vorhanden.

---

## 13. Risiken & Grenzen

- **Archiv-Tiefe** hängt am RSS-Feed; Vollarchiv ggf. erst über Podcast Index API / oaws.de (Phase X).
- **Survivorship/Merger:** Delistete Picks verzerren Aggregate nach oben, wenn man sie stillschweigend wegrechnet — daher zählen und ausweisen, nicht verstecken.
- **Ticker-Resolution** ist nie 100 % automatisch; Override-Map ist Absicht, nicht Workaround.
- **yfinance** ist inoffiziell und kann sich ändern → Kurs-Layer hinter einer Funktion kapseln, damit Quelle austauschbar ist.
- **Kein Anlageberatungs-Produkt.**
