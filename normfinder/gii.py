"""Parser für das amtliche XML-Format von gesetze-im-internet.de (gii-norm.dtd).

Ein Archiv enthält ein <dokumente>-Element mit einer Folge von <norm>-Elementen:
  * die erste Norm trägt die Stammdaten des Gesetzes (jurabk, amtabk, langue,
    kurzue, standangabe) und meist Hinweise in <fussnoten>,
  * Gliederungseinheiten haben <gliederungseinheit> mit einer Kennzahl, deren
    Länge die Tiefe angibt (3 Ziffern je Ebene),
  * Einzelnormen haben <enbez> („§ 573“, „Art 1“, „Anlage 2“, „(XXXX) §§ 3 bis 6“)
    und optional <titel>; der Text steht in textdaten/text/Content,
    Fußnoten zum Text in textdaten/text/Footnotes, Änderungshinweise
    („+++ … +++“) in textdaten/fussnoten.

Das Ergebnis ist ein schlankes Modell (Law, Unit, Norm, Absatz und Blöcke),
das render.py zu HTML und search_index.py zum Suchindex weiterverarbeitet.
"""
from __future__ import annotations

import html
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

# ---------------------------------------------------------------- Modell


@dataclass
class Para:
    runs: list            # siehe Inline-Runs unten
    cont: bool = False    # setzt einen Satz fort, der vor einer Aufzählung begann


@dataclass
class Item:
    label: str            # wie im Text: „1.“, „a)“, „aa)“, „-“
    key: str              # für Anker und Zielmarkierung: „1“, „a“, „aa“, ""
    blocks: list


@dataclass
class ListBlock:
    kind: str             # nr | lit | dlit | plain
    items: list


@dataclass
class Cell:
    blocks: list
    colspan: int = 1
    rowspan: int = 1
    align: str = ""
    head: bool = False


@dataclass
class Table:
    rows: list            # list[list[Cell]]
    widths: list          # relative Spaltenbreiten (Prozent) oder []


@dataclass
class Pre:
    text: str


@dataclass
class Img:
    src: str
    width: int = 0
    height: int = 0
    alt: str = ""


@dataclass
class Heading:
    runs: list


@dataclass
class Absatz:
    label: str            # „1“, „2a“ oder "" (ohne Absatzzählung)
    blocks: list


@dataclass
class Footnote:
    id: str
    mark: str
    runs: list


@dataclass
class Norm:
    enbez: str
    kind: str             # p (§), a (Art), r (Bereich §§/Art), x (Anlage u. Ä.)
    id: str               # URL-Kennung: „573“, „1“, „229-6“, „anlage-1“
    label: str            # Anzeige: „§ 573“, „Art. 1“, „§§ 3 bis 6“, „Anlage 1“
    title: str
    unit: int             # Index der tiefsten Gliederungseinheit oder -1
    absaetze: list = field(default_factory=list)
    footnotes: list = field(default_factory=list)
    notes: list = field(default_factory=list)   # Hinweise aus <fussnoten>
    covers: list = field(default_factory=list)  # bei Bereichen: alle Nummern
    gone: bool = False
    gii: str = ""          # Dateiname der Einzelnorm auf gesetze-im-internet.de
    head_fns: list = field(default_factory=list)  # Fußnotenverweise an der Überschrift
    sign: str = "§"        # Paragraphen- oder Artikelzeichen der Norm


@dataclass
class Unit:
    depth: int
    label: str            # „Buch 1“, „Abschnitt 3“
    title: str
    first: int            # Index der ersten Norm in dieser Einheit


@dataclass
class Law:
    slug: str             # Kennung auf gesetze-im-internet.de
    abk: str              # amtliche Abkürzung, sonst juris-Abkürzung
    jurabk: list
    title: str            # langue
    short: str            # kurzue
    stand: list           # [(typ, kommentar)]
    date: str             # Ausfertigungsdatum
    builddate: str
    notes: list
    units: list
    norms: list
    images: dict = field(default_factory=dict)  # Dateiname -> Bytes
    sign: str = "§"       # überwiegendes Normzeichen: § oder Art.


# ---------------------------------------------------------------- Helfer

WS = re.compile(r"\s+")


def clean(s: str | None) -> str:
    return WS.sub(" ", s or "").strip()


