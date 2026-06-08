"""Phase 2: Aktien aus Episodenbeschreibungen extrahieren.

Definition "vorgestellt" (§10): exakt dann, wenn `Firmenname (WKN: XXXXXX)`
in der Beschreibung vorkommt. News-Ticker ohne WKN zaehlen nicht.

Output: data/mentions.json -> Liste von {wkn, name, presented_date, ep_title, guid}.
Eine Zeile pro Vorstellung (Mehrfachnennungen => mehrere Zeilen).
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

try:  # erlaubt Aufruf als Modul (Tests) und als Skript
    from .common import EPISODES, MENTIONS, load_json, save_json
except ImportError:  # pragma: no cover - Skript-Aufruf
    from common import EPISODES, MENTIONS, load_json, save_json

# WKN: 6 Zeichen, Ziffern oder Grossbuchstaben, ohne I/O (Verwechslungsschutz).
# Name: 2-60 Zeichen vor "(WKN:" – erlaubt Umlaute, &, ., -, Apostrophvarianten, Leerzeichen.
WKN_RE = re.compile(r"([A-Za-zÄÖÜäöü0-9&.+\-'’ ]{2,60}?)\s*\(WKN:\s*([A-HJ-NP-Z0-9]{6})\)")


# Satzgrenzen, an denen Fliesstext vor dem Firmennamen abgeschnitten wird.
_SENT_SPLIT = re.compile(r"[.!?:;…•]\s+|\s[–—]\s+")


def _name_like(tok: str) -> bool:
    """Token gehoert plausibel zum Firmennamen (Eigenname/Connector)."""
    if not tok:
        return False
    c = tok[0]
    return c.isupper() or c.isdigit() or tok in ("+", "&")


def _clean_name(name: str) -> str:
    """Firmennamen aus dem Regex-Treffer herausschaelen.

    Die Beschreibungen sind Prosa ("… Das ist die Story von IMAX (WKN: …)").
    Zweistufig: (1) an der letzten Satzgrenze abschneiden, (2) im Rest-Clause
    von rechts den zusammenhaengenden Eigennamen-Lauf nehmen (Firmennamen
    beginnen gross; das rechteste Token wird immer behalten, auch
    klein geschriebene Marken wie "comdirect"). Kanonische Namen liefert
    spaeter die Ticker-Resolution – das hier ist Anker/Hinweis.
    """
    name = name.replace("’", "'").strip(" -–·,").strip()
    if not name:
        return ""
    clause = _SENT_SPLIT.split(name)[-1].strip() or name
    tokens = clause.split()
    if not tokens:
        return ""
    kept = [tokens[-1]]
    for tok in reversed(tokens[:-1]):
        if _name_like(tok):
            kept.insert(0, tok)
        else:
            break
    return " ".join(kept)


def extract(text: str):
    """Liefert Liste von {"name", "wkn"} – nur Treffer mit (WKN: …)."""
    text = html.unescape(text or "")
    out = []
    for m in WKN_RE.finditer(text):
        name = m.group(1).strip(" -–·,").strip()
        # Apostrophvarianten normalisieren auf ASCII '
        name = name.replace("’", "'")
        name = _clean_name(name)
        wkn = m.group(2).upper()
        out.append({"name": name, "wkn": wkn})
    return out


def berlin_date(published_iso: str) -> str:
    """ISO-UTC-String -> Berliner Handelsdatum (YYYY-MM-DD)."""
    dt_utc = datetime.fromisoformat(published_iso)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()


def main() -> None:
    episodes = load_json(EPISODES, default=[]) or []
    mentions = []
    for ep in episodes:
        presented = berlin_date(ep["published_utc"])
        seen = set()  # WKN je Episode entdoppeln (summary+content duplizieren oft)
        for hit in extract(ep.get("text", "")):
            if hit["wkn"] in seen:
                continue
            seen.add(hit["wkn"])
            mentions.append({
                "wkn": hit["wkn"],
                "name": hit["name"],
                "presented_date": presented,
                "ep_title": ep.get("title", ""),
                "guid": ep.get("guid", ""),
            })
    save_json(MENTIONS, mentions)
    uniq = len({m["wkn"] for m in mentions})
    print(f"extract_stocks: {len(mentions)} Vorstellungen, {uniq} unique WKNs "
          f"aus {len(episodes)} Episoden -> {MENTIONS}")


if __name__ == "__main__":
    main()
