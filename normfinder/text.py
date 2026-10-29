"""Satzerkennung und Inline-Rendering.

Die Satzerkennung stammt aus dem Prototyp und ist an den amtlichen
Satznummern geprüft, die manche Gesetze (EStG, AO, UStG …) im XML mitliefern
(<SUP class="Rec">). Wo diese Nummern vorhanden sind, gelten sie; sonst
greift die Heuristik.
"""
from __future__ import annotations

import html
import re

# Abkürzungen, nach denen ein Punkt keinen Satz beendet
ABBR = set("""
abs nr nrn s art artt buchst bzw vgl usw ziff ca dr st ff f gem abschn kap bgbl rgbl abl ggf sog
inkl evtl einschl zzgl lit anh anl bd eg ewg eu euratom verf jh u ä z b d h a i e o m v l g w
tz rn rdnr bek anm allg bes betr abt str lfd max min mio mrd tsd nachf geb hrsg ausg prof dipl
ing pos kfz co kg nr. bzgl ebd entspr erg gez hs inkl insb jew kap lt mind mtl nachf o.ä od
ord pkt rd bgbi abi gbl vobl sa sek so sp spez stellv tel tlw urspr usf uvm vers verw vj vorm vs zt zul zw
""".split())
REFWORD = re.compile(r"^(§§?|abs|absatz|absatzes|absätze|nr|nummer|nummern|satz|satzes|sätze|s|art|artikel|"
                     r"buchstabe|buchstaben|buchst|anlage|anlagen|teil|teils|kapitel|abschnitt|abschnitts|"
                     r"halbsatz|unterabsatz|ziffer|anhang|titel|tabelle|spalte|zeile|position)\.?$", re.I)
BOUNDARY = re.compile(r"[.?!][\"“”)]?(?:\s+(?=[A-ZÄÖÜ„§(])|(?=[A-ZÄÖÜ§][a-zäöü ]))")
MONTH = re.compile(r"(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b")


def split_sentences(text: str) -> list[int]:
    """Startpositionen der Sätze (immer mit 0 beginnend)."""
    starts = [0]
    for m in BOUNDARY.finditer(text):
        dot = m.start()
        if text[dot] == ".":
            before = text[starts[-1]:dot]
            lw = (re.search(r"(\S+)$", before) or [None, ""])[1] if before else ""
            lwl = lw.lower().lstrip("(„\"")
            if re.fullmatch(r"[a-z]{1,2}", lwl) and re.search(r"(Buchstabe|Buchst\.|lit\.|Doppelbuchstabe)\s+\S+$", before):
                pass  # „… Buchstabe a. Satz“ endet hier
            elif lwl in ABBR or re.fullmatch(r"[a-zäöü]", lwl, re.I):
                continue
            if m.end() == dot + 1 and (len(lwl) <= 3 or "." in lwl):
                continue  # kein Leerzeichen: nur nach längerem Wort als Satzende werten
            if re.fullmatch(r"[a-zäöü]+\.[a-zäöü]+", lwl):  # „z.B.“, „i.V.“
                continue
            if re.fullmatch(r"\d+[a-z]?", lwl):
                if MONTH.match(text, m.end()):
                    continue  # Datum („am 31. Dezember“)
                prev = before.split()[-8:-1]
                if re.fullmatch(r"(1[89]|20)\d\d", lwl):
                    pass  # Jahreszahl am Satzende
                elif not any(REFWORD.match(w) for w in prev):
                    continue  # Ordinalzahl oder Datum („am 1. Januar“)
            if re.fullmatch(r"[IVXLC]+", lw):  # „Buch III. Abschnitt“
                continue
        if m.end() < len(text):
            starts.append(m.end())
    return starts


def ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.?!][\"“”)]?\s*$", text))


# ---------------------------------------------------------------- Normalisierung für die Suche

def fold(s: str) -> str:
    s = s.lower()
    return (s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
            .replace("é", "e").replace("è", "e"))


# ---------------------------------------------------------------- Inline-Rendering

def esc(s: str) -> str:
    return html.escape(s, quote=True)


