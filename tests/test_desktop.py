"""Datenverwaltung der Desktop-Version (ohne Oberfläche)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from normfinder.desktop import CHECK_EVERY, DataManager, parse_line

FIX = Path(__file__).parent / "fixtures"


class Fortschritt(unittest.TestCase):
    def test_zeilen(self):
        self.assertEqual(parse_line("2026-11-02 INFO 200/6147 geprüft ({…})")[0], "Gesetze laden: 200 von 6147")
        text, frac = parse_line("INFO 3000/6147 Gesetze erzeugt")
        self.assertEqual(text, "Seiten erzeugen: 3000 von 6147")
        self.assertTrue(0.87 < frac < 0.98)
        self.assertEqual(parse_line("INFO Umgeschaltet auf 20261102-120000"), ("Fertig", 1.0))
        self.assertIsNone(parse_line("irgendwas anderes"))


class Ablauf(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dm = DataManager(self.tmp / "data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_release(self, partial: bool):
        rel = self.dm.root / "releases" / "20260101-000000"
        rel.mkdir(parents=True)
        (rel / "index.html").write_text("x")
        (rel / "build.json").write_text(json.dumps({"partial": partial, "laws": 7}))
        os.symlink("releases/20260101-000000", self.dm.root / "current")

    def test_erster_start(self):
        self.assertFalse(self.dm.ready())
        self.assertEqual(self.dm.plan(), ["core", "full"])
        fetch, build = self.dm.commands("core")
        self.assertIn("fetch", fetch)
        self.assertIn("bgb", fetch[fetch.index("--only") + 1].split(","))
        self.assertIn("--no-check", build)
        self.assertEqual(build[build.index("--keep") + 1], "1")

    def test_nur_kerngesetze_vorhanden(self):
        self.fake_release(partial=True)
        self.assertEqual(self.dm.plan(), ["full"])

    def test_vollstaendig_und_aktuell(self):
        self.fake_release(partial=False)
        (self.dm.root / "last-check").touch()
        self.assertEqual(self.dm.plan(), [])
        old = time.time() - CHECK_EVERY - 60
        os.utime(self.dm.root / "last-check", (old, old))
        self.assertEqual(self.dm.plan(), ["update"])
        self.assertEqual(self.dm.commands("update")[0][-1], "update")

    def test_erzeugen_mit_fortschritt(self):
        """Echter Lauf (python3 -m normfinder build) mit den Fixtures, Fortschritt aus dem Log."""
        cache = self.dm.cache / "zips"
        cache.mkdir(parents=True)
        for p in FIX.glob("*.zip"):
            shutil.copy(p, cache / p.name)

        class Lokal(DataManager):
            def commands(self, step):
                return [[sys.executable, "-m", "normfinder", "--root", str(self.root), "--cache", str(self.cache),
                         "--keep", "1", "--workers", "2", "build", "--no-check"]]

        dm = Lokal(self.dm.root)
        seen = []
        self.assertTrue(dm.run("core", seen.append))
        self.assertTrue(dm.ready())
        texts = [p.text for p in seen]
        self.assertTrue(any(t.startswith("Seiten erzeugen") or "gelesen" in t for t in texts), texts)
        self.assertEqual(seen[-1].fraction, 1.0)
        self.assertEqual(len([p for p in (dm.root / "releases").iterdir() if not p.name.endswith(".tmp")]), 1)

    def test_fehler_wird_gemeldet(self):
        class Kaputt(DataManager):
            def commands(self, step):
                return [[sys.executable, "-c", "import sys; print('ERROR kaputt'); sys.exit(3)"]]

        seen = []
        self.assertFalse(Kaputt(self.dm.root).run("update", seen.append))
        self.assertIn("kaputt", seen[-1].text)


if __name__ == "__main__":
    unittest.main()
