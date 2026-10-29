"""Erzeugt einen vollständigen Stand („Release“) des Normfinders und schaltet ihn um.

Ablauf:
  1. alle Archive lesen (parallel) → Gesetzesregister,
  2. Seiten, Gesetzesdaten, Bilder und Suchindex in releases/<zeit>.tmp schreiben,
  3. prüfen (Mindestumfang, Kerngesetze, Stichproben, Vergleich mit dem Vorstand),
  4. atomar umschalten: Symlink „current“ zeigt auf den neuen Stand,
  5. alte Stände bis auf die letzten drei löschen.
Schlägt etwas fehl, bleibt der bisherige Stand online.

Unveränderte Dateien werden aus dem vorherigen Stand hart verlinkt statt neu
geschrieben; so belegt jeder Stand nur Platz für das, was sich geändert hat.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import multiprocessing as mp
import os
import re
import shutil
import time
from pathlib import Path

from . import gii, laws, render, search_index
from .refs import Linker

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RESERVED_IDS = {"index", "img"}
EXAMPLES = ["573 bgb", "§ 573 Abs. 2 Nr. 1 BGB", "art 1 gg", "433 II 1 bgb", "§§ 823 ff. BGB",
            "263 stgb", "§ 42 Abs. 1 VwGO", "grundgesetz 20", "kündigung vermieter"]


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- Dateien schreiben

class Writer:
    """Schreibt Dateien; identische Dateien des Vorstands werden hart verlinkt."""

    def __init__(self, root: Path, prev: Path | None):
        self.root = root
        self.prev = prev
        self.linked = 0
        self.written = 0

    def write(self, rel: str, data: bytes | str):
        if isinstance(data, str):
            data = data.encode("utf-8")
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.prev is not None:
            old = self.prev / rel
            try:
                if old.stat().st_size == len(data) and old.read_bytes() == data:
                    os.link(old, path)
                    self.linked += 1
                    return
            except OSError:
                pass
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o644)
        self.written += 1


# ---------------------------------------------------------------- Arbeitsprozesse

_G: dict = {}   # in den Kindprozessen geerbte Daten (fork)


def _summarize(zpath: str):
    try:
        law = gii.load(zpath)
        return laws.summarize(law), None
    except Exception as e:  # noqa: BLE001
        return None, f"{Path(zpath).stem}: {type(e).__name__}: {e}"


def _render_law(slug: str):
    reg, site, out, prev, zips, fts = _G["reg"], _G["site"], _G["out"], _G["prev"], _G["zips"], _G["fts"]
    t0 = time.time()
    try:
        law = gii.load(zips / f"{slug}.zip", slug)
        info = reg.get(slug)
        w = Writer(out, prev)
        d = info.url
        linker = Linker(reg, site.norm_url)
        img_base = f"{site.base}{d}/img/"
        for name, data in law.images.items():
            w.write(f"{d}/img/{name}", data)
        real = {n.id for n in law.norms}
        for k, n in enumerate(law.norms):
            if n.id in RESERVED_IDS:
                n.id += "-n"
        for k, n in enumerate(law.norms):
            html = site.norm_page(law, k, linker, img_base)
            w.write(f"{d}/{n.id}.html", html)
            for c in n.covers:
                if c != n.id and c not in real and c not in RESERVED_IDS:
                    w.write(f"{d}/{c}.html", html)
        w.write(f"{d}/index.html", site.toc_page(law))
        w.write(f"{d}/index.json", site.law_index_json(law))
        fts.write_law(slug, search_index.law_postings(law))
        core = None
        if info.core:
            core = [[info.url, n.id, n.label, n.title] for n in law.norms if not n.gone]
        return {"slug": slug, "norms": len(law.norms), "written": w.written, "linked": w.linked,
                "secs": round(time.time() - t0, 2), "core": core}
    except Exception as e:  # noqa: BLE001
        log.exception("%s: Fehler beim Erzeugen", slug)
        return {"slug": slug, "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------- Build

def code_version() -> str:
    """Prüfsumme über Code, Oberfläche und Datenlisten – ändert sie sich, wird neu erzeugt."""
    h = hashlib.sha1()
    for base in (ROOT / "normfinder", WEB / "assets", ROOT / "data"):
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                h.update(p.relative_to(ROOT).as_posix().encode())
                h.update(p.read_bytes())
    return h.hexdigest()[:12]


def asset_version() -> str:
    h = hashlib.sha1()
    for p in sorted((WEB / "assets").rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def build(cache: Path, root: Path, *, base: str = "/normfinder/", only: list[str] | None = None,
          workers: int | None = None, keep: int = 3, check: bool = True, switch: bool = True) -> dict:
    zips = cache / "zips"
    paths = sorted(zips.glob("*.zip"))
    if only:
        paths = [p for p in paths if p.stem in only]
    if not paths:
        raise BuildError(f"keine Archive in {zips}")
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    current = root / "current"
    prev = current.resolve() if current.exists() else None
    prev_stats = {}
    if prev and (prev / "build.json").exists():
        prev_stats = json.loads((prev / "build.json").read_text())
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = releases / f"{stamp}.tmp"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    t0 = time.time()
    ctx = mp.get_context("fork")

    log.info("Lese %d Archive mit %d Prozessen …", len(paths), workers)
    infos, errors = [], []
    with ctx.Pool(workers) as pool:
        for info, err in pool.imap_unordered(_summarize, [str(p) for p in paths], chunksize=8):
            if err:
                errors.append(err)
                log.warning("übersprungen: %s", err)
            else:
                infos.append(info)
    reg = laws.Registry(infos)
    fetched = dt.date.today().strftime("%d.%m.%Y")
    site = render.Site(reg, base=base, asset_version=asset_version(), fetched=fetched)
    fts = search_index.IndexWriter(root / "tmp-fts" / stamp)
    _G.update(reg=reg, site=site, out=out, prev=prev, zips=zips, fts=fts)

    log.info("Erzeuge Seiten für %d Gesetze …", len(infos))
    results = []
    order = sorted(reg.by_slug)
    with ctx.Pool(workers) as pool:
        for k, r in enumerate(pool.imap_unordered(_render_law, order, chunksize=4), 1):
            results.append(r)
            if "error" in r:
                errors.append(f'{r["slug"]}: {r["error"]}')
            if k % 500 == 0:
                log.info("%d/%d Gesetze erzeugt", k, len(order))
    failed = {r["slug"] for r in results if "error" in r}
    ok_laws = [s for s in order if s not in failed]

    w = Writer(out, prev)
    log.info("Suchindex …")
    fts_stats = fts.finish([(s, reg.get(s).url, reg.get(s).abk) for s in ok_laws], out / "data" / "fts")
    shutil.rmtree(root / "tmp-fts", ignore_errors=True)

    # gemeinsame Seiten und Daten
    w.write("index.html", site.start_page(EXAMPLES, reg.core["landesrecht"]))
    w.write("suche/index.html", site.search_page())
    w.write("hinweise/index.html", site.info_page())
    w.write("404.html", site.not_found_page())
    w.write("gesetze/index.html", site.az_page(None))
    for letter in site.letters():
        w.write(f"gesetze/{letter}/index.html", site.az_page(letter))
    w.write("data/laws.json", laws_json(reg, ok_laws))
    core = [row for r in results if r.get("core") for row in r["core"]]
    order_core = {s: i for i, s in enumerate(reg.core["vorschlag_reihenfolge"])}
    url_rank = {reg.get(s).url: order_core.get(s, 99) for s in reg.by_slug}
    core.sort(key=lambda row: url_rank.get(row[0], 99))
    w.write("data/core.json", json.dumps({"norms": core, "landesrecht": reg.core["landesrecht"]},
                                         ensure_ascii=False, separators=(",", ":")))
    for s in ok_laws:   # Weiterleitung von der Kennung auf gesetze-im-internet.de
        info = reg.get(s)
        alt = gii.slugify(s)
        if alt != info.url and alt not in reg.by_url and alt not in laws.RESERVED:
            w.write(f"{alt}/index.html", site.redirect_page(site.law_url(s)))
    copy_assets(out, w)
    sitemaps(out, w, site, reg, ok_laws)

    norms = sum(r.get("norms", 0) for r in results)
    stats = {"stamp": stamp, "code": code_version(), "laws": len(ok_laws), "norms": norms, "errors": errors,
             "fts": fts_stats, "secs": round(time.time() - t0), "fetched": fetched,
             "written": w.written + sum(r.get("written", 0) for r in results),
             "linked": w.linked + sum(r.get("linked", 0) for r in results), "partial": bool(only)}
    (out / "build.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    log.info("Fertig: %d Gesetze, %d Normen, %d Fehler, %ss", stats["laws"], norms, len(errors), stats["secs"])

    if check:
        try:
            validate(out, stats, prev_stats, reg, full=not only)
        except BuildError:
            final = releases / f"{stamp}.failed"
            out.rename(final)
            raise
    final = releases / stamp
    out.rename(final)
    if switch:
        activate(root, final)
        prune(releases, keep, final)
    return stats


def laws_json(reg, slugs) -> str:
    """Kompaktes Verzeichnis aller Gesetze für den Eingabe-Parser im Browser.
    [url, abk, titel, zeichen, [weitere Schlüssel], kerngruppe, normzahl]"""
    rows = []
    groups = {g["name"]: i for i, g in enumerate(reg.core["gruppen"])}
    for s in slugs:
        i = reg.get(s)
        keys = set()
        for a in i.abbrevs:
            keys.add(laws.norm_key(a))
        keys.add(laws.norm_key(i.slug))
        keys.discard(laws.norm_key(i.abk))
        names = [n.lower() for n in i.names if len(n) <= 70]
        title = render.short_name(i) if i.core else laws.display_title(i.short or i.title)
        if len(title) > 90:
            title = title[:87] + "…"
        rows.append([i.url, i.abk, title, "a" if i.sign == "Art." else "p", sorted(keys), names[:3],
                     groups.get(i.core, -1), i.count])
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def copy_assets(out: Path, w: Writer):
    for p in sorted((WEB / "assets").rglob("*")):
        if p.is_file():
            w.write("assets/" + p.relative_to(WEB / "assets").as_posix(), p.read_bytes())


def sitemaps(out: Path, w: Writer, site, reg, slugs):
    urls = [site.base, site.base + "gesetze/"]
    for s in slugs:
        urls.append(site.law_url(s))
        idx = json.loads((out / reg.get(s).url / "index.json").read_text())
        urls.extend(f"{site.base}{reg.get(s).url}/{n[0]}" for n in idx["norms"])
    chunks = [urls[i:i + 45000] for i in range(0, len(urls), 45000)]
    for k, chunk in enumerate(chunks):
        body = "".join(f"<url><loc>{render.SITE}{u}</loc></url>" for u in chunk)
        w.write(f"sitemap-{k}.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>')
    idx = "".join(f"<sitemap><loc>{render.SITE}{site.base}sitemap-{k}.xml</loc></sitemap>" for k in range(len(chunks)))
    w.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{idx}</sitemapindex>')


# ---------------------------------------------------------------- Prüfen und Umschalten

CHECKS = [  # (Datei, erwarteter Text)
    ("bgb/573.html", "Ordentliche Kündigung des Vermieters"),
    ("gg/1.html", "Die Würde des Menschen ist unantastbar"),
    ("stgb/263.html", "Betrug"),
    ("zpo/29.html", "Erfüllungsort"),
]


def validate(out: Path, stats: dict, prev: dict, reg, full: bool):
    problems = []
    for rel in ("index.html", "data/laws.json", "data/fts/manifest.json", "assets/app.js", "assets/app.css"):
        if not (out / rel).exists():
            problems.append(f"fehlt: {rel}")
    if full:
        if stats["laws"] < 4000:
            problems.append(f"nur {stats['laws']} Gesetze (erwartet > 4000)")
        if stats["norms"] < 80000:
            problems.append(f"nur {stats['norms']} Normen (erwartet > 80000)")
        for rel, needle in CHECKS:
            p = out / rel
            if not p.exists() or needle not in p.read_text(encoding="utf-8"):
                problems.append(f"Stichprobe fehlgeschlagen: {rel}")
        for g in reg.core["gruppen"]:
            for s in g["gesetze"]:
                i = reg.get(s)
                if i is None or not (out / i.url / "index.html").exists():
                    problems.append(f"Kerngesetz fehlt: {s}")
        if prev and not prev.get("partial"):
            if stats["laws"] < 0.95 * prev.get("laws", 0):
                problems.append(f"Gesetze: {stats['laws']} statt bisher {prev['laws']} (−5 % oder mehr)")
            if stats["norms"] < 0.95 * prev.get("norms", 0):
                problems.append(f"Normen: {stats['norms']} statt bisher {prev['norms']} (−5 % oder mehr)")
    if problems:
        raise BuildError("Prüfung fehlgeschlagen: " + "; ".join(problems))


def activate(root: Path, release: Path):
    tmp = root / "current.new"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(os.path.relpath(release, root), tmp)
    os.replace(tmp, root / "current")
    log.info("Umgeschaltet auf %s", release.name)


def rollback(root: Path) -> str:
    current = (root / "current").resolve()
    stamps = sorted(p for p in (root / "releases").iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{8}-\d{6}", p.name))
    older = [p for p in stamps if p.name < current.name]
    if not older:
        raise BuildError("kein älterer Stand vorhanden")
    activate(root, older[-1])
    return older[-1].name


def prune(releases: Path, keep: int, active: Path):
    stamps = sorted(p for p in releases.iterdir() if p.is_dir() and re.fullmatch(r"\d{8}-\d{6}", p.name))
    for p in stamps[:-keep]:
        if p != active:
            shutil.rmtree(p, ignore_errors=True)
    for p in releases.iterdir():
        if p.name.endswith((".tmp", ".failed")) and p != active:
            age = time.time() - p.stat().st_mtime
            if age > 3 * 86400:
                shutil.rmtree(p, ignore_errors=True)
