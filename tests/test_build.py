"""Erzeugung eines Stands aus den Fixtures: Seiten, Anker, Verweise, Umschalten, Rückfall."""
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from normfinder import build as B

FIX = Path(__file__).parent / "fixtures"


def make_cache(tmp: Path) -> Path:
    cache = tmp / "cache"
    (cache / "zips").mkdir(parents=True)
    for p in FIX.glob("*.zip"):
        shutil.copy(p, cache / "zips" / p.name)
    return cache


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.cache = make_cache(cls.tmp)
        cls.root = cls.tmp / "site"
        cls.stats = B.build(cls.cache, cls.root, workers=2, check=False)
        cls.cur = cls.root / "current"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def page(self, rel):
        return (self.cur / rel).read_text(encoding="utf-8")

    def test_struktur(self):
        for rel in ("index.html", "suche/index.html", "404.html", "gesetze/index.html", "gesetze/b/index.html",
                    "bgb/index.html", "bgb/573.html", "bgb/index.json", "gg/1.html", "egbgb/229-6.html",
                    "data/laws.json", "data/core.json", "data/fts/manifest.json", "sitemap.xml",
                    "assets/app.js", "assets/app.css", "assets/fonts/newsreader-latin.woff2", "hinweise/index.html"):
            self.assertTrue((self.cur / rel).exists(), rel)
        self.assertTrue(self.cur.is_symlink())
        self.assertEqual(self.stats["laws"], 7)

    def test_normseite(self):
        h = self.page("bgb/573.html")
        self.assertIn("<title>§ 573 BGB – Ordentliche Kündigung des Vermieters | Normfinder</title>", h)
        self.assertIn('id="abs-2"', h)
        self.assertIn('id="abs-2-nr-1"', h)
        self.assertIn('id="abs-1-satz-2"', h)
        self.assertIn('href="https://www.gesetze-im-internet.de/bgb/__573.html"', h)
        self.assertIn("Keine Rechtsberatung.", h)
        self.assertIn("Maßgeblich ist die amtliche Fassung", h)
        self.assertIn('rel="prev" href="/normfinder/bgb/572"', h)
        self.assertIn('rel="next" href="/normfinder/bgb/573a"', h)
        self.assertIn('<link rel="canonical" href="https://fsr-jura-halle.de/normfinder/bgb/573">', h)
        self.assertIn("zuletzt geändert durch", h)
        self.assertIn("https://fsr-jura-halle.de/impressum/", h)
        # keine externen Ressourcen
        for m in re.finditer(r'(?:src|href)="(https?://[^"]+)"', h):
            tag_start = h.rfind("<", 0, m.start())
            self.assertTrue(h.startswith("<a", tag_start) or h.startswith("<link rel=\"canonical\"", tag_start), m.group(1))

    def test_verweise_verlinkt(self):
        h = self.page("bgb/573a.html")
        self.assertIn('href="/normfinder/bgb/573"', h)
        h = self.page("bgb/14.html")
        self.assertIn('href="#fn-', h)
        self.assertIn('id="fn-', h)

    def test_einzelner_satz_ohne_nummer(self):
        h = self.page("bgb/1004.html")
        self.assertIn('id="abs-2"', h)
        abs2 = h[h.index('id="abs-2"'):]
        abs2 = abs2[:abs2.index("</div></div>")]
        self.assertNotIn('class="sn"', abs2, "ein Satz → keine Satznummer")

    def test_bereich_und_aliase(self):
        self.assertTrue((self.cur / "bgb/4.html").exists())
        self.assertIn("weggefallen", self.page("bgb/4.html"))
        idx = json.loads(self.page("bgb/index.json"))
        self.assertEqual(idx["alias"]["5"], "3")
        self.assertEqual(idx["abk"], "BGB")
        eg = json.loads(self.page("egbgb/index.json"))
        self.assertEqual(eg["alias"]["229"], "229-1")

    def test_gliederung(self):
        h = self.page("bgb/index.html")
        self.assertIn('id="g-0"', h)
        self.assertIn("Buch 1", h)
        self.assertIn('href="/normfinder/bgb/573"', h)

    def test_daten(self):
        laws = json.loads(self.page("data/laws.json"))
        urls = {r[0] for r in laws}
        self.assertTrue({"bgb", "gg", "egbgb", "zpo", "stgb"} <= urls)
        m = json.loads(self.page("data/fts/manifest.json"))
        self.assertEqual(m["docs"], sum(len(json.loads(self.page(f"{u}/index.json"))["norms"]) for u, *_ in m["laws"]))
        core = json.loads(self.page("data/core.json"))
        self.assertTrue(any(n[0] == "bgb" and n[1] == "573" for n in core["norms"]))
        self.assertIn("landesrecht", core)

    def test_startseite(self):
        h = self.page("index.html")
        self.assertIn("Kerngesetze", h)
        self.assertIn("Landesrechtsportal", h)
        self.assertIn("landesrecht.sachsen-anhalt.de", h)
        self.assertIn('href="/normfinder/bgb/"', h)
        self.assertIn("Zur FSR-Website", h)


class Umschalten(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = make_cache(self.tmp)
        self.root = self.tmp / "site"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pruefung_haelt_alten_stand(self):
        B.build(self.cache, self.root, workers=2, check=False)
        first = (self.root / "current").resolve()
        # vollständiger Lauf mit Prüfung: 7 Gesetze sind „auffällig klein“ → bleibt beim alten Stand
        with self.assertRaises(B.BuildError):
            B.build(self.cache, self.root, workers=2, check=True)
        self.assertEqual((self.root / "current").resolve(), first)
        self.assertTrue(any(p.name.endswith(".failed") for p in (self.root / "releases").iterdir()))

    def test_hardlinks_und_rollback(self):
        import time
        B.build(self.cache, self.root, workers=2, check=False)
        first = (self.root / "current").resolve()
        time.sleep(1.1)
        s2 = B.build(self.cache, self.root, workers=2, check=False)
        second = (self.root / "current").resolve()
        self.assertNotEqual(first, second)
        self.assertGreater(s2["linked"], 0.9 * (s2["linked"] + s2["written"]), "unveränderte Dateien verlinkt")
        self.assertEqual(os.stat(first / "bgb/573.html").st_ino, os.stat(second / "bgb/573.html").st_ino)
        self.assertEqual(B.rollback(self.root), first.name)
        self.assertEqual((self.root / "current").resolve(), first)


if __name__ == "__main__":
    unittest.main()