def plain(el: ET.Element | None) -> str:
    """Text eines Elements; <BR/> wird zum Leerzeichen."""
    if el is None:
        return ""
    parts = []
    def walk(e):
        if e.text:
            parts.append(e.text)
        for c in e:
            if c.tag == "BR":
                parts.append(" ")
            else:
                walk(c)
            if c.tail:
                parts.append(c.tail)
    walk(el)
    return clean("".join(parts))


def slugify(s: str) -> str:
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def gii_name(enbez: str) -> str:
    """Dateiname der Einzelnorm bei gesetze-im-internet.de („§ 573“ → „__573“)."""
    s = enbez.lower()
    s = re.sub(r"\s*§\s*", "__", s)
    s = s.replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "_", s)


def runs_text(runs: list) -> str:
    return "".join(r[1] for r in runs if r[0] == "t")


# ---------------------------------------------------------------- Inline

INLINE_TAGS = {
    "B": ("b", ""), "I": ("i", ""), "U": ("u", ""), "SUP": ("sup", ""), "SUB": ("sub", ""),
    "SP": ("span", "sp"), "small": ("small", ""), "F": ("span", "f"),
}
TRANSPARENT = {"NB", "noindex", "Revision", "FILE", "ABWFORMAT_TEXT", "span", "em", "strong"}
SKIP = {"ABWFORMAT", "kommentar", "FnArea", "TOC"}
BLOCK_TAGS = {"P", "LA", "DL", "table", "pre", "Title", "Subtitle", "Content", "Footnotes"}


class Builder:
    """Wandelt gemischten Inhalt (Text + Elemente) in eine Blockliste um."""

    def __init__(self, law_images: set[str]):
        self.images = law_images

    def blocks(self, el: ET.Element, include_text=True) -> list:
        out: list = []
        cur: list = []
        after_block = False

        def flush():
            nonlocal cur
            if any((r[0] == "t" and r[1].strip()) or r[0] in ("v", "s", "i", "f") for r in cur):
                out.append(Para(trim(cur), cont=after_block))
            cur = []

        def add_text(t):
            if t:
                cur.append(("t", t))

        if include_text:
            add_text(el.text)
        for ch in el:
            tag = ch.tag
            if tag in SKIP:
                add_text(ch.tail)
                continue
            if self.is_block(ch):
                flush()
                out.extend(self.block(ch))
                after_block = True
                add_text(ch.tail)
                continue
            self.inline(ch, cur)
            add_text(ch.tail)
        flush()
        return out

    def is_block(self, ch: ET.Element) -> bool:
        if ch.tag == "IMG":
            return ch.get("Pos", "") == "block" or ch.get("Align", "") == "center"
        return ch.tag in BLOCK_TAGS

    def block(self, el: ET.Element) -> list:
        tag = el.tag
        if tag in ("P", "Content", "LA"):
            return self.blocks(el)
        if tag == "DL":
            return [self.dl(el)]
        if tag == "table":
            return [self.table(el)]
        if tag == "pre":
            return [Pre(pre_text(el))]
        if tag in ("Title", "Subtitle"):
            runs: list = []
            self.inline_children(el, runs)
            runs = trim(runs)
            return [Heading(runs)] if runs_text(runs).strip() else []
        if tag == "IMG":
            img = self.img(el)
            return [img] if img else []
        return self.blocks(el)

    def img(self, el: ET.Element) -> Img | None:
        src = el.get("SRC", "")
        if not src or src not in self.images:
            return None
        def num(v):
            try:
                return int(float(v or 0))
            except ValueError:
                return 0
        return Img(src, num(el.get("Width")), num(el.get("Height")), el.get("alt", ""))

    def inline(self, ch: ET.Element, cur: list):
        tag = ch.tag
        if tag == "BR":
            cur.append(("v", "<br>"))
            return
        if tag == "FnR":
            cur.append(("f", ch.get("ID", "")))
            return
        if tag == "IMG":
            img = self.img(ch)
            if img:
                cur.append(("i", img))
            return
        if tag == "SUP" and ch.get("class") == "Rec":
            cur.append(("s", clean(plain(ch))))
            return
        if tag in INLINE_TAGS:
            html_tag, cls = INLINE_TAGS[tag]
            cur.append(("o", html_tag, cls))
            self.inline_children(ch, cur)
            cur.append(("c", html_tag))
            return
        # unbekannte und transparente Elemente: Inhalt übernehmen
        self.inline_children(ch, cur)

    def inline_children(self, el: ET.Element, cur: list):
        if el.text:
            cur.append(("t", el.text))
        for ch in el:
            if ch.tag in SKIP:
                pass
            elif self.is_block(ch):
                # Block mitten im Inline-Kontext (selten): als Zeilenumbruch + Text
                cur.append(("v", "<br>"))
                for b in self.block(ch):
                    if isinstance(b, Para):
                        cur.extend(b.runs)
            else:
                self.inline(ch, cur)
            if ch.tail:
                cur.append(("t", ch.tail))

    def dl(self, el: ET.Element) -> ListBlock:
        typ = (el.get("Type") or "").lower()
        items: list[Item] = []
        label = None
        for ch in el:
            if ch.tag == "DT":
                label = clean(plain(ch))
            elif ch.tag == "DD":
                blocks = self.blocks(ch)
                lab = label or ""
                items.append(Item(lab, item_key(lab), blocks))
                label = None
        keys = [i.key for i in items if i.key]
        if typ == "arabic" or (keys and all(re.fullmatch(r"\d+[a-z]?", k) for k in keys)):
            kind = "nr"
        elif typ in ("alpha", "a-alpha") or (keys and all(re.fullmatch(r"[a-z]", k) for k in keys)):
            kind = "lit"
        elif keys and all(re.fullmatch(r"([a-z])\1+", k) for k in keys):
            kind = "dlit"
        else:
            kind = "plain" if not keys else "nr" if re.fullmatch(r"\d.*", keys[0]) else "lit"
        return ListBlock(kind, items)

    def table(self, el: ET.Element) -> Table:
        rows: list = []
        widths: list = []
        for tg in el.iter("tgroup"):
            specs = [c for c in tg if c.tag == "colspec"]
            names = [c.get("colname") or f"col{i + 1}" for i, c in enumerate(specs)]
            ws = []
            for c in specs:
                m = re.match(r"([\d.]+)\*", c.get("colwidth") or "")
                ws.append(float(m.group(1)) if m else 0)
            if ws and all(ws):
                total = sum(ws)
                widths = [round(100 * w / total, 1) for w in ws]
            for part in tg:
                if part.tag not in ("thead", "tbody", "tfoot"):
                    continue
                for row in part.iter("row"):
                    cells = []
                    for e in row:
                        if e.tag != "entry":
                            continue
                        span = 1
                        st, en = e.get("namest"), e.get("nameend")
                        if st in names and en in names:
                            span = names.index(en) - names.index(st) + 1
                        try:
                            rs = int(e.get("morerows") or 0) + 1
                        except ValueError:
                            rs = 1
                        cells.append(Cell(self.blocks(e), max(span, 1), rs,
                                          (e.get("align") or "").lower(), part.tag == "thead"))
                    rows.append(cells)
        return Table(rows, widths)


