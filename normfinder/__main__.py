"""Kommandozeile des Normfinders.

  python3 -m normfinder update     Laden, erzeugen, prüfen, umschalten, melden (nächtlich)
  python3 -m normfinder fetch      nur Archive laden
  python3 -m normfinder build      nur erzeugen (aus dem Cache)
  python3 -m normfinder rollback   auf den vorherigen Stand zurückschalten
  python3 -m normfinder status     aktuellen Stand anzeigen
  python3 -m normfinder serve      lokaler Testserver (wie Caddy: /normfinder/bgb/573)

Pfade und Einstellungen kommen aus Umgebungsvariablen (siehe deploy/normfinder.env).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import build as B
from .fetch import Fetcher

log = logging.getLogger("normfinder")


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def setup_logging(root: Path | None, verbose: bool):
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if root is not None:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(logs / time.strftime("update-%Y-%m-%d.log"), encoding="utf-8"))
        for p in logs.glob("update-*.log"):  # 30 Tage aufheben
            if time.time() - p.stat().st_mtime > 30 * 86400:
                p.unlink()
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")


def notify(ok: bool, msg: str):
    """Meldung an Uptime Kuma (Push-Monitor) und optional per Mail über sendmail."""
    push = os.environ.get("NORMFINDER_PUSH_URL", "").split("?")[0]  # Kuma zeigt die URL mit ?status=up… an
    if push:
        q = urllib.parse.urlencode({"status": "up" if ok else "down", "msg": msg[:200], "ping": ""})
        try:
            urllib.request.urlopen(f"{push}?{q}", timeout=20).read()
        except Exception as e:  # noqa: BLE001
            log.warning("Uptime-Kuma-Meldung fehlgeschlagen: %s", e)
    mail = os.environ.get("NORMFINDER_MAIL")
    if mail and not ok:
        import shutil
        import subprocess
        sm = shutil.which("sendmail") or "/usr/sbin/sendmail"
        if os.path.exists(sm):
            body = f"To: {mail}\nSubject: [Normfinder] Update fehlgeschlagen\nContent-Type: text/plain; charset=utf-8\n\n{msg}\n"
            try:
                subprocess.run([sm, "-t"], input=body.encode(), timeout=60, check=True)
            except Exception as e:  # noqa: BLE001
                log.warning("Mailversand fehlgeschlagen: %s", e)


def cmd_update(a):
    root, cache = a.root, a.cache
    lock = open(root / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error("Ein anderer Lauf ist noch aktiv – Abbruch.")
        return 2
    try:
        f = Fetcher(cache, interval=a.interval)
        f.run()
        if f.stats["failed"] > 200:
            raise B.BuildError(f"{f.stats['failed']} Downloads fehlgeschlagen")
        cur = root / "current" / "build.json"
        same_code = cur.exists() and json.loads(cur.read_text()).get("code") == B.code_version()
        if f.stats["updated"] == 0 and f.stats["removed"] == 0 and same_code and not a.force:
            log.info("Keine Änderungen – der aktuelle Stand bleibt.")
            notify(True, "keine Änderungen")
            return 0
        stats = B.build(cache, root, base=a.base, workers=a.workers)
        msg = f"{stats['laws']} Gesetze, {stats['norms']} Normen, {len(stats['errors'])} Fehler, {f.stats['updated']} aktualisiert"
        notify(True, msg)
        if stats["errors"]:
            log.warning("Fehler bei einzelnen Gesetzen: %s", "; ".join(stats["errors"][:20]))
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("Update fehlgeschlagen – der bisherige Stand bleibt online")
        notify(False, f"Update fehlgeschlagen: {e}")
        return 1


def cmd_fetch(a):
    only = a.only.split(",") if a.only else None
    Fetcher(a.cache, interval=a.interval).run(only)
    return 0


def cmd_build(a):
    only = a.only.split(",") if a.only else None
    stats = B.build(a.cache, a.root, base=a.base, only=only, workers=a.workers, check=not a.no_check)
    print(json.dumps({k: v for k, v in stats.items() if k != "errors"}, ensure_ascii=False))
    return 0


def cmd_rollback(a):
    print("Umgeschaltet auf", B.rollback(a.root))
    return 0


def cmd_status(a):
    cur = a.root / "current"
    if not cur.exists():
        print("Noch kein Stand vorhanden.")
        return 1
    stats = json.loads((cur / "build.json").read_text())
    print(f"Aktiv: {cur.resolve().name}")
    print(json.dumps(stats, ensure_ascii=False, indent=1)[:3000])
    rel = sorted(p.name for p in (a.root / "releases").iterdir())
    print("Vorhandene Stände:", ", ".join(rel))
    return 0


def cmd_serve(a):
    from .devserver import serve
    serve(a.root / "current", a.port, a.base)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="normfinder", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=env_path("NORMFINDER_ROOT", "/srv/normfinder"),
                   help="Datenverzeichnis (releases/, current, logs/)")
    p.add_argument("--cache", type=Path, default=None, help="Download-Cache (Standard: <root>/cache)")
    p.add_argument("--base", default=os.environ.get("NORMFINDER_BASE", "/normfinder/"))
    p.add_argument("--workers", type=int, default=int(os.environ.get("NORMFINDER_WORKERS", "0")) or None)
    p.add_argument("--interval", type=float, default=float(os.environ.get("NORMFINDER_INTERVAL", "0.3")),
                   help="Mindestabstand zwischen zwei Downloads in Sekunden")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("update")
    s.add_argument("--force", action="store_true", help="auch ohne Änderungen neu erzeugen")
    s.set_defaults(fn=cmd_update)
    s = sub.add_parser("fetch")
    s.add_argument("--only", help="kommagetrennte Kennungen, z. B. bgb,gg")
    s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("build")
    s.add_argument("--only", help="nur diese Gesetze (zum Testen)")
    s.add_argument("--no-check", action="store_true")
    s.set_defaults(fn=cmd_build)
    sub.add_parser("rollback").set_defaults(fn=cmd_rollback)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    a.cache = a.cache or a.root / "cache"
    a.root.mkdir(parents=True, exist_ok=True)
    setup_logging(a.root if a.cmd in ("update", "build") else None, a.verbose)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
