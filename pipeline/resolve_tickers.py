"""Phase 3: WKN -> Yahoo-Ticker aufloesen (dreistufig, selbstkorrigierend, §6).

1. Override-Map (manuell gepflegt, source="override") gewinnt immer.
2. OpenFIGI ID_WERTPAPIER -> Equity-Kandidaten -> Yahoo-Symbol-Kandidaten,
   per yfinance validiert (erste Notierung mit echten Kursdaten gewinnt).
   Ground Truth ist die yfinance-Validierung, nicht der Exchange-Code.
3. Nicht aufloesbar -> resolved=false (in Tabelle "n/a", aus Rankings raus).

Cache: data/wkn_map.json. Nur fehlende WKNs werden neu aufgeloest.
Optional begrenzen auf juengste Vorstellungen via --since-days N (Slice-first).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta

import requests

try:
    from .common import MENTIONS, WKN_MAP, load_json, save_json
except ImportError:  # pragma: no cover
    from common import MENTIONS, WKN_MAP, load_json, save_json

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_KEY = os.environ.get("OPENFIGI_API_KEY")

# OpenFIGI exchCode -> Yahoo-Suffix (haeufige Boersen). "" = US (kein Suffix).
EXCH_SUFFIX = {
    "GR": ".DE", "GF": ".F", "GS": ".SG", "GB": ".BE", "GM": ".MU",
    "GH": ".HM", "GD": ".DU", "GW": ".SG", "GT": ".SG", "GY": ".DE",
    "SW": ".SW", "SE": ".SW", "VX": ".SW",
    "LN": ".L",
    "FP": ".PA",
    "NA": ".AS",
    "BB": ".BR",
    "IM": ".MI",
    "SM": ".MC", "SQ": ".MC",
    "PL": ".LS",
    "ID": ".IR",
    "DC": ".CO",
    "SS": ".ST",
    "NO": ".OL",
    "FH": ".HE",
    "AV": ".VI",
    "PW": ".WA",
    "CT": ".TO", "CN": ".TO", "CV": ".V",
    "JT": ".T", "JP": ".T",
    "HK": ".HK",
    "AT": ".AT",
    "SP": ".SI",
    "AU": ".AX",
}

SUFFIX_CCY = {
    "": "USD", ".DE": "EUR", ".F": "EUR", ".SG": "EUR", ".BE": "EUR",
    ".MU": "EUR", ".HM": "EUR", ".DU": "EUR", ".SW": "CHF", ".L": "GBp",
    ".PA": "EUR", ".AS": "EUR", ".BR": "EUR", ".MI": "EUR", ".MC": "EUR",
    ".LS": "EUR", ".IR": "EUR", ".CO": "DKK", ".ST": "SEK", ".OL": "NOK",
    ".HE": "EUR", ".VI": "EUR", ".WA": "PLN", ".TO": "CAD", ".V": "CAD",
    ".T": "JPY", ".HK": "HKD", ".AT": "EUR", ".SI": "SGD", ".AX": "AUD",
}

# Versuchs-Reihenfolge der Suffixe: US zuerst, dann grosse EU-Boersen, dann Rest.
SUFFIX_PRIORITY = {"": 0, ".DE": 1, ".SW": 1, ".L": 1, ".PA": 1, ".AS": 1,
                   ".BR": 1, ".MI": 1, ".MC": 1, ".CO": 1, ".ST": 1, ".OL": 1,
                   ".HE": 1, ".VI": 1, ".IR": 1, ".LS": 1, ".F": 2}


def _is_us(exch: str) -> bool:
    return exch == "US" or (len(exch) == 2 and exch.startswith("U"))


def figi_candidates(wkns, batch=None):
    """Liste von WKN-Batches -> dict wkn -> Liste von OpenFIGI data-Eintraegen."""
    headers = {"Content-Type": "application/json"}
    if OPENFIGI_KEY:
        headers["X-OPENFIGI-APIKEY"] = OPENFIGI_KEY
    batch = batch or (100 if OPENFIGI_KEY else 10)
    out: dict[str, list] = {}
    wkns = list(wkns)
    for i in range(0, len(wkns), batch):
        chunk = wkns[i:i + batch]
        body = [{"idType": "ID_WERTPAPIER", "idValue": w} for w in chunk]
        for attempt in range(5):
            r = requests.post(OPENFIGI_URL, json=body, headers=headers, timeout=30)
            if r.status_code == 429:
                time.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError("OpenFIGI: zu viele 429er")
        for w, res in zip(chunk, r.json()):
            out[w] = (res or {}).get("data", []) or []
        print(f"  OpenFIGI {i + len(chunk)}/{len(wkns)}", file=sys.stderr)
        time.sleep(0.3 if OPENFIGI_KEY else 2.6)  # Rate-Limit (25 req/min keyless)
    return out


def yahoo_guesses(data):
    """OpenFIGI-Equity-Kandidaten -> priorisierte, eindeutige Yahoo-Symbole."""
    eq = [d for d in data
          if d.get("marketSector") == "Equity"
          and d.get("securityType2") in ("Common Stock", "Depositary Receipt")]
    eq = eq or data  # Fallback: irgendwas ist besser als nichts
    guesses = []
    seen = set()
    for d in eq:
        tk = (d.get("ticker") or "").strip().upper().replace("/", "-")
        exch = (d.get("exchCode") or "").strip().upper()
        if not tk:
            continue
        if _is_us(exch):
            suffix = ""
        elif exch in EXCH_SUFFIX:
            suffix = EXCH_SUFFIX[exch]
        else:
            continue  # unbekannte Boerse -> nicht raten
        sym = tk + suffix
        if sym in seen:
            continue
        seen.add(sym)
        guesses.append((SUFFIX_PRIORITY.get(suffix, 3), sym, suffix))
    guesses.sort(key=lambda x: x[0])
    return [(sym, suffix) for _, sym, suffix in guesses]


YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def yahoo_search(name):
    """Fallback: Yahoo-Namenssuche -> Liste von EQUITY-Yahoo-Symbolen (in Trefferreihenfolge)."""
    if not name:
        return []
    for attempt in range(4):
        try:
            r = requests.get(YAHOO_SEARCH,
                             params={"q": name, "quotesCount": 8, "newsCount": 0},
                             headers=_UA, timeout=15)
            if r.status_code == 429:  # Yahoo-Rate-Limit -> Backoff
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            out, seen = [], set()
            for q in r.json().get("quotes", []):
                if q.get("quoteType") != "EQUITY":
                    continue
                sym = (q.get("symbol") or "").strip()
                if sym and sym not in seen:
                    seen.add(sym)
                    out.append(sym)
            return out
        except Exception:
            time.sleep(2)
    return []


def validate(sym):
    """yfinance-Validierung. Liefert dict(currency, liquidity) oder None.

    liquidity = mittleres Handelsvolumen*Kurs (~Umsatz in Lokalwaehrung) als
    Proxy fuer die Primaernotierung – so gewinnt die Hauptboerse statt eines
    illiquiden US-OTC-Graumarkt-Listings.
    """
    import yfinance as yf
    try:
        t = yf.Ticker(sym)
        h = t.history(period="6mo", auto_adjust=False)
        if h is None or h.empty:
            return None
        ccy = None
        try:
            ccy = t.fast_info.get("currency")
        except Exception:
            ccy = None
        vol = (h["Volume"].fillna(0) * h["Close"].fillna(0)).mean()
        return {"currency": ccy, "liquidity": float(vol or 0.0)}
    except Exception:
        return None


MAX_GUESSES = 8  # pro WKN max. so viele Symbole validieren (Kostenbremse)


def _pick(syms_suffixes, source):
    cands = []
    for sym, suffix in syms_suffixes[:MAX_GUESSES]:
        v = validate(sym)
        if v is not None:
            cands.append((v["liquidity"], sym, suffix, v["currency"]))
    if not cands:
        return None
    cands.sort(reverse=True)  # hoechste Liquiditaet = Primaernotierung
    _, sym, suffix, ccy = cands[0]
    return {"yahoo": sym, "currency": ccy or SUFFIX_CCY.get(suffix),
            "exchange": suffix or "US", "source": source, "resolved": True}


def resolve_one(wkn, data, name=None):
    # Stufe 2: OpenFIGI(WKN) -> Yahoo-Symbol-Kandidaten
    res = _pick(yahoo_guesses(data), "openfigi")
    if res:
        return res
    # Stufe 4 (Fallback): Yahoo-Namenssuche (kanonischer FIGI-Name bevorzugt)
    figi_name = next((d.get("name") for d in data if d.get("name")), None)
    query = figi_name or name
    if query:
        syms = yahoo_search(figi_name or name)
        ss = [(s, ("." + s.split(".", 1)[1]) if "." in s else "") for s in syms]
        res = _pick(ss, "yahoo_search")
        if res:
            return res
    return {"yahoo": None, "currency": None, "exchange": None,
            "source": "unresolved", "resolved": False, "figi_name": figi_name}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=None,
                    help="Nur WKNs aus Vorstellungen der letzten N Tage aufloesen (Slice-first)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Auch fruehere resolved=false erneut versuchen")
    ap.add_argument("--limit", type=int, default=None, help="Max. neue WKNs (Debug)")
    args = ap.parse_args()

    mentions = load_json(MENTIONS, default=[]) or []
    if args.since_days is not None:
        cutoff = (date.today() - timedelta(days=args.since_days)).isoformat()
        mentions = [m for m in mentions if m["presented_date"] >= cutoff]

    cache = load_json(WKN_MAP, default={}) or {}
    # Committeten Override-Seed einmischen (gewinnt immer, §6) – auch auf frischer VM
    from common import OVERRIDES  # lokal, vermeidet Import-Reihenfolge-Probleme
    for w, ov in (load_json(OVERRIDES, default={}) or {}).items():
        entry = dict(ov)
        entry["source"] = "override"
        entry.setdefault("resolved", True)
        cache[w] = entry
    wkn_names = {}  # fuer Yahoo-Namenssuche-Fallback
    for m in mentions:
        wkn_names.setdefault(m["wkn"], m.get("name"))
    want = []
    seen = set()
    for m in mentions:
        w = m["wkn"]
        if w in seen:
            continue
        seen.add(w)
        entry = cache.get(w)
        if entry is None:
            want.append(w)
        elif entry.get("source") == "override":
            continue
        elif entry.get("resolved") is False and args.retry_failed:
            want.append(w)
    if args.limit:
        want = want[:args.limit]

    print(f"resolve_tickers: {len(seen)} WKNs im Scope, {len(want)} neu aufzuloesen "
          f"(OpenFIGI key: {'ja' if OPENFIGI_KEY else 'nein'})")
    if not want:
        save_json(WKN_MAP, cache)
        return

    figi = figi_candidates(want)
    for i, w in enumerate(want, 1):
        data = figi.get(w, [])
        # resolve_one deckt auch leeres OpenFIGI-Ergebnis ab (Yahoo-Namenssuche-Fallback)
        res = resolve_one(w, data, name=wkn_names.get(w))
        nm = next((d.get("name") for d in data if d.get("name")), None)
        if nm:
            res["name"] = nm.title() if nm.isupper() else nm
        cache[w] = res
        if i % 10 == 0 or i == len(want):
            print(f"  resolved {i}/{len(want)}", file=sys.stderr)
            save_json(WKN_MAP, cache)  # inkrementell sichern

    save_json(WKN_MAP, cache)
    ok = sum(1 for w in seen if cache.get(w, {}).get("resolved") is not False
             and cache.get(w, {}).get("yahoo"))
    print(f"resolve_tickers: {ok}/{len(seen)} im Scope aufgeloest -> {WKN_MAP}")


if __name__ == "__main__":
    main()