def item_key(label: str) -> str:
    k = label.strip().strip("().").rstrip(")").lower()
    return k if re.fullmatch(r"[0-9]+[a-z]{0,2}|[a-z]{1,3}", k) else ""


def pre_text(el: ET.Element) -> str:
    parts = []
    def walk(e):
        if e.text:
            parts.append(e.text)
        for c in e:
            if c.tag == "BR":
                parts.append("\n")
            else:
                walk(c)
            if c.tail:
                parts.append(c.tail)
    walk(el)
    text = "".join(parts)
    text = re.sub(r"\n[ \t]*\n", "\n", text)
    return "\n".join(l.rstrip() for l in text.strip("\n").split("\n"))


def trim(runs: list) -> list:
    """Whitespace normalisieren, führende/abschließende Leerzeichen entfernen."""
    out = []
    for r in runs:
        if r[0] == "t":
            t = WS.sub(" ", r[1])
            if out and out[-1][0] == "t":
                out[-1] = ("t", out[-1][1] + t)
            else:
                out.append(("t", t))
        else:
            out.append(r)
    # Leerzeichen nach <br> und am Rand entfernen
    for i, r in enumerate(out):
        if r[0] == "t" and i > 0 and out[i - 1] == ("v", "<br>"):
            out[i] = ("t", r[1].lstrip())
    while out and out[0][0] == "t" and not out[0][1].strip():
        out.pop(0)
    if out and out[0][0] == "t":
        out[0] = ("t", out[0][1].lstrip())
    while out and (out[-1][0] == "t" and not out[-1][1].strip() or out[-1] == ("v", "<br>")):
        out.pop()
    if out and out[-1][0] == "t":
        out[-1] = ("t", out[-1][1].rstrip())
    return out


