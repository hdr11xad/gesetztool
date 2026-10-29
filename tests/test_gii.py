"""XML-Parser an echten Archiven von gesetze-im-internet.de (tests/fixtures/*.zip)."""
import unittest
from pathlib import Path

from normfinder import gii
from normfinder.gii import Img, ListBlock, Para, Table
from normfinder.text import Inline

FIX = Path(__file__).parent / "fixtures"
_cache = {}


def law(slug):
    if slug not in _cache:
        _cache[slug] = gii.load(FIX / f"{slug}.zip", slug)
    return _cache[slug]


def norm(slug, nid):
    return next(n for n in law(slug).norms if n.id == nid)


def text(blocks):
    out = []
    for b in blocks:
        if isinstance(b, Para):
            out.append(Inline(b.runs).text)
        elif isinstance(b, ListBlock):
            for it in b.items:
                out.append(it.label + " " + text(it.blocks))
    return " ".join(out)


class Metadaten(unittest.TestCase):
    def test_abkuerzungen(self):
        self.assertEqual(law("bgb").abk, "BGB")
        self.assertEqual(law("gg").abk, "GG")
        self.assertEqual(law("stgb").abk, "StGB")
        self.assertEqual(law("zpo").abk, "ZPO")
        self.assertEqual(law("bgbeg").abk, "BGBEG")
        self.assertEqual(law("bgb").title, "Bürgerliches Gesetzbuch")
        self.assertEqual(law("baunvo").short, "Baunutzungsverordnung")

    def test_stand(self):
        typen = [t for t, _ in law("bgb").stand]
        self.assertIn("Stand", typen)
        self.assertTrue(law("bgb").builddate.startswith("20"))

    def test_zeichen(self):
        self.assertEqual(law("gg").sign, "Art.")
        self.assertEqual(law("bgb").sign, "§")
        self.assertEqual(law("bgbeg").sign, "Art.")


class Gliederung(unittest.TestCase):
    def test_tiefe_und_pfad(self):
        L = law("bgb")
        buecher = [u for u in L.units if u.depth == 1]
        self.assertEqual([u.label for u in buecher], ["Buch 1", "Buch 2", "Buch 3", "Buch 4", "Buch 5"])
        n = norm("bgb", "573")
        u = L.units[n.unit]
        self.assertEqual(u.label, "Unterkapitel 2")
        self.assertEqual(u.depth, 6)

    def test_gg_abschnitte(self):
        labels = [u.label for u in law("gg").units]
        self.assertIn("I.", labels)
        self.assertEqual(law("gg").units[0].title, "Die Grundrechte")

    def test_keine_inhaltsuebersicht_als_norm(self):
        for s in ("bgb", "stgb", "zpo", "baunvo"):
            self.assertFalse(any(n.label.startswith("Inhalts") for n in law(s).norms), s)


class Normen(unittest.TestCase):
    def test_bgb_573(self):
        n = norm("bgb", "573")
        self.assertEqual(n.label, "§ 573")
        self.assertEqual(n.title, "Ordentliche Kündigung des Vermieters")
        self.assertEqual([a.label for a in n.absaetze], ["1", "2", "3", "4"])
        abs2 = n.absaetze[1]
        lst = next(b for b in abs2.blocks if isinstance(b, ListBlock))
        self.assertEqual(lst.kind, "nr")
        self.assertEqual([i.key for i in lst.items], ["1", "2", "3"])
        self.assertIn("578 Abs. 3", " ".join(n.notes))
        self.assertEqual(n.gii, "__573")

    def test_verschachtelte_aufzaehlung(self):
        n = norm("bgb", "204")
        lst = next(b for b in n.absaetze[0].blocks if isinstance(b, ListBlock))
        keys = [i.key for i in lst.items]
        self.assertIn("1a", keys)
        nr4 = next(i for i in lst.items if i.key == "4")
        inner = next(b for b in nr4.blocks if isinstance(b, ListBlock))
        self.assertEqual(inner.kind, "lit")
        self.assertEqual([i.key for i in inner.items], ["a", "b"])
        # Text nach der inneren Aufzählung gehört weiter zu Nummer 4
        self.assertTrue(any(isinstance(b, Para) and b.cont for b in nr4.blocks))

    def test_gg_artikel(self):
        n = norm("gg", "1")
        self.assertEqual(n.label, "Art. 1")
        self.assertIn("Die Würde des Menschen ist unantastbar", text(n.absaetze[0].blocks))
        self.assertEqual(n.gii, "art_1")
        self.assertEqual(norm("gg", "praeambel").label, "Präambel")

    def test_weggefallen(self):
        n = norm("bgb", "3")
        self.assertEqual(n.kind, "r")
        self.assertEqual(n.label, "§§ 3 bis 6")
        self.assertEqual(n.covers, ["3", "4", "5", "6"])
        self.assertTrue(n.gone)
        self.assertTrue(norm("stgb", "48").gone)
        self.assertFalse(norm("stgb", "263").gone)

    def test_stgb_zpo(self):
        self.assertEqual(norm("stgb", "263").title, "Betrug")
        self.assertEqual(norm("zpo", "29").title, "Besonderer Gerichtsstand des Erfüllungsorts")
        self.assertEqual(len(norm("stgb", "263").absaetze), 7)

    def test_fussnoten_im_text(self):
        n = norm("bgb", "14")
        self.assertEqual(len(n.footnotes), 1)
        self.assertIn("Amtlicher Hinweis", Inline(n.footnotes[0].runs).text)
        self.assertEqual([a.label for a in n.absaetze], ["1", "2"])
        self.assertEqual(n.head_fns, [n.footnotes[0].id])

    def test_egbgb_artikel_mit_paragrafen(self):
        n = norm("bgbeg", "229-6")
        self.assertEqual(n.label, "Art. 229 § 6")
        self.assertEqual(n.gii, "art_229__6")
        self.assertEqual(norm("bgbeg", "3").label, "Art. 3")
        self.assertTrue(norm("bgbeg", "3").title.startswith("Anwendungsbereich"))

    def test_kennungen_eindeutig(self):
        for s in ("bgb", "gg", "stgb", "zpo", "estg", "baunvo", "bgbeg"):
            ids = [n.id for n in law(s).norms]
            self.assertEqual(len(ids), len(set(ids)), s)


