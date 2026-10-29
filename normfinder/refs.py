"""Verweiserkennung im Normtext.

Erkennt Verweise wie
  § 573 Abs. 2 Nr. 1 · §§ 433 bis 435 · Artikel 1 Abs. 3 · Art. 229 § 6
und ordnet sie einem Gesetz zu:
  * „dieses Gesetzes“, „dieser Verordnung“ oder ohne Angabe → aktuelles Gesetz,
  * Kürzel dahinter („§ 29 ZPO“, „§ 8 VVG 2008“),
  * Name im Genitiv („§ 1 des Handelsgesetzbuchs“,
    „Artikel 246 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche“).
Verweise auf unbekannte Rechtsakte (EU-Verordnungen, „des Gesetzes vom …“)
bleiben unverlinkt, statt falsch ins aktuelle Gesetz zu zeigen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NUM = r"\d+[a-z]{0,2}\b"
SIGN = re.compile(r"(§§|§|\bArtikeln\b|\bArtikel\b|\bArt\.)\s*(" + NUM + ")")
SEP = re.compile(r"\s*(,|und|bis|oder|sowie|u\.)\s*(?=(?:§\s*)?\d)")
NEXTNUM = re.compile(r"(?:§\s*)?(" + NUM + ")")
SUB = re.compile(
    r"\s*(?P<k>Abs\.|Absatz|Absätze|Absätzen|Satz|Sätze|Sätzen|S\.|Nr\.|Nrn\.|Nummer|Nummern|"
    r"Buchstabe|Buchstaben|Buchst\.|lit\.|Halbsatz|Unterabsatz|Unterabs\.|Alternative|Alt\.|Var\.)"
    r"\s*(?P<v>\d+[a-z]{0,2}|[a-z]{1,2}\b(?=[\s,;.)]|$))"
    r"(?:\s*(?:,|und|bis|oder)\s*(?:\d+[a-z]{0,2}|[a-z]\b))*")
SUBKEY = {"Abs.": "abs", "Absatz": "abs", "Absätze": "abs", "Absätzen": "abs", "Satz": "satz",
          "Sätze": "satz", "Sätzen": "satz", "S.": "satz", "Nr.": "nr", "Nrn.": "nr", "Nummer": "nr",
          "Nummern": "nr", "Buchstabe": "lit", "Buchstaben": "lit", "Buchst.": "lit", "lit.": "lit"}
THIS_LAW = re.compile(r"\s*(?:dieses\s+(?:Gesetz(?:es|buch(?:e?s)?)?|Buch(?:e?s)?)|dieser\s+(?:Verordnung|Ordnung))\b")
LAW_ARTICLE = re.compile(r"\s*(?:des|der|eines|einer)\s+")
FOREIGN = re.compile(
    r"\s*(?:des|der|eines|einer|im|in)\s+(?:[\wÄÖÜäöüß\-]+\s+){0,3}?"
    r"(?:[A-ZÄÖÜ][\wäöüß\-]*(?:gesetz|gesetzes|gesetzbuch\w*|ordnung|verordnung|abkommens?|übereinkommens?|"
    r"vertrag\w*|richtlinie|statuts?|protokolls?|satzung|vereinbarung|konvention|charta|grundsätze)\b"
    r"|Gesetz(?:es)?\b|Verordnung\b|Richtlinie\b|Bekanntmachung\b|Anlage\b)")
EU = re.compile(r"\s*(?:\w+\s+){0,4}?\((?:EU|EG|EWG|Euratom)\)")
INTRA = re.compile(r"\b(Absatz|Absätze|Abs\.)\s*(\d+[a-z]?)\b")


@dataclass
class Target:
    law: str        # gii-Kennung
    id: str
    anchor: str = ""


def anchor_for(parts: dict) -> str:
    out = []
    for k in ("abs", "satz", "nr", "lit"):
        if parts.get(k):
            if k == "satz" and parts.get("nr"):
                continue  # „Satz 1 Nr. 2“: Ziel ist die Nummer
            out.append(f"{k}-{parts[k]}")
    return "-".join(out)


class Linker:
    def __init__(self, registry, href):
        """href(law_slug, norm_id, anchor) → URL"""
        self.reg = registry
        self.href = href

    def find(self, text: str, law: str, absaetze: set | None = None) -> list:
        """Liefert [(start, ende, url, titel)] für text im Gesetz law (gii-Kennung)."""
        out = []
        cur = self.reg.get(law)
        covered_until = 0
        spans = []
        for m in SIGN.finditer(text):
            if m.start() < covered_until:
                continue
            sign = m.group(1)
            plural = sign in ("§§", "Artikeln")
            is_art = sign.startswith("Art")
            nums = [(m.start(2), m.end(2), m.group(2))]
            pos = m.end()
            parts = {}
            art_para = None
            if is_art:
                mm = re.match(r"\s*§\s*(" + NUM + ")", text[pos:])
                if mm:
                    art_para = mm.group(1)
                    nums = [(m.start(2), pos + mm.end(), f"{m.group(2)}-{art_para}")]
                    pos += mm.end()
            # Unterteilungen der ersten Norm
            while True:
                sm = SUB.match(text, pos)
                if not sm:
                    break
                key = SUBKEY.get(sm.group("k"))
                if key and key not in parts:
                    parts[key] = sm.group("v").lower()
                pos = sm.end()
            sub_end = pos
            # weitere Normnummern („§§ 433 bis 435“, „§§ 3, 4 und 6“)
            if plural:
                while True:
                    sp = SEP.match(text, pos)
                    if not sp:
                        break
                    nm = NEXTNUM.match(text, sp.end())
                    if not nm:
                        break
                    nums.append((nm.start(1), nm.end(1), nm.group(1)))
                    pos = nm.end()
                    while True:
                        sm = SUB.match(text, pos)
                        if not sm:
                            break
                        pos = sm.end()
            covered_until = pos
            spans.append((m.start(), pos))
            target_law = self._law_after(text, pos, law, is_art and cur is not None and cur.sign != "Art.")
            if not target_law:
                continue
            info = self.reg.get(target_law)
            if info is None:
                continue
            title = "" if target_law == law else f"{info.abk}"
            if len(nums) == 1:
                nid = nums[0][2]
                if nid not in info.ids:
                    continue
                anchor = anchor_for(parts)
                out.append((m.start(), sub_end if parts else nums[0][1], self.href(target_law, nid, anchor), title))
            else:
                for k, (a, b, nid) in enumerate(nums):
                    if nid in info.ids:
                        out.append((m.start() if k == 0 else a, b, self.href(target_law, nid, ""), title))
        if absaetze:
            out.extend(self._intra(text, spans, absaetze))
        return sorted(out)

    def _law_after(self, text: str, pos: int, law: str, art_needs_law: bool) -> str | None:
        rest = text[pos:pos + 260]
        if THIS_LAW.match(rest):
            return law
        am = re.match(r"\s*", rest)
        hit = self.reg.match_abbrev(rest[am.end():])
        if hit:
            return hit[0]
        lm = LAW_ARTICLE.match(rest)
        if lm:
            hit = self.reg.match_name(rest[lm.end():])
            if hit:
                return hit[0]
        if FOREIGN.match(rest) or EU.match(rest):
            return None
        if art_needs_law:
            return None
        return law

    def _intra(self, text: str, spans: list, absaetze: set) -> list:
        out = []
        for m in INTRA.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            if m.group(2) not in absaetze:
                continue
            rest = text[m.end():m.end() + 120]
            # „Absatz 2 des § 5“ / „Absatz 1 der Richtlinie“ verweisen nach außen
            if re.match(r"(?:\s+(?:Satz|Nr\.|Nummer|Buchstabe)\s*\w+)*\s+(?:des|der|dieses|eines|einer|im|in)\b", rest):
                continue
            if re.match(r"\s+(?:§|Artikel|Art\.)", rest):
                continue
            end = m.end()
            sm = re.match(r"\s+Satz\s+(\d+)", rest)
            anchor = f"abs-{m.group(2)}"
            if sm:
                anchor += f"-satz-{sm.group(1)}"
                end += sm.end()
            out.append((m.start(), end, "#" + anchor, ""))
        return out
