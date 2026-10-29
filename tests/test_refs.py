"""Verweiserkennung, auch gesetzesübergreifend."""
import unittest
from pathlib import Path

from normfinder import gii, laws
from normfinder.refs import Linker

FIX = Path(__file__).parent / "fixtures"
REG = None


def setUpModule():
    global REG, LK
    infos = [laws.summarize(gii.load(p)) for p in sorted(FIX.glob("*.zip"))]
    REG = laws.Registry(infos)
    LK = Linker(REG, lambda law, nid, a: f"/{REG.get(law).url}/{nid}" + (f"#{a}" if a else ""))


def links(text, law="bgb", absaetze=frozenset({"1", "2", "3"})):
    return [(text[a:b], href) for a, b, href, _ in LK.find(text, law, set(absaetze))]


class Verweise(unittest.TestCase):
    def test_im_selben_gesetz(self):
        self.assertEqual(links("nach § 573 Abs. 2 Nr. 1"), [("§ 573 Abs. 2 Nr. 1", "/bgb/573#abs-2-nr-1")])
        self.assertEqual(links("gemäß § 204 Abs. 1 Nr. 4 Buchstabe a"),
                         [("§ 204 Abs. 1 Nr. 4 Buchstabe a", "/bgb/204#abs-1-nr-4-lit-a")])
        self.assertEqual(links("§ 26 Absatz 2 Satz 1"), [("§ 26 Absatz 2 Satz 1", "/bgb/26#abs-2-satz-1")])

    def test_mehrere_normen(self):
        r = links("die §§ 433 bis 435 und der §§ 28, 31a Abs. 1 Satz 2")
        self.assertEqual([h for _, h in r], ["/bgb/433", "/bgb/435", "/bgb/28", "/bgb/31a"])

    def test_dieses_gesetzes(self):
        self.assertEqual(links("§ 3 dieses Gesetzes", law="zpo"), [("§ 3", "/zpo/3")])

    def test_kuerzel_dahinter(self):
        self.assertEqual(links("§ 29 ZPO und § 823 BGB", law="stgb"), [("§ 29", "/zpo/29"), ("§ 823", "/bgb/823")])

    def test_name_im_genitiv(self):
        self.assertEqual(links("nach § 1 des Handelsgesetzbuchs"), [("§ 1", "/hgb/1")] if REG.get("hgb") else [])
        self.assertEqual(links("§ 263 des Strafgesetzbuches"), [("§ 263", "/stgb/263")])
        self.assertEqual(links("§ 29 der Zivilprozessordnung"), [("§ 29", "/zpo/29")])
        self.assertEqual(links("Artikel 229 § 6 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche"),
                         [("Artikel 229 § 6", f"/{REG.get('bgbeg').url}/229-6")])

    def test_grundgesetz(self):
        r = links("nach Artikel 1 Abs. 3 und Art. 20 Abs. 4", law="gg")
        self.assertEqual(r, [("Artikel 1 Abs. 3", "/gg/1#abs-3"), ("Art. 20 Abs. 4", "/gg/20#abs-4")])
        self.assertEqual(links("Artikel 1 des Grundgesetzes"), [("Artikel 1", "/gg/1")])

    def test_unbekannte_rechtsakte_nicht_verlinken(self):
        self.assertEqual(links("Artikel 6 Absatz 1 Buchstabe a der Verordnung (EU) 2016/679"), [])
        self.assertEqual(links("§ 12 des Telekommunikationsgesetzes"), [])
        self.assertEqual(links("§ 5 des Gesetzes vom 1. Januar 1990"), [])
        self.assertEqual(links("Artikel 3 ohne Gesetz"), [], "Artikel in einem §-Gesetz ohne Angabe")

    def test_nicht_existierende_norm(self):
        self.assertEqual(links("§ 99999"), [])

    def test_absatz_derselben_norm(self):
        self.assertEqual(links("die in Absatz 2 Satz 1 genannten"), [("Absatz 2 Satz 1", "#abs-2-satz-1")])
        self.assertEqual(links("Absatz 2 des § 5"), [("§ 5", "/bgb/5")])
        self.assertEqual(links("Absatz 9"), [], "Absatz existiert nicht")


class Register(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(REG.get("bgb").url, "bgb")
        self.assertEqual(REG.get("bgbeg").url, "egbgb")
        self.assertEqual(REG.get("gg").url, "gg")

    def test_kuerzel(self):
        self.assertEqual(REG.match_abbrev("ZPO bleibt")[0], "zpo")
        self.assertIsNone(REG.match_abbrev("Gesetz"))
        self.assertEqual(REG.match_name("Bürgerlichen Gesetzbuchs gilt")[0], "bgb")
        self.assertEqual(REG.match_name("Einführungsgesetzes zum Bürgerlichen Gesetzbuche")[0], "bgbeg")


if __name__ == "__main__":
    unittest.main()