class TabellenUndAnlagen(unittest.TestCase):
    def test_estg_anlagen(self):
        anl = [n for n in law("estg").norms if n.id.startswith("anlage")]
        self.assertGreaterEqual(len(anl), 3)
        self.assertEqual(anl[0].label, "Anlage 1")

    def test_tabelle(self):
        tables = []

        def walk(blocks):
            for b in blocks:
                if isinstance(b, Table):
                    tables.append(b)
                elif isinstance(b, ListBlock):
                    for it in b.items:
                        walk(it.blocks)
        for n in law("estg").norms:
            for a in n.absaetze:
                walk(a.blocks)
        self.assertGreater(len(tables), 10)
        spans = [c.colspan for t in tables for r in t.rows for c in r]
        self.assertTrue(any(s > 1 for s in spans), "Zellen über mehrere Spalten")
        self.assertTrue(all(len(t.rows) > 0 for t in tables))

    def test_baunvo_tabelle_inhalt(self):
        n = norm("baunvo", "17")
        self.assertTrue(any(isinstance(b, Table) for a in n.absaetze for b in a.blocks))

    def test_amtliche_satznummern(self):
        n = norm("estg", "39b")
        para = next(b for b in n.absaetze[1].blocks if isinstance(b, Para))
        marks = Inline(para.runs).official_sentences()
        self.assertEqual([m[1] for m in marks][:3], ["1", "2", "3"])


class Synthetisch(unittest.TestCase):
    XML = """<?xml version="1.0" encoding="UTF-8"?><dokumente builddate="20260101000000" doknr="X">
<norm><metadaten><jurabk>TestG</jurabk><amtabk>TestG</amtabk><langue>Testgesetz</langue></metadaten></norm>
<norm><metadaten><jurabk>TestG</jurabk><enbez>§ 1</enbez><titel>Bild &amp; Text</titel></metadaten>
<textdaten><text format="XML"><Content><P>(1) Siehe<BR/>Bild: <IMG SRC="a.gif" Width="10" Height="5" alt="A"/></P>
<P>(2) Fehlendes Bild <IMG SRC="fehlt.gif"/> wird ignoriert.</P><P>(3) Ein &auml;lteres Zeichen.</P></Content></text></textdaten></norm>
<norm><metadaten><jurabk>TestG</jurabk><enbez>Anlage</enbez><titel>(zu § 1)</titel></metadaten>
<textdaten><text format="XML"><Content><table><tgroup cols="2"><colspec colname="c1"/><colspec colname="c2"/>
<thead><row><entry namest="c1" nameend="c2">Kopf</entry></row></thead><tbody><row><entry morerows="1">A</entry><entry>B</entry></row>
<row><entry>C</entry></row></tbody></tgroup></table></Content></text></textdaten></norm></dokumente>"""

    def test_bilder_tabellen_entities(self):
        L = gii.parse_law("testg", self.XML.encode(), {"a.gif": b"GIF89a"})
        self.assertEqual(L.abk, "TestG")
        self.assertEqual(list(L.images), ["a.gif"])
        n = L.norms[0]
        self.assertEqual(n.title, "Bild & Text")
        self.assertEqual([a.label for a in n.absaetze], ["1", "2", "3"])
        runs = n.absaetze[0].blocks[0].runs
        self.assertTrue(any(r[0] == "i" and isinstance(r[1], Img) for r in runs))
        self.assertIn("älteres", Inline(n.absaetze[2].blocks[0].runs).text)
        t = L.norms[1].absaetze[0].blocks[0]
        self.assertIsInstance(t, Table)
        self.assertEqual(t.rows[0][0].colspan, 2)
        self.assertTrue(t.rows[0][0].head)
        self.assertEqual(t.rows[1][0].rowspan, 2)
        self.assertEqual(L.norms[1].id, "anlage")


if __name__ == "__main__":
    unittest.main()
