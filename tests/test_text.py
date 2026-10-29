"""Satzerkennung und Inline-Rendering."""
import unittest
from pathlib import Path

from normfinder import gii
from normfinder.text import Inline, ends_sentence, split_sentences

FIX = Path(__file__).parent / "fixtures"


def sentences(t):
    s = split_sentences(t)
    return [t[a:b].strip() for a, b in zip(s, s[1:] + [len(t)])]


class Satzerkennung(unittest.TestCase):
    def test_einfach(self):
        self.assertEqual(len(sentences("Der Vermieter kann nur kündigen, wenn er ein berechtigtes Interesse hat. "
                                       "Die Kündigung zum Zwecke der Mieterhöhung ist ausgeschlossen.")), 2)

    def test_abkuerzungen(self):
        t = "Die Frist beträgt nach § 573c Abs. 1 S. 2 drei Monate. Dies gilt z. B. auch i. V. m. Nr. 3 u. a. für Mieter. Ende."
        self.assertEqual(len(sentences(t)), 3)

    def test_ordinalzahl_und_datum(self):
        t = "Das Gesetz tritt am 1. Januar 2002 in Kraft. Es gilt ab dem 31. Dezember 2008 gelten Regeln. Weiter."
        self.assertEqual(sentences(t)[0], "Das Gesetz tritt am 1. Januar 2002 in Kraft.")
        self.assertEqual(len(sentences(t)), 3)
        self.assertEqual(len(sentences("Am 3. Oktober ist Feiertag.")), 1)

    def test_verweis_am_satzende(self):
        t = "Dies gilt entsprechend für Absatz 2. Der Vermieter muss zahlen."
        self.assertEqual(len(sentences(t)), 2)
        t = "Er richtet sich nach Satz 1 Nummer 2 Buchstabe a. Im Übrigen gilt Absatz 3."
        self.assertEqual(len(sentences(t)), 2)

    def test_jahreszahl_am_satzende(self):
        self.assertEqual(len(sentences("Das gilt bis 2027. Danach nicht mehr.")), 2)

    def test_paragraf_am_satzanfang(self):
        self.assertEqual(len(sentences("Er haftet. § 280 bleibt unberührt.")), 2)

    def test_satzende(self):
        self.assertTrue(ends_sentence("Ende."))
        self.assertTrue(ends_sentence("Ende.“ "))
        self.assertFalse(ends_sentence("liegt insbesondere vor, wenn"))

    def test_gegen_amtliche_satznummern(self):
        """Das EStG liefert amtliche Satznummern; die Heuristik muss sie fast vollständig treffen."""
        L = gii.load(FIX / "estg.zip")
        total = ok = 0
        for n in L.norms:
            for a in n.absaetze:
                for b in a.blocks:
                    if not isinstance(b, gii.Para):
                        continue
                    inl = Inline(b.runs)
                    gold = sorted(p for p, _ in inl.official_sentences())
                    if not gold:
                        continue
                    first = gold[0]
                    pred = [p + first for p in split_sentences(inl.text[first:])]
                    total += 1
                    # Positionsabweichung durch doppelte Leerzeichen zählt nicht
                    ok += len(pred) == len(gold) and all(abs(x - y) <= 2 for x, y in zip(pred, gold))
        self.assertGreater(total, 800)
        self.assertGreaterEqual(ok / total, 0.99, f"{ok}/{total}")


class InlineRendering(unittest.TestCase):
    def test_saetze_und_links(self):
        runs = [("t", "Er haftet nach "), ("o", "b", ""), ("t", "§ 280"), ("c", "b"), ("t", ". Das gilt auch hier.")]
        inl = Inline(runs)
        self.assertEqual(inl.text, "Er haftet nach § 280. Das gilt auch hier.")
        starts = split_sentences(inl.text)
        html = inl.render([], [(p, f'<span data-s="{i + 1}">') for i, p in enumerate(starts)])
        self.assertEqual(html.count("<span"), 2)
        self.assertEqual(html.count("</span>"), 2)
        self.assertIn("<b>§ 280</b>", html)

    def test_link_ueber_tag_wird_verworfen(self):
        runs = [("t", "nach § "), ("o", "i", ""), ("t", "280"), ("c", "i")]
        html = Inline(runs).render([(5, 12, "/x", "")])
        self.assertNotIn("<a", html)

    def test_link(self):
        html = Inline([("t", "nach § 280 BGB")]).render([(5, 10, "/normfinder/bgb/280", "")])
        self.assertIn('<a class="ref" href="/normfinder/bgb/280">§ 280</a>', html)

    def test_escaping(self):
        self.assertIn("&lt;script&gt;", Inline([("t", "<script>")]).render())


if __name__ == "__main__":
    unittest.main()
