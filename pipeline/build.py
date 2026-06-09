"""Phase 5: Orchestrierung – Mentions + Map + Kurse -> public/data.json + meta.json.

Berechnet pro Vorstellung abs_delta, pct_delta (in Heimatwaehrung, §8.4 – kein
FX noetig) und days_held. Aggregate fuer die Kennzahlen-Cards (§7). Inkrementell
ueber guid (Dedup). Nicht aufloesbare -> resolved=false, aus Rankings raus.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

try:
    from .common import (EPISODES, MENTIONS, OUT_DATA, OUT_META, PRICES,
                         WKN_MAP, load_json, save_json)
except ImportError:  # pragma: no cover
    from common import (EPISODES, MENTIONS, OUT_DATA, OUT_META, PRICES,
                        WKN_MAP, load_json, save_json)


def pct(entry, now):
    if not entry or now is None:
        return None
    return round((now / entry - 1) * 100, 2)


def days_between(d_iso: str) -> int:
    d = datetime.fromisoformat(d_iso).date()
    return (datetime.now(timezone.utc).date() - d).days


def build_rows(mentions, wkn_map, prices):
    rows = []
    for m in mentions:
        wkn = m["wkn"]
        meta = wkn_map.get(wkn) or {}
        sym = meta.get("yahoo")
        # Display-Name: kanonischer Name aus Resolver bevorzugen, sonst Extraktion
        name = meta.get("name") or m["name"]
        prec = prices.get(sym) if sym else None
        entry = (prec or {}).get("entry_by_date", {}).get(m["presented_date"]) if prec else None
        now = (prec or {}).get("latest") if prec else None
        now_date = (prec or {}).get("latest_date") if prec else None
        ccy = (prec or {}).get("currency") or meta.get("currency")
        resolved = bool(sym) and meta.get("resolved") is not False \
            and entry is not None and now is not None
        p = pct(entry, now) if resolved else None
        rows.append({
            "wkn": wkn,
            "name": name,
            "ticker": sym,
            "presented_date": m["presented_date"],
            "ep_title": m["ep_title"],
            "guid": m["guid"],
            "entry": round(entry, 4) if entry is not None else None,
            "now": round(now, 4) if now is not None else None,
            "now_date": now_date,
            "currency": ccy,
            "abs_delta": round(now - entry, 4) if (resolved) else None,
            "pct_delta": p,
            "days_held": days_between(m["presented_date"]),
            "resolved": resolved,
        })
    return rows


def last_added(rows):
    """Zuletzt vorgestellte Aktie: hoechstes Vorstellungsdatum (neuester Pick)."""
    if not rows:
        return None
    r = max(rows, key=lambda x: x["presented_date"])
    return {
        "name": r["name"],
        "wkn": r["wkn"],
        "ticker": r["ticker"],
        "presented_date": r["presented_date"],
        "ep_title": r["ep_title"],
        "pct_delta": r["pct_delta"],
        "currency": r["currency"],
        "resolved": r["resolved"],
    }


def first_mention_view(rows):
    """Erstnennung: je WKN nur das frueheste Vorstellungsdatum."""
    best = {}
    for r in rows:
        k = r["wkn"]
        if k not in best or r["presented_date"] < best[k]["presented_date"]:
            best[k] = r
    return list(best.values())


def aggregates(rows):
    res = [r for r in rows if r["resolved"] and r["pct_delta"] is not None]
    pcts = [r["pct_delta"] for r in res]
    winners = [r for r in res if r["pct_delta"] > 0]
    losers = [r for r in res if r["pct_delta"] < 0]
    agg = {
        "count_rows": len(rows),
        "count_resolved": len(res),
        "winners": len(winners),
        "losers": len(losers),
        "winner_share": round(100 * len(winners) / len(res), 1) if res else None,
        "loser_share": round(100 * len(losers) / len(res), 1) if res else None,
        "avg_pct": round(statistics.mean(pcts), 2) if pcts else None,
        "median_pct": round(statistics.median(pcts), 2) if pcts else None,
        "equal_weight_pct": round(statistics.mean(pcts), 2) if pcts else None,
        "best": None,
        "worst": None,
    }
    if res:
        b = max(res, key=lambda r: r["pct_delta"])
        w = min(res, key=lambda r: r["pct_delta"])
        agg["best"] = {"name": b["name"], "pct": b["pct_delta"], "wkn": b["wkn"]}
        agg["worst"] = {"name": w["name"], "pct": w["pct_delta"], "wkn": w["wkn"]}
    return agg


def main() -> None:
    mentions = load_json(MENTIONS, default=[]) or []
    wkn_map = load_json(WKN_MAP, default={}) or {}
    prices = load_json(PRICES, default={}) or {}

    # Dedup ueber (guid, wkn) – idempotenter Re-Run, keine Doppelzeilen
    seen = set()
    uniq = []
    for m in mentions:
        key = (m["guid"], m["wkn"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)

    rows = build_rows(uniq, wkn_map, prices)
    rows.sort(key=lambda r: (r["pct_delta"] is None, -(r["pct_delta"] or 0)))
    first = first_mention_view(rows)

    n_episodes_total = len(load_json(EPISODES, default=[]) or [])
    n_episodes_with_picks = len({m["guid"] for m in uniq})
    unresolved_wkns = sorted({r["wkn"] for r in rows if not r["resolved"]})
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")

    save_json(OUT_DATA, {
        "as_of": as_of,
        "all": rows,
        "first": first,
        "last_added": last_added(rows),
        "aggregates_all": aggregates(rows),
        "aggregates_first": aggregates(first),
    })
    save_json(OUT_META, {
        "as_of": as_of,
        "episodes": n_episodes_total,
        "episodes_with_picks": n_episodes_with_picks,
        "presentations": len(rows),
        "unique_wkns": len({r["wkn"] for r in rows}),
        "unresolved_count": len(unresolved_wkns),
        "unresolved_wkns": unresolved_wkns,
    })
    print(f"build: {len(rows)} Zeilen ({aggregates(rows)['count_resolved']} aufgeloest), "
          f"{n_episodes_total} Folgen ({n_episodes_with_picks} mit Picks), "
          f"{len(unresolved_wkns)} ungeloeste WKNs -> {OUT_DATA}")


if __name__ == "__main__":
    main()
