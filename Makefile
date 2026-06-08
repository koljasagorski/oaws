PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup episodes extract resolve prices build update serve test clean

setup:
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

episodes:
	$(PY) pipeline/fetch_episodes.py

extract:
	$(PY) pipeline/extract_stocks.py

resolve:
	$(PY) pipeline/resolve_tickers.py

prices:
	$(PY) pipeline/fetch_prices.py

build:
	$(PY) pipeline/build.py

# Inkrementeller Voll-Lauf (Phasen 1->5), Frontend liest data.json neu
update: episodes extract resolve prices build

serve:
	$(PY) -m http.server 8000 --directory public

test:
	$(PY) -m pytest -q tests/

clean:
	rm -rf data/cache/* public/data.json public/meta.json
