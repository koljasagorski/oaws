"""Gemeinsame Helfer: Pfade + JSON-IO. Bewusst dependency-frei."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
PUBLIC = ROOT / "public"

# Datendateien
EPISODES = DATA / "episodes.json"
MENTIONS = DATA / "mentions.json"
WKN_MAP = DATA / "wkn_map.json"
OVERRIDES = DATA / "overrides.json"  # committeter Seed (gewinnt immer, §6)
PRICES = DATA / "prices.json"
OUT_DATA = PUBLIC / "data.json"
OUT_META = PUBLIC / "meta.json"

PODCAST_ID = "1542785062"  # OAWS (Apple Podcasts)

CONFIG = DATA / "config.json"
LAST_RUN = DATA / "last_run.json"
RUN_LOG = DATA / "run.log"
ENV_FILE = ROOT / ".env"

DEFAULT_CONFIG = {
    "entry_mode": "on_or_before",  # oder "on_or_after"
    "scope_days": None,             # None = Vollarchiv, sonst nur letzte N Tage
    "schedule": "08:00",            # taegliche Cron-Zeit (Europe/Berlin)
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(CONFIG, default={}) or {})
    return cfg


def save_config(cfg: dict) -> None:
    save_json(CONFIG, cfg)


def read_env() -> dict:
    """Minimaler .env-Parser (KEY=VALUE pro Zeile)."""
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def write_env(updates: dict) -> None:
    """Setzt/ueberschreibt Keys in .env, erhaelt Reihenfolge/Kommentare grob."""
    env = read_env()
    env.update({k: v for k, v in updates.items() if v is not None})
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


def load_json(path: Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