class Inline:
    """Rendert Inline-Runs zu HTML, mit optionalen Satzspannen und Verweislinks.

    runs:   Liste aus („t“, Text) | („o“, tag, klasse) | („c“, tag) | („v“, html)
            | („f“, fußnoten-id) | („i“, Img) | („s“, amtliche Satznummer)
    """

    def __init__(self, runs: list, img_url=None, fn_href=None):
        self.runs = runs
        self.img_url = img_url or (lambda src: src)
        self.fn_href = fn_href or (lambda fid: "#fn-" + fid)
        parts, marks = [], []
        pos = 0
        for r in runs:
            if r[0] == "t":
                parts.append(r[1])
                pos += len(r[1])
            else:
                marks.append((pos, r))
        self.text = "".join(parts)
        self.marks = marks

    def official_sentences(self) -> list[tuple[int, str]]:
        return [(pos, r[1]) for pos, r in self.marks if r[0] == "s"]

    def _markup(self, r) -> str:
        k = r[0]
        if k == "o":
            return f'<{r[1]} class="{r[2]}">' if r[2] else f"<{r[1]}>"
        if k == "c":
            return f"</{r[1]}>"
        if k == "v":
            return r[1]
        if k == "f":
            return f'<sup class="fnr"><a href="{esc(self.fn_href(r[1]))}">*</a></sup>'
        if k == "i":
            img = r[1]
            wh = f' width="{img.width}" height="{img.height}"' if img.width and img.height else ""
            return f'<img src="{esc(self.img_url(img.src))}" alt="{esc(img.alt)}"{wh} loading="lazy">'
        return ""

    def render(self, links=(), sentences=None) -> str:
        """links: [(start, end, href, title)], sentences: [(start, open_html)] – Spannen enden
        jeweils am nächsten Satzanfang bzw. am Textende."""
        text = self.text
        events: dict[int, list] = {}
        tag_pos = [p for p, _ in self.marks]
        good_links = []
        for (a, b, href, title) in links:
            if any(a < p < b for p in tag_pos):
                continue
            if sentences and any(a < s < b for s, _ in sentences):
                continue
            good_links.append((a, b, href, title))
        cuts = {0, len(text)}
        for a, b, *_ in good_links:
            cuts.update((a, b))
        if sentences:
            cuts.update(s for s, _ in sentences)
        cuts.update(tag_pos)
        cuts = sorted(c for c in cuts if 0 <= c <= len(text))

        sent_at = dict(sentences or [])
        link_start = {a: (b, href, title) for a, b, href, title in good_links}
        mark_at: dict[int, list] = {}
        for p, r in self.marks:
            mark_at.setdefault(p, []).append(r)

        out = []
        stack: list = []        # offene Inline-Tags
        in_sent = False
        link_end = None
        for i, c in enumerate(cuts):
            if link_end == c:
                out.append("</a>")
                link_end = None
            if c in sent_at:
                if in_sent:
                    out.extend(f"</{t[1]}>" for t in reversed(stack))
                    out.append("</span>")
                    if out and c > 0:
                        out.append(" ")
                out.append(sent_at[c])
                out.extend(self._markup(t) for t in stack)
                in_sent = True
            for r in mark_at.get(c, []):
                if r[0] == "s":
                    continue
                if r[0] == "o":
                    stack.append(r)
                elif r[0] == "c":
                    for j in range(len(stack) - 1, -1, -1):
                        if stack[j][1] == r[1]:
                            stack.pop(j)
                            break
                out.append(self._markup(r))
            if c in link_start and link_end is None:
                b, href, title = link_start[c]
                t = f' title="{esc(title)}"' if title else ""
                out.append(f'<a class="ref" href="{esc(href)}"{t}>')
                link_end = b
            if i + 1 < len(cuts):
                seg = text[c:cuts[i + 1]]
                if cuts[i + 1] in sent_at and in_sent:
                    seg = seg.rstrip()
                out.append(esc(seg))
        if link_end is not None:
            out.append("</a>")
        if in_sent:
            out.extend(f"</{t[1]}>" for t in reversed(stack))
            out.append("</span>")
        return "".join(out)
