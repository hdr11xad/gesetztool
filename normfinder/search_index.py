"""Volltextindex für die Suche im Browser.

Der Index ist ein invertierter Index über alle Normtexte, aufgeteilt in
Teildateien („Shards“) nach Wortanfang. Eine Suche lädt nur die Shards ihrer
Suchwörter, nie das gesamte Bundesrecht.

Dateien unter data/fts/:
  manifest.json  {"v":1, "laws":[[url, abk, docStart], …], "shards":[ersterBegriff, …]}
  <n>.json       {"Begriff": [Δdoc*32+gewicht, …], …}

Gewicht: Häufigkeit im Normtext (max. 15) + 16, wenn der Begriff in der
Überschrift steht. Dokumentnummern sind global fortlaufend; Dokument d gehört
zu dem Gesetz mit dem größten docStart ≤ d, die Norm ist dort an Position
d − docStart (Reihenfolge wie in <gesetz>/index.json).
"""
from __future__ import annotations

import json
import os
import re
from array import array
from collections import Counter, defaultdict
from pathlib import Path

from .gii import Heading, ListBlock, Para, Table
from .text import Inline, fold

STOP = set("""
aber als am an auch auf aus bei bis da dabei damit dann dar darf darüber das dass daß dem den
denen der deren des dessen die dies diese diesem diesen dieser dieses doch dort durch ein eine
einem einen einer eines er es für gegen hat haben hier ihm ihn ihr ihre ihrem ihren ihrer ihres im
in ist jede jedem jeden jeder jedes kann kein keine keinem keinen keiner können man mit muss müssen
nach nicht noch nur ob oder ohne sein seine seinem seinen seiner seines sich sie sind so soll sollen
soweit sofern sowie über um und uns unter vom von vor war wenn werden wer wie wird wo zu zum zur
zwar abs absatz absatzes nr nummer satz satzes buchstabe buchst gemäß gem vgl bzw sinne
""".split())
STOP = {fold(w) for w in STOP}
TOKEN = re.compile(r"[a-z0-9äöüß]+")
MAX_SHARD = 180_000   # Zeichen JSON je Shard (ungefähr)


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(fold(text)):
        if len(t) < 2 or t in STOP or t.isdigit():
            continue
        out.append(t)
    return out


def norm_text(norm) -> str:
    parts: list[str] = []

    def walk(blocks):
        for b in blocks:
            if isinstance(b, (Para, Heading)):
                parts.append(Inline(b.runs).text)
            elif isinstance(b, ListBlock):
                for it in b.items:
                    walk(it.blocks)
            elif isinstance(b, Table):
                for row in b.rows:
                    for c in row:
                        walk(c.blocks)
    for a in norm.absaetze:
        walk(a.blocks)
    return " ".join(parts)


def law_postings(law) -> list[dict]:
    """Je Norm: {Begriff: Gewicht}."""
    out = []
    for n in law.norms:
        if n.gone:
            out.append({})
            continue
        tf = Counter(tokens(norm_text(n)))
        title = set(tokens(n.title))
        d = {}
        for t in set(tf) | title:
            d[t] = min(tf.get(t, 0), 15) + (16 if t in title else 0)
        out.append(d)
    return out


class IndexWriter:
    """Sammelt Postings je Gesetz und schreibt am Ende die Shards."""

    def __init__(self, tmpdir: Path):
        self.tmp = tmpdir
        self.tmp.mkdir(parents=True, exist_ok=True)

    def write_law(self, key: str, postings: list[dict]):
        """Zwischenergebnis eines Gesetzes (läuft im Arbeitsprozess)."""
        with open(self.tmp / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(postings, f, ensure_ascii=False, separators=(",", ":"))

    def finish(self, laws: list[tuple[str, str, str]], out: Path) -> dict:
        """laws: [(key, url, abk)] in Ausgabereihenfolge."""
        index: dict[str, array] = defaultdict(lambda: array("q"))
        table = []
        doc = 0
        for key, url, abk in laws:
            path = self.tmp / f"{key}.json"
            postings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            table.append([url, abk, doc])
            for local, d in enumerate(postings):
                for t, w in d.items():
                    index[t].append((doc + local) * 32 + w)
            doc += len(postings)
        out.mkdir(parents=True, exist_ok=True)
        shards: list[str] = []
        cur: dict = {}
        size = 0
        n = 0

        def flush():
            nonlocal cur, size, n
            if cur:
                (out / f"{n}.json").write_text(json.dumps(cur, separators=(",", ":")), encoding="utf-8")
                n += 1
                cur, size = {}, 0

        n_terms = len(index)
        for term in sorted(index):
            vals = sorted(index.pop(term))
            deltas = []
            prev = 0
            for v in vals:
                doc_id, w = divmod(v, 32)
                deltas.append((doc_id - prev) * 32 + w)
                prev = doc_id
            est = len(term) + 4 + sum(len(str(x)) + 1 for x in deltas)
            if cur and size + est > MAX_SHARD:
                flush()
            if not cur:
                shards.append(term)
            cur[term] = deltas
            size += est
        flush()
        manifest = {"v": 1, "docs": doc, "laws": table, "shards": shards}
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                                           encoding="utf-8")
        for p in self.tmp.glob("*.json"):
            os.unlink(p)
        return {"terms": n_terms, "docs": doc, "shards": len(shards)}