# ---------------------------------------------------------------- Absätze

ABS_RE = re.compile(r"^\((\d{1,3}[a-z]?)\)\s*")


def split_absaetze(blocks: list) -> list[Absatz]:
    out: list[Absatz] = []
    cur: Absatz | None = None
    for b in blocks:
        if isinstance(b, Para) and b.runs and b.runs[0][0] == "t":
            m = ABS_RE.match(b.runs[0][1])
            if m and not b.cont:
                rest = b.runs[0][1][m.end():]
                runs = ([("t", rest)] if rest else []) + b.runs[1:]
                cur = Absatz(m.group(1), [])
                out.append(cur)
                if runs:
                    cur.blocks.append(Para(runs))
                continue
        if cur is None:
            cur = Absatz("", [])
            out.append(cur)
        cur.blocks.append(b)
    # Absätze, die nur aus einem Fußnotenverweis bestehen, entfernen
    return [a for a in out if a.blocks or a.label]


# ---------------------------------------------------------------- Normbezeichnungen

GONE_TEXT = re.compile(r"^\(?\s*(weggefallen|aufgehoben|gegenstandslos)\s*\)?\.?$|^-+$", re.I)


def expand_range(spec: str) -> list[str]:
    toks = re.split(r"\s*(bis|und|u\.|,)\s*", spec)
    ids = [t for t in toks if t and t not in ("bis", "und", "u.", ",")]
    seps = [t for t in toks if t in ("bis", "und", "u.", ",")]
    covers = []
    for j, a in enumerate(ids):
        covers.append(a)
        if j < len(seps) and seps[j] == "bis" and j + 1 < len(ids):
            b = ids[j + 1]
            if a.isdigit() and b.isdigit() and int(b) - int(a) < 500:
                covers += [str(x) for x in range(int(a) + 1, int(b))]
            else:
                ma = re.fullmatch(r"(\d+)([a-z]?)", a)
                mb = re.fullmatch(r"(\d+)([a-z])", b)
                if ma and mb and ma.group(1) == mb.group(1):
                    start = ord(ma.group(2)) + 1 if ma.group(2) else ord("a")
                    covers += [ma.group(1) + chr(c) for c in range(start, ord(mb.group(2)))]
                elif ma and mb and int(mb.group(1)) - int(ma.group(1)) < 500:
                    covers += [str(x) for x in range(int(ma.group(1)) + 1, int(mb.group(1)) + 1)]
    seen = set()
    return [c for c in covers if not (c in seen or seen.add(c))]


def describe(enbez: str) -> tuple[str, str, str, list, str]:
    """→ (kind, id, label, covers, sign) aus der Einzelnormbezeichnung."""
    e = clean(enbez.replace(" ", " "))
    e = re.sub(r"^\(XXXX\)\s*", "", e)
    e = re.sub(r"\b(bis|und|u\.|,)\s*(?:Art(?:ikel|\.)?|§§?)\s*(?=\d)", r"\1 ", e)  # „Art 5 bis Art 7“
    if not e:
        return "x", "text", "", [], ""
    m = re.fullmatch(r"§\s*(\d+(?:\.\d+)+[a-z]{0,2})", e, re.I)  # „§ 1.01“ (Binnenschifffahrt u. a.)
    if m:
        n = m.group(1).lower()
        return "p", n, f"§ {n}", [], "§"
    m = re.fullmatch(r"§\s*(\d+[a-z]{0,2})(?:\s*\.)?", e, re.I)
    if m:
        n = m.group(1).lower()
        return "p", n, f"§ {n}", [], "§"
    m = re.fullmatch(r"Art(?:ikel|\.)?\s*(\d+[a-z]{0,2})", e, re.I)
    if m:
        n = m.group(1).lower()
        return "a", n, f"Art. {n}", [], "Art."
    m = re.fullmatch(r"(§§|Art(?:ikel|\.)?)\s*(\d+[a-z]{0,2}(?:\s*(?:bis|und|u\.|,)\s*\d+[a-z]{0,2})+)", e, re.I)
    if m:
        sign = "§" if m.group(1) == "§§" else "Art."
        spec = m.group(2).lower()
        covers = expand_range(spec)
        label = ("§§ " if sign == "§" else "Art. ") + re.sub(r"\s+", " ", spec)
        return "r", covers[0], label, covers, sign
    m = re.fullmatch(r"Art(?:ikel|\.)?\s*(\d+[a-z]{0,2})\s*§\s*(\d+[a-z]{0,2})", e, re.I)
    if m:
        a, p = m.group(1).lower(), m.group(2).lower()
        return "a", f"{a}-{p}", f"Art. {a} § {p}", [], "Art."
    return "x", slugify(e) or "norm", e, [], ""


