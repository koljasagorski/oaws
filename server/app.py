"""OAWS Tracker – Web-App: oeffentliches Dashboard + passwortgeschuetztes Admin.

- `/`            statisches Dashboard (public/)
- `/admin`       Admin-UI (Single-Passwort-Login, Session-Cookie)
- `/api/*`       JSON-APIs (Login-pflichtig ausser /api/login)

Secrets in .env: ADMIN_PASSWORD_HASH (scrypt), SESSION_SECRET, OPENFIGI_API_KEY.
Pipeline-Laeufe werden als Subprozess (pipeline/run.py) gestartet.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from common import (  # noqa: E402
    LAST_RUN, PUBLIC, RUN_LOG, WKN_MAP, DATA, load_config, load_json,
    read_env, save_config, save_json, write_env,
)

SERVER_DIR = Path(__file__).resolve().parent
LOCK = DATA / ".run.lock"


# ---- Passwort-Hashing (stdlib scrypt) ---------------------------------------
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---- App --------------------------------------------------------------------
def get_session_secret() -> str:
    env = read_env()
    sec = env.get("SESSION_SECRET")
    if not sec:
        sec = secrets.token_hex(32)
        write_env({"SESSION_SECRET": sec})
    return sec


app = FastAPI(title="OAWS Tracker")
app.add_middleware(SessionMiddleware, secret_key=get_session_secret(),
                   same_site="lax", https_only=False, max_age=60 * 60 * 24 * 14)


@app.middleware("http")
async def revalidate_assets(request: Request, call_next):
    """CSS/JS/HTML/JSON immer revalidieren (kein veraltetes Cache-Asset im Browser)."""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p == "/admin" or p.endswith((".css", ".js", ".html", ".json")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def require_auth(request: Request):
    if not request.session.get("auth"):
        raise HTTPException(status_code=401, detail="nicht angemeldet")


def run_active() -> bool:
    return LOCK.exists()


# ---- Auth -------------------------------------------------------------------
@app.post("/api/login")
async def login(request: Request):
    form = await request.form()
    pw = (form.get("password") or "").strip()
    env = read_env()
    stored = env.get("ADMIN_PASSWORD_HASH", "")
    if not stored:
        raise HTTPException(500, "Kein Admin-Passwort gesetzt (ADMIN_PASSWORD_HASH fehlt)")
    if not verify_password(pw, stored):
        raise HTTPException(401, "Falsches Passwort")
    request.session["auth"] = True
    return {"ok": True}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---- Status / Daten ---------------------------------------------------------
@app.get("/api/status")
async def status(request: Request):
    require_auth(request)
    meta = load_json(PUBLIC / "meta.json", default={}) or {}
    last = load_json(LAST_RUN, default={}) or {}
    cfg = load_config()
    env = read_env()
    wkn = load_json(WKN_MAP, default={}) or {}
    unresolved = [{"wkn": k, "figi_name": v.get("figi_name") or v.get("name")}
                  for k, v in wkn.items() if v.get("resolved") is False]
    return {
        "meta": meta,
        "last_run": last,
        "running": run_active(),
        "config": cfg,
        "has_openfigi_key": bool(env.get("OPENFIGI_API_KEY")),
        "unresolved": unresolved[:500],
        "unresolved_count": len(unresolved),
    }


@app.get("/api/run-log")
async def run_log(request: Request):
    require_auth(request)
    if not RUN_LOG.exists():
        return PlainTextResponse("(noch kein Lauf)")
    txt = RUN_LOG.read_text(encoding="utf-8", errors="replace")
    return PlainTextResponse(txt[-20000:])


# ---- Aktionen ---------------------------------------------------------------
@app.post("/api/refresh")
async def refresh(request: Request):
    require_auth(request)
    if run_active():
        return JSONResponse({"ok": False, "msg": "Lauf bereits aktiv"}, status_code=409)
    env = dict(os.environ)
    env.update({k: v for k, v in read_env().items() if v})
    subprocess.Popen([sys.executable, "pipeline/run.py"], cwd=str(ROOT), env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "msg": "Lauf gestartet"}


@app.post("/api/keys")
async def set_keys(request: Request):
    require_auth(request)
    data = await request.json()
    updates = {}
    if "openfigi_api_key" in data:
        updates["OPENFIGI_API_KEY"] = (data["openfigi_api_key"] or "").strip()
    if updates:
        write_env(updates)
    return {"ok": True}


@app.post("/api/password")
async def set_password(request: Request):
    require_auth(request)
    data = await request.json()
    new = (data.get("new_password") or "").strip()
    if len(new) < 8:
        raise HTTPException(400, "Passwort zu kurz (min. 8 Zeichen)")
    write_env({"ADMIN_PASSWORD_HASH": hash_password(new)})
    return {"ok": True}


@app.post("/api/override")
async def set_override(request: Request):
    """WKN-Override setzen/loeschen (gewinnt immer, §6)."""
    require_auth(request)
    data = await request.json()
    wkn = (data.get("wkn") or "").strip().upper()
    if not wkn:
        raise HTTPException(400, "WKN fehlt")
    cache = load_json(WKN_MAP, default={}) or {}
    if data.get("delete"):
        cache.pop(wkn, None)
    else:
        yahoo = (data.get("yahoo") or "").strip()
        if not yahoo:
            raise HTTPException(400, "Yahoo-Ticker fehlt")
        cache[wkn] = {
            "name": (data.get("name") or "").strip() or cache.get(wkn, {}).get("name"),
            "yahoo": yahoo,
            "currency": (data.get("currency") or "").strip() or None,
            "exchange": (data.get("exchange") or "").strip() or None,
            "source": "override",
            "resolved": True,
        }
    save_json(WKN_MAP, cache)
    return {"ok": True}


@app.post("/api/settings")
async def set_settings(request: Request):
    require_auth(request)
    data = await request.json()
    cfg = load_config()
    if "entry_mode" in data and data["entry_mode"] in ("on_or_before", "on_or_after"):
        cfg["entry_mode"] = data["entry_mode"]
    if "scope_days" in data:
        v = data["scope_days"]
        cfg["scope_days"] = None if v in (None, "", "null") else int(v)
    schedule_changed = False
    if "schedule" in data and data["schedule"]:
        hhmm = str(data["schedule"]).strip()
        parts = hhmm.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            cfg["schedule"] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            schedule_changed = True
    save_config(cfg)
    msg = "gespeichert"
    if schedule_changed:
        # systemd-Timer via sudo-Helfer aktualisieren (best effort)
        try:
            subprocess.run(["sudo", "-n", "/usr/local/bin/oaws-set-schedule",
                            cfg["schedule"]], timeout=15, check=False)
        except Exception:
            msg = "gespeichert (Timer-Update nicht moeglich – Helfer/sudo fehlt)"
    return {"ok": True, "config": cfg, "msg": msg}


# ---- Seiten -----------------------------------------------------------------
@app.get("/admin")
async def admin_page():
    return FileResponse(SERVER_DIR / "admin.html")


@app.get("/admin.js")
async def admin_js():
    return FileResponse(SERVER_DIR / "admin.js", media_type="application/javascript")


@app.post("/api/github-webhook")
async def github_webhook(request: Request):
    """GitHub-Push -> Auto-Deploy (HMAC-verifiziert). Caddy routet HTTPS hierher."""
    secret = read_env().get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook nicht konfiguriert")
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "ungueltige Signatur")
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"ok": True, "pong": True}
    if event != "push":
        return {"ok": True, "ignored": event}
    import json as _json
    try:
        ref = _json.loads(body).get("ref", "")
    except Exception:
        ref = ""
    if ref and not (ref.endswith("/master") or ref.endswith("/main")):
        return {"ok": True, "ignored_ref": ref}
    # Detached deployen (ueberlebt den Service-Restart am Ende des Skripts)
    subprocess.Popen(["bash", "deploy/auto-deploy.sh"], cwd=str(ROOT),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True, "deploying": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "running": run_active()}


# Statisches Dashboard zuletzt mounten (faengt alle uebrigen Pfade)
app.mount("/", StaticFiles(directory=str(PUBLIC), html=True), name="public")
