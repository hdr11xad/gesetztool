"""Gesetzesregister: Kürzel, Namen, URL-Kennungen und Normbestand aller Gesetze.

Das Register wird aus einer ersten Lesung aller Archive aufgebaut und dient
  * der Vergabe sprechender URL-Kennungen (/normfinder/bgb/573),
  * der Verweiserkennung (Kürzel nach der Norm, Gesetzesname im Genitiv),
  * dem Suchindex im Browser (laws.json).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .gii import Law, slugify

DATA = Path(__file__).resolve().parent.parent / "data"
RESERVED = {"suche", "assets", "data", "gesetze", "img", "404", "landesrecht", "index", "sitemap"}


@dataclass
class LawInfo:
    slug: str                  # Kennung auf gesetze-im-internet.de
    url: str = ""              # Kennung im Normfinder
    abk: str = ""
    jurabk: list = field(default_factory=list)
    title: str = ""
    short: str = ""
    sign: str = "§"
    ids: set = field(default_factory=set)       # alle aufrufbaren Normkennungen
    count: int = 0
    stand: str = ""
    builddate: str = ""
    aliases: list = field(default_factory=list)  # aus data/aliases.json
    core: str = ""             # Gruppe, falls Kerngesetz

    @property
    def names(self) -> list[str]:
        out = []
        for n in [self.short, self.title, *[a for a in self.aliases if not is_abbrev(a)]]:
            if not n:
                continue
            out.append(n)
            # „Gesetz über … (Kurzname - Kürzel)“: Klammerinhalt als eigener Name
            m = re.search(r"\(([^()]+)\)\s*$", n)
            if m:
                inner = re.split(r"\s+[-–]\s+", m.group(1))[0].strip()
                if len(inner) > 4:
                    out.append(inner)
                out.append(n[:m.start()].strip())
        return list(dict.fromkeys(x for x in out if len(x) > 3))

    @property
    def abbrevs(self) -> list[str]:
        out = [self.abk, *self.jurabk] + [a for a in self.aliases if is_abbrev(a)]
        return list(dict.fromkeys(a for a in out if a))


def is_abbrev(s: str) -> bool:
    s = s.strip()
    if re.fullmatch(r"[A-ZÄÖÜ][\wÄÖÜäöü]* (?:[IVX]+|\d{4}|LSA|Bund)", s):
        return True
    return (" " not in s and len(s) <= 12 and sum(c.isupper() for c in s) >= 2
            and not re.search(r"gesetz|ordnung|buch", s, re.I))


def summarize(law: Law) -> LawInfo:
    ids = set()
    for n in law.norms:
        ids.add(n.id)
        ids.update(n.covers)
    stand = next((k for t, k in law.stand if t == "Stand"), "") or (law.stand[0][1] if law.stand else "")
    return LawInfo(slug=law.slug, abk=law.abk, jurabk=law.jurabk, title=law.title, short=law.short,
                   sign=law.sign, ids=ids, count=len(law.norms), stand=stand, builddate=law.builddate)


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Namensabgleich

STEM_SUFFIXES = ("es", "en", "em", "er", "s", "e", "n")


def stem(word: str) -> str:
    w = word.lower().strip(".,;:()„“\"")
    if len(w) > 4:
        for suf in STEM_SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                return w[: -len(suf)]
    return w


def name_tokens(name: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[\wÄÖÜäöüß]+(?:-[\wÄÖÜäöüß]+)*-?", name)]


class Registry:
    def __init__(self, infos: list[LawInfo]):
        aliases = load_json("aliases.json")
        core = load_json("core.json")
        group_of = {s: g["name"] for g in core["gruppen"] for s in g["gesetze"]}
        self.core = core
        self.by_slug: dict[str, LawInfo] = {}
        for info in infos:
            info.aliases = [a for a in aliases.get(info.slug, [])]
            info.core = group_of.get(info.slug, "")
            self.by_slug[info.slug] = info
        self._assign_urls()
        self.by_url = {i.url: i for i in self.by_slug.values()}
        # Kürzel (case-sensitiv für die Verweiserkennung, sonst kleingeschrieben)
        self.abk_exact: dict[str, str] = {}
        self.abk_lower: dict[str, str] = {}
        for info in self._ranked():
            for a in info.abbrevs:
                self.abk_exact.setdefault(a, info.slug)
                self.abk_lower.setdefault(norm_key(a), info.slug)
        # Namens-Trie über Wortstämme (für „§ 1 des Handelsgesetzbuchs“)
        self.trie: dict = {}
        for info in self._ranked():
            for n in info.names:
                toks = name_tokens(n)
                if len(toks) < 1 or (len(toks) == 1 and len(toks[0]) < 6):
                    continue
                node = self.trie
                for t in toks:
                    node = node.setdefault(t, {})
                node.setdefault("$", info.slug)

    def _ranked(self) -> list[LawInfo]:
        """Kerngesetze zuerst, dann Gesetze mit amtlicher Abkürzung, dann nach Umfang."""
        return sorted(self.by_slug.values(), key=lambda i: (not i.core, not i.abk or i.abk == i.slug.upper(), -i.count, i.slug))

    def _assign_urls(self):
        taken: set[str] = set()
        wanted: dict[str, list[LawInfo]] = {}
        for info in self.by_slug.values():
            # Kerngesetze mit abweichender Studienabkürzung (EGBGB, WEG) bekommen diese als URL
            first = info.aliases[0] if info.aliases else ""
            base = slugify(first if info.core and is_abbrev(first) else info.abk) or slugify(info.slug)
            wanted.setdefault(base, []).append(info)
        for base, infos in sorted(wanted.items()):
            infos.sort(key=lambda i: (not i.core, i.slug != base, -i.count, i.slug))
            for k, info in enumerate(infos):
                url = base if k == 0 and base not in RESERVED else slugify(info.slug)
                n = 2
                while url in taken or url in RESERVED:
                    url = f"{slugify(info.slug)}-{n}"
                    n += 1
                info.url = url
                taken.add(url)

    # -- Abfragen ------------------------------------------------------

    def get(self, slug: str) -> LawInfo | None:
        return self.by_slug.get(slug)

    def match_abbrev(self, text: str) -> tuple[str, int] | None:
        """Kürzel am Anfang von text (z. B. „ZPO“, „VVG 2008“, „SGB V“)."""
        m = re.match(r"([A-ZÄÖÜ][\wÄÖÜäöüß\-]*)(?:\s+([IVX]+\b|\d{4}\b|LSA\b))?", text)
        if not m:
            return None
        if m.group(2):
            two = m.group(1) + " " + m.group(2)
            if two in self.abk_exact:
                return self.abk_exact[two], m.end()
        one = m.group(1)
        if one in self.abk_exact and (any(c.isupper() for c in one[1:]) or one in ("Gesetz",) or len(one) <= 5):
            return self.abk_exact[one], m.end(1)
        return None

    def match_name(self, text: str) -> tuple[str, int] | None:
        """Gesetzesname (beliebiger Kasus) am Anfang von text → (slug, Länge)."""
        best = None
        node = self.trie
        last = 0
        for m in WORD.finditer(text):
            if m.start() > 200 or re.search(r"[.;:()]", text[last:m.start()]):
                break
            t = stem(m.group(0))
            if t not in node:
                break
            node = node[t]
            last = m.end()
            if "$" in node:
                best = (node["$"], m.end())
        return best


WORD = re.compile(r"[\wÄÖÜäöüß]+(?:-[\wÄÖÜäöüß]+)*-?")


def norm_key(s: str) -> str:
    return re.sub(r"[\s._\-]+", "", s.lower())