# ---------------------------------------------------------------- Gesetz parsen

ENTITY = re.compile(rb"&([A-Za-z][A-Za-z0-9]*);")


def _fix_entities(data: bytes) -> bytes:
    def rep(m):
        name = m.group(1).decode()
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return m.group(0)
        ch = html.unescape(f"&{name};")
        return ch.encode() if ch != f"&{name};" else b"&amp;" + m.group(1) + b";"
    return ENTITY.sub(rep, data)


def read_zip(path) -> tuple[bytes, dict]:
    with zipfile.ZipFile(path) as z:
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xmls:
            raise ValueError("keine XML-Datei im Archiv")
        data = z.read(sorted(xmls, key=lambda n: -z.getinfo(n).file_size)[0])
        images = {n.rsplit("/", 1)[-1]: z.read(n) for n in z.namelist()
                  if re.search(r"\.(jpe?g|png|gif)$", n, re.I)}
    return data, images


def parse_law(slug: str, data: bytes, images: dict | None = None) -> Law:
    images = images or {}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        root = ET.fromstring(_fix_entities(data))
    builder = Builder(set(images))
    norms_el = root.findall("norm")
    if not norms_el:
        raise ValueError("keine Normen gefunden")
    meta = norms_el[0].find("metadaten")
    jurabk = [clean(j.text) for j in meta.findall("jurabk") if clean(j.text)]
    amtabk = clean(meta.findtext("amtabk"))
    law = Law(
        slug=slug,
        abk=amtabk or (jurabk[0] if jurabk else slug.upper()),
        jurabk=jurabk,
        title=clean(meta.findtext("langue")) or clean(meta.findtext("kurzue")) or slug,
        short=clean(meta.findtext("kurzue")),
        stand=[(clean(s.findtext("standtyp")), clean(s.findtext("standkommentar")))
               for s in meta.findall("standangabe")],
        date=clean(meta.findtext("ausfertigung-datum")),
        builddate=root.get("builddate", ""),
        notes=[], units=[], norms=[],
    )
    used_images: set[str] = set()
    ids: dict[str, int] = {}
    gii_seen: set[str] = set()
    cur_unit = -1
    for i, nel in enumerate(norms_el):
        md = nel.find("metadaten")
        td = nel.find("textdaten")
        text_el = td.find("text") if td is not None else None
        content = text_el.find("Content") if text_el is not None else None
        notes = _notes(td)
        enbez = clean(md.findtext("enbez")) if md is not None else ""
        gl = md.find("gliederungseinheit") if md is not None else None
        if i == 0 and not enbez and gl is None:
            law.notes = notes
            continue
        if gl is not None and enbez:
            # Norm innerhalb eines Artikels (EGBGB: „Art 229“ + „§ 6“ = Art. 229 § 6)
            am = re.fullmatch(r"Art(?:ikel|\.)?\s*(\d+[a-z]{0,2})", clean(gl.findtext("gliederungsbez")), re.I)
            if am and enbez.startswith("§"):
                enbez = f"Art {am.group(1)} {enbez}"
            gl = None
        if gl is not None:
            bez = clean(gl.findtext("gliederungsbez"))
            nxt = norms_el[i + 1].find("metadaten") if i + 1 < len(norms_el) else None
            has_children = nxt is not None and nxt.find("enbez") is not None and \
                clean(nxt.findtext("gliederungseinheit/gliederungsbez")) == bez
            if (re.fullmatch(r"(?:Art(?:ikel|\.)?|§)\s*\d+[a-z]{0,2}", bez, re.I)
                    and content is not None and plain(content) and not has_children):
                # Gliederungseinheit, die selbst Normtext trägt (EGBGB: „Art 1“) → Norm
                enbez = bez
                md_title = plain(gl.find("gliederungstitel"))
                gl = None
            else:
                md_title = None
        else:
            md_title = None
        if gl is not None:
            kz = clean(gl.findtext("gliederungskennzahl"))
            depth = max(1, len(kz) // 3) if kz.isdigit() else 1
            label = clean(gl.findtext("gliederungsbez"))
            title = plain(gl.find("gliederungstitel"))
            law.units.append(Unit(depth, label, title, len(law.norms)))
            cur_unit = len(law.units) - 1
            continue
        title = md_title if md_title is not None else (plain(md.find("titel")) if md is not None else "")
        if title in ("(keine Überschrift)", "-"):
            title = ""
        if not enbez:
            if not title and content is None:
                continue
            enbez = title or "Text"
        if enbez in ("Inhaltsübersicht", "Inhaltsverzeichnis") or (
                text_el is not None and text_el.find("TOC") is not None):
            continue
        kind, nid, label, covers, sign = describe(enbez)
        if not label:
            label = title or "Text"
            nid = slugify(label) or "text"
        if title and re.match(r"^\(?XXXX\)?$", title):
            title = ""
        blocks = builder.blocks(content) if content is not None else []
        absaetze = split_absaetze(blocks)
        head_fns = []
        # Absatz, der nur aus einem Fußnotenzeichen besteht → an die Überschrift
        if absaetze and not absaetze[0].label and all(
                isinstance(b, Para) and all(r[0] == "f" or (r[0] == "t" and not r[1].strip()) or r == ("v", "<br>")
                                            for r in b.runs) for b in absaetze[0].blocks):
            head_fns = [r[1] for b in absaetze[0].blocks for r in b.runs if r[0] == "f"]
            absaetze = absaetze[1:]
        fns = []
        if text_el is not None:
            for fn in text_el.iter("Footnote"):
                runs: list = []
                builder.inline_children(fn, runs)
                fns.append(Footnote(fn.get("ID", ""), fn.get("FnZ", "*"), trim(runs)))
        body_text = " ".join(runs_text(p.runs) for a in absaetze for p in a.blocks if isinstance(p, Para))
        gone = (not absaetze and not fns) or bool(GONE_TEXT.match(body_text.strip())) or bool(
            re.fullmatch(r"\(?weggefallen\)?", title or "", re.I))
        if gone and re.fullmatch(r"\(?weggefallen\)?", title or "", re.I):
            title = ""
        # Kennung eindeutig machen (z. B. mehrfach vorkommende Anlagen)
        base = nid
        k = 2
        while nid in ids:
            nid = f"{base}-{k}"
            k += 1
        gname = gii_name(enbez if kind != "x" or md.findtext("enbez") else "") if kind != "r" else ""
        if gname in gii_seen:
            gname = ""
        gii_seen.add(gname)
        norm = Norm(enbez=enbez, kind=kind, id=nid, label=label, title=title, unit=cur_unit,
                    absaetze=absaetze, footnotes=fns, notes=notes, covers=covers, gone=gone,
                    gii=gname, sign=sign, head_fns=head_fns)
        ids[nid] = len(law.norms)
        law.norms.append(norm)
        _collect_images(absaetze, used_images)
        for fn in fns:
            used_images.update(r[1].src for r in fn.runs if r[0] == "i")
    law.images = {k: v for k, v in images.items() if k in used_images}
    arts = sum(1 for n in law.norms if n.kind == "a")
    paras = sum(1 for n in law.norms if n.kind == "p")
    law.sign = "Art." if arts > paras else "§"
    return law


def _notes(td) -> list[str]:
    if td is None:
        return []
    fn = td.find("fussnoten")
    if fn is None:
        return []
    out = []
    for p in fn.iter("P"):
        t = pre_text(p) if p.find("pre") is not None else plain(p)
        t = clean(t.replace("\n", " "))
        if t:
            out.append(t)
    if not out:
        t = plain(fn)
        if t:
            out.append(t)
    return out


def _collect_images(blocks, acc: set):
    for b in blocks:
        if isinstance(b, Absatz):
            _collect_images(b.blocks, acc)
        elif isinstance(b, Img):
            acc.add(b.src)
        elif isinstance(b, (Para, Heading)):
            acc.update(r[1].src for r in b.runs if r[0] == "i")
        elif isinstance(b, ListBlock):
            for it in b.items:
                _collect_images(it.blocks, acc)
        elif isinstance(b, Table):
            for row in b.rows:
                for c in row:
                    _collect_images(c.blocks, acc)


def load(path, slug: str | None = None) -> Law:
    from pathlib import Path
    p = Path(path)
    data, images = read_zip(p)
    return parse_law(slug or p.stem, data, images)
