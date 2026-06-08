"""Phase 4: Kurse holen (Entry-Close + letzter Close + Waehrung).

Entry-Kurs = letzter Close <= Vorstellungstag (§8.3), per Flag umschaltbar auf
"erster Close >= Tag" (realistischer Listener-Fill). Aktueller Kurs = letzter
verfuegbarer Close. Fehlt/delisted -> null. Kurs-Layer hinter Funktionen
gekapselt, damit yfinance austauschbar bleibt.

Output: data/prices.json -> {yahoo: {entry_by_date: {date: close}, latest, currency}}
Pro (yahoo, presented_date) wird der Entry-Close gecacht.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import pandas as pd

try:
    from .common import MENTIONS, PRICES, WKN_MAP, load_json, save_json
except ImportError:  # pragma: no cover
    from common import MENTIONS, PRICES, WKN_MAP, load_json, save_json

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _history(sym, start=None, end=None, period=None):
    import yfinance as yf
    return yf.Ticker(sym).history(start=start, end=end, period=period,
                                  auto_adjust=False)


def entry_close(sym, presented_date: str, mode: str = "on_or_before"):
    """Entry-Close fuer einen Vorstellungstag.

    mode="on_or_before": letzter Close <= Tag (Default, das Kursumfeld).
    mode="on_or_after":  erster Close >= Tag (Listener-Fill).
    """
    pd_date = pd.Timestamp(presented_date).date()
    start = (pd.Timestamp(pd_date) - pd.Timedelta(days=12)).date()
    end = (pd.Timestamp(pd_date) + pd.Timedelta(days=12)).date()
    h = _history(sym, start=start, end=end)
    if h is None or h.empty:
        return None
    h.index = [d.date() for d in h.index]
    if mode == "on_or_after":
        ge = [d for d in h.index if d >= pd_date]
        if not ge:
            return None
        return float(h.loc[min(ge), "Close"])
    le = [d for d in h.index if d <= pd_date]
    if not le:
        return None
    return float(h.loc[max(le), "Close"])


def latest_close(sym):
    h = _history(sym, period="5d")
    if h is None or h.empty:
        return None
    return float(h["Close"].iloc[-1])


def latest_closes_batch(symbols):
    """Letzte Closes vieler Symbole in EINEM yfinance-Download (schnell/schonend).

    Faellt pro fehlendem Symbol nicht zurueck – Luecken werden danach einzeln
    nachgezogen. Gibt dict sym -> close|None.
    """
    import yfinance as yf
    out = {}
    symbols = list(symbols)
    if not symbols:
        return out
    try:
        df = yf.download(symbols, period="5d", auto_adjust=False,
                         group_by="ticker", progress=False, threads=True)
    except Exception:
        return out
    for sym in symbols:
        try:
            if len(symbols) == 1:
                col = df["Close"]
            else:
                col = df[sym]["Close"]
            col = col.dropna()
            out[sym] = float(col.iloc[-1]) if not col.empty else None
        except Exception:
            out[sym] = None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["on_or_before", "on_or_after"],
                    default="on_or_before")
    ap.add_argument("--since-days", type=int, default=None)
    args = ap.parse_args()

    mentions = load_json(MENTIONS, default=[]) or []
    if args.since_days is not None:
        cutoff = (date.today() - timedelta(days=args.since_days)).isoformat()
        mentions = [m for m in mentions if m["presented_date"] >= cutoff]
    wkn_map = load_json(WKN_MAP, default={}) or {}
    cache = load_json(PRICES, default={}) or {}

    # Welche Yahoo-Symbole brauchen wir, fuer welche Entry-Tage, welche Waehrung?
    need: dict[str, set] = {}
    sym_ccy: dict[str, str] = {}
    for m in mentions:
        entry = wkn_map.get(m["wkn"]) or {}
        sym = entry.get("yahoo")
        if not sym:
            continue
        need.setdefault(sym, set()).add(m["presented_date"])
        if entry.get("currency"):
            sym_ccy[sym] = entry["currency"]

    total = len(need)
    # 1) latest-Close fuer ALLE Symbole in einem Batch (schnell), Luecken einzeln
    print(f"  batching latest close fuer {total} Symbole …")
    batch = latest_closes_batch(need.keys())

    # 2) entry-Closes nur fuer noch nicht gecachte (sym, date)-Paare
    for i, (sym, dates) in enumerate(sorted(need.items()), 1):
        rec = cache.get(sym) or {"entry_by_date": {}, "latest": None, "currency": None}
        rec.setdefault("entry_by_date", {})
        rec["currency"] = sym_ccy.get(sym, rec.get("currency"))
        rec["latest"] = batch.get(sym) if batch.get(sym) is not None else latest_close(sym)
        for d in sorted(dates):
            if d not in rec["entry_by_date"]:
                rec["entry_by_date"][d] = entry_close(sym, d, mode=args.mode)
        cache[sym] = rec
        if i % 25 == 0 or i == total:
            print(f"  prices {i}/{total} ({sym})")
            save_json(PRICES, cache)

    save_json(PRICES, cache)
    print(f"fetch_prices: {total} Symbole, mode={args.mode} -> {PRICES}")


if __name__ == "__main__":
    main()
