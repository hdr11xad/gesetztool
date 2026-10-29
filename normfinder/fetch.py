"""Download des Inhaltsverzeichnisses und der XML-Archive von gesetze-im-internet.de.

Lädt nur Geänderte (ETag / Last-Modified), hält ein Rate-Limit ein, setzt
Timeouts und wiederholt fehlgeschlagene Anfragen mit wachsender Wartezeit.
Ein Archiv ersetzt die zwischengespeicherte Fassung erst, wenn es sich als
gültiges ZIP öffnen lässt.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

BASE = "https://www.gesetze-im-internet.de"
TOC_URL = BASE + "/gii-toc.xml"
USER_AGENT = "Normfinder des FSR Jura Halle (+https://fsr-jura-halle.de/normfinder/)"


@dataclass
class TocItem:
    slug: str
    title: str


def parse_toc(data: bytes) -> list[TocItem]:
    root = ET.fromstring(data)
    items = []
    seen = set()
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        m = re.search(r"gesetze-im-internet\.de/([^/]+)/xml\.zip$", link)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        items.append(TocItem(m.group(1), (it.findtext("title") or "").strip()))
    return items


class Fetcher:
    def __init__(self, cache: Path, interval: float = 0.25, timeout: float = 60,
                 retries: int = 4):
        self.cache = cache
        self.zips = cache / "zips"
        self.zips.mkdir(parents=True, exist_ok=True)
        self.meta_path = cache / "meta.json"
        self.meta = json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {}
        self.interval = interval
        self.timeout = timeout
        self.retries = retries
        self._last = 0.0
        self.stats = {"unchanged": 0, "updated": 0, "failed": 0, "removed": 0}

    def save_meta(self):
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=0, sort_keys=True))
        os.replace(tmp, self.meta_path)

    def _wait(self):
        delta = time.monotonic() - self._last
        if delta < self.interval:
            time.sleep(self.interval - delta)
        self._last = time.monotonic()

    def get(self, url: str, key: str) -> bytes | None:
        """Bedingter GET. Gibt neue Daten zurück, None bei 304 (unverändert)."""
        prev = self.meta.get(key, {})
        headers = {"User-Agent": USER_AGENT}
        if prev.get("etag"):
            headers["If-None-Match"] = prev["etag"]
        if prev.get("last_modified"):
            headers["If-Modified-Since"] = prev["last_modified"]
        err: Exception | None = None
        for attempt in range(self.retries):
            self._wait()
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = r.read()
                    self.meta[key] = {
                        "etag": r.headers.get("ETag"),
                        "last_modified": r.headers.get("Last-Modified"),
                        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    return data
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    return None
                if e.code == 404:
                    raise
                err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                err = e
            wait = 2 ** (attempt + 1)
            log.warning("%s: Versuch %d fehlgeschlagen (%s), warte %ds", url, attempt + 1, err, wait)
            time.sleep(wait)
        raise RuntimeError(f"{url}: {err}")

    def fetch_toc(self) -> list[TocItem]:
        path = self.cache / "gii-toc.xml"
        data = self.get(TOC_URL, "__toc__")
        if data is not None:
            items = parse_toc(data)  # erst prüfen, dann speichern
            path.write_bytes(data)
            self.save_meta()
            return items
        return parse_toc(path.read_bytes())

    def fetch_law(self, slug: str) -> bool:
        """True, wenn eine gültige Fassung im Cache liegt."""
        target = self.zips / f"{slug}.zip"
        if not target.exists():
            self.meta.pop(slug, None)  # erzwingt vollständigen Download
        try:
            data = self.get(f"{BASE}/{slug}/xml.zip", slug)
        except Exception as e:  # noqa: BLE001 – ein Gesetz darf den Lauf nicht abbrechen
            log.error("%s: Download fehlgeschlagen: %s", slug, e)
            self.stats["failed"] += 1
            return target.exists()
        if data is None:
            self.stats["unchanged"] += 1
            return True
        tmp = target.with_suffix(".part")
        tmp.write_bytes(data)
        try:
            with zipfile.ZipFile(tmp) as z:
                if not any(n.lower().endswith(".xml") for n in z.namelist()):
                    raise zipfile.BadZipFile("keine XML-Datei im Archiv")
        except zipfile.BadZipFile as e:
            log.error("%s: ungültiges Archiv (%s), behalte alte Fassung", slug, e)
            tmp.unlink()
            self.meta.pop(slug, None)
            self.stats["failed"] += 1
            return target.exists()
        os.replace(tmp, target)
        self.stats["updated"] += 1
        return True

    def run(self, only: list[str] | None = None) -> list[TocItem]:
        items = self.fetch_toc()
        wanted = [i for i in items if not only or i.slug in only]
        log.info("Inhaltsverzeichnis: %d Einträge", len(items))
        ok = []
        for n, item in enumerate(wanted, 1):
            if self.fetch_law(item.slug):
                ok.append(item)
            if n % 200 == 0:
                self.save_meta()
                log.info("%d/%d geprüft (%s)", n, len(wanted), self.stats)
        if not only:  # Gesetze, die nicht mehr im Verzeichnis stehen, entfernen
            keep = {i.slug for i in items}
            for p in self.zips.glob("*.zip"):
                if p.stem not in keep:
                    p.unlink()
                    self.meta.pop(p.stem, None)
                    self.stats["removed"] += 1
        self.save_meta()
        log.info("Download fertig: %s", self.stats)
        return ok
