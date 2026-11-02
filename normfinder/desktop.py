"""Datenverwaltung der Desktop-Version (Flatpak), ohne Oberfläche und damit testbar.

Erster Start:
  1. Kerngesetze laden und erzeugen → nach etwa einer Minute benutzbar,
  2. das restliche Bundesrecht im Hintergrund laden und erzeugen.
Später: höchstens einmal am Tag nach Änderungen sehen (nur Geändertes laden).

Laden und Erzeugen laufen als eigene Prozesse (python3 -m normfinder …);
die Fortschrittsmeldungen werden aus deren Log-Ausgabe gelesen.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
CHECK_EVERY = 20 * 3600   # Sekunden zwischen zwei Prüfungen auf neue Fassungen


@dataclass
class Progress:
    phase: str            # core | full | update
    text: str
    fraction: float | None = None   # 0..1 oder None (unbestimmt)


PATTERNS = [
    (re.compile(r"Inhaltsverzeichnis: (\d+) Einträge"), lambda m: ("Inhaltsverzeichnis geladen", None)),
    (re.compile(r"(\d+)/(\d+) geprüft"),
     lambda m: (f"Gesetze laden: {m.group(1)} von {m.group(2)}", 0.85 * int(m.group(1)) / int(m.group(2)))),
    (re.compile(r"Download fertig"), lambda m: ("Download fertig", 0.85)),
    (re.compile(r"Lese (\d+) Archive"), lambda m: (f"{m.group(1)} Gesetze werden gelesen …", 0.87)),
    (re.compile(r"(\d+)/(\d+) Gesetze erzeugt"),
     lambda m: (f"Seiten erzeugen: {m.group(1)} von {m.group(2)}", 0.87 + 0.11 * int(m.group(1)) / int(m.group(2)))),
    (re.compile(r"Suchindex"), lambda m: ("Suchindex wird erstellt …", 0.98)),
    (re.compile(r"Umgeschaltet auf"), lambda m: ("Fertig", 1.0)),
    (re.compile(r"Keine Änderungen"), lambda m: ("Keine neuen Fassungen", 1.0)),
]


def parse_line(line: str) -> tuple[str, float | None] | None:
    for rx, fn in PATTERNS:
        m = rx.search(line)
        if m:
            return fn(m)
    return None


class DataManager:
    def __init__(self, root: Path, python: str = sys.executable, interval: float = 0.15):
        self.root = Path(root)
        self.cache = self.root / "cache"
        self.python = python
        self.interval = interval
        self.proc: subprocess.Popen | None = None
        self.stopped = False
        self.root.mkdir(parents=True, exist_ok=True)

    # -- Zustand --------------------------------------------------------

    @property
    def site(self) -> Path:
        return self.root / "current"

    def ready(self) -> bool:
        return (self.site / "index.html").exists()

    def stats(self) -> dict:
        try:
            return json.loads((self.site / "build.json").read_text())
        except (OSError, ValueError):
            return {}

    def complete(self) -> bool:
        """Vollständiges Bundesrecht vorhanden (nicht nur die Kerngesetze)?"""
        s = self.stats()
        return bool(s) and not s.get("partial")

    def due(self) -> bool:
        stamp = self.root / "last-check"
        try:
            return time.time() - stamp.stat().st_mtime > CHECK_EVERY
        except OSError:
            return True

    def plan(self) -> list[str]:
        """Welche Schritte stehen an? core · full · update"""
        if not self.ready():
            return ["core", "full"]
        if not self.complete():
            return ["full"]
        return ["update"] if self.due() else []

    # -- Ausführen ------------------------------------------------------

    def core_slugs(self) -> list[str]:
        core = json.loads((PKG_ROOT / "data" / "core.json").read_text(encoding="utf-8"))
        return [s for g in core["gruppen"] for s in g["gesetze"]]

    def commands(self, step: str) -> list[list[str]]:
        base = [self.python, "-m", "normfinder", "--root", str(self.root), "--cache", str(self.cache),
                "--interval", str(self.interval), "--keep", "1"]
        if step == "core":
            only = ",".join(self.core_slugs())
            return [base + ["fetch", "--only", only], base + ["build", "--only", only, "--no-check"]]
        if step in ("full", "update"):
            return [base + ["update"]]
        raise ValueError(step)

    def run(self, step: str, report=None) -> bool:
        """Führt einen Schritt aus; report(Progress) erhält die Fortschrittsmeldungen."""
        env = dict(os.environ, PYTHONPATH=str(PKG_ROOT), PYTHONUNBUFFERED="1")
        env.pop("NORMFINDER_PUSH_URL", None)
        for cmd in self.commands(step):
            if self.stopped:
                return False
            proc = self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                                env=env, cwd=str(PKG_ROOT), start_new_session=True)
            tail: list[str] = []
            for line in proc.stdout:
                tail = (tail + [line.rstrip()])[-20:]
                hit = parse_line(line)
                if hit and report:
                    report(Progress(step, *hit))
            if proc.wait() != 0:
                if report:
                    report(Progress(step, "Fehler: " + (tail[-1] if tail else "unbekannt"), None))
                return False
        self.proc = None
        if step in ("full", "update"):
            (self.root / "last-check").touch()
        return True

    def stop(self):
        """Beim Beenden der App: laufenden Schritt samt Unterprozessen abbrechen."""
        self.stopped = True
        proc = self.proc
        if proc and proc.poll() is None:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
                proc.kill()
