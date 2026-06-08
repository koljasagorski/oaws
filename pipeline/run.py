"""Orchestrierter Pipeline-Lauf (Cron + manueller Refresh aus dem Admin).

Liest data/config.json (entry_mode, scope_days), fuehrt die Phasen 1-5 aus,
schreibt fortlaufend data/run.log und am Ende data/last_run.json. Ein Lockfile
verhindert parallele Laeufe. OPENFIGI_API_KEY wird aus .env in die Umgebung
gelegt, damit die Resolution das hoehere Rate-Limit nutzt.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

try:
    from .common import (DATA, LAST_RUN, ROOT, RUN_LOG, load_config, read_env,
                         save_json)
except ImportError:  # pragma: no cover
    from common import (DATA, LAST_RUN, ROOT, RUN_LOG, load_config, read_env,
                        save_json)

LOCK = DATA / ".run.lock"
PY = sys.executable


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(fh, msg):
    line = f"[{_now()}] {msg}"
    print(line)
    fh.write(line + "\n")
    fh.flush()


def _step(fh, name, argv, env):
    _log(fh, f"START {name}: {' '.join(argv)}")
    p = subprocess.run(argv, cwd=str(ROOT), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for ln in (p.stdout or "").splitlines():
        fh.write("    " + ln + "\n")
    fh.flush()
    _log(fh, f"END {name} rc={p.returncode}")
    if p.returncode != 0:
        raise RuntimeError(f"{name} fehlgeschlagen (rc={p.returncode})")
    return (p.stdout or "").strip().splitlines()[-1:] or [""]


def main() -> int:
    if LOCK.exists():
        print("Lauf bereits aktiv (Lockfile vorhanden) – abgebrochen.", file=sys.stderr)
        return 2
    LOCK.write_text(_now())
    started = _now()
    ok = False
    summary = ""
    cfg = load_config()
    env = dict(os.environ)
    env.update({k: v for k, v in read_env().items() if v})
    scope = cfg.get("scope_days")
    mode = cfg.get("entry_mode", "on_or_before")
    pdir = "pipeline"
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("w", encoding="utf-8") as fh:
            _log(fh, f"RUN start | scope_days={scope} entry_mode={mode} "
                     f"openfigi_key={'yes' if env.get('OPENFIGI_API_KEY') else 'no'}")
            _step(fh, "episodes", [PY, f"{pdir}/fetch_episodes.py"], env)
            _step(fh, "extract", [PY, f"{pdir}/extract_stocks.py"], env)
            rargs = [PY, f"{pdir}/resolve_tickers.py"]
            pargs = [PY, f"{pdir}/fetch_prices.py", "--mode", mode]
            if scope is not None:
                rargs += ["--since-days", str(scope)]
                pargs += ["--since-days", str(scope)]
            _step(fh, "resolve", rargs, env)
            _step(fh, "prices", pargs, env)
            last = _step(fh, "build", [PY, f"{pdir}/build.py"], env)
            summary = last[0] if last else ""
            _log(fh, "RUN done OK")
            ok = True
    except Exception as e:  # noqa: BLE001
        summary = f"FEHLER: {e}"
        try:
            with RUN_LOG.open("a", encoding="utf-8") as fh:
                _log(fh, summary)
        except OSError:
            pass
    finally:
        LOCK.unlink(missing_ok=True)
    save_json(LAST_RUN, {
        "started": started, "finished": _now(), "ok": ok,
        "summary": summary, "scope_days": scope, "entry_mode": mode,
    })
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
