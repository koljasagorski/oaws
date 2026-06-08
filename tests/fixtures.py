"""Golden-Fixtures aus echten Folgenbeschreibungen (§9 der Anleitung).

extract() MUSS fuer jeden String exakt das (name, wkn)-Paar liefern.
"""

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
