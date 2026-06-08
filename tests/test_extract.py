import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from extract_stocks import extract  # noqa: E402
from fixtures import CASES, NEGATIVE  # noqa: E402


def _pairs(text):
    return [(h["name"], h["wkn"]) for h in extract(text)]


def test_golden_cases():
    for text, expected in CASES:
        assert _pairs(text) == expected, f"Mismatch fuer: {text!r}"


def test_negative_no_match():
    assert extract(NEGATIVE) == []


def test_entity_decoding():
    # D&#x27;Ieteren -> D'Ieteren, Apostroph als ASCII
    res = extract("D&#x27;Ieteren (WKN: A1H5AN) ist spannend")
    assert res == [{"name": "D'Ieteren", "wkn": "A1H5AN"}]
