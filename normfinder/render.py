"""Statische HTML-Seiten des Normfinders.

Jede Norm bekommt eine eigene Seite unter /normfinder/<gesetz>/<norm>, die ohne
JavaScript vollständig lesbar ist. JavaScript ergänzt Suche, Vorschläge,
Kopierknöpfe und Tastatursteuerung.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import gii
from .gii import Absatz, Heading, Img, ListBlock, Para, Pre, Table
from .text import Inline, ends_sentence, esc, split_sentences

SITE = "https://fsr-jura-halle.de"
FSR = "https://fsr-jura-halle.de"
GII = "https://www.gesetze-im-internet.de"
FOOTER_LINKS = [("Kontakt", FSR + "/kontakt/"), ("Impressum", FSR + "/impressum/"),
                ("Datenschutz", FSR + "/datenschutz/")]
LIST_KEY = {"nr": "nr", "lit": "lit", "dlit": "dlit"}


def fmt_date(s: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", s or "")
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else s


class Site:
    def __init__(self, registry, base: str = "/normfinder/", asset_version: str = "1",
                 fetched: str | None = None):
        self.reg = registry
        self.base = base
        self.v = asset_version
        self.fetched = fetched or dt.date.today().strftime("%d.%m.%Y")

    # ------------------------------------------------------------ URLs

    def law_url(self, slug: str) -> str:
        return f"{self.base}{self.reg.get(slug).url}/"

    def norm_url(self, slug: str, nid: str, anchor: str = "") -> str:
        return f"{self.base}{self.reg.get(slug).url}/{nid}" + (f"#{anchor}" if anchor else "")

    def asset(self, name: str) -> str:
        return f"{self.base}assets/{name}?v={self.v}"

    # ------------------------------------------------------------ Rahmen

    def page(self, *, title: str, body: str, canonical: str, description: str = "",
             law: str = "", norm: str = "", search: bool = True, kind: str = "", noindex=False,
             head_extra: str = "") -> str:
        data = f' data-base="{esc(self.base)}"'
        if law:
            info = self.reg.get(law)
            data += f' data-law="{esc(info.url)}" data-abk="{esc(info.abk)}" data-sign="{esc(info.sign)}"'
        if norm:
            data += f' data-norm="{esc(norm)}"'
        if kind:
            data += f' data-page="{kind}"'
        search_html = self.search_form() if search else ""
        robots = '<meta name="robots" content="noindex">' if noindex else ""
        desc = f'<meta name="description" content="{esc(description)}">' if description else ""
        return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{desc}{robots}
<link rel="canonical" href="{esc(SITE + canonical)}">
<link rel="icon" href="{self.asset('icon.svg')}" type="image/svg+xml">
<link rel="preload" href="{self.base}assets/fonts/newsreader-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{self.asset('app.css')}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#5e1f27">
<script src="{self.asset('theme.js')}"></script>
<script type="module" src="{self.asset('app.js')}"></script>
{head_extra}</head>
<body{data}>
<a class="skip" href="#main">Zum Inhalt springen</a>
<header class="site-head">
  <div class="head-in">
    <a class="brand" href="{self.base}" aria-label="Normfinder – Startseite"><img src="{self.base}assets/logo.svg" alt="" width="46" height="46"><span class="brand-t"><b>Normfinder</b><small>FSR Jura Halle</small></span></a>
    {search_html}
    <nav class="head-nav" aria-label="Weitere Seiten"><a class="fsr-link" href="{FSR}/">Zur FSR-Website</a><button class="theme-btn" type="button" hidden aria-label="Farbschema wechseln" title="Hell/Dunkel"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z" fill="currentColor"/></svg></button></nav>
  </div>
</header>
<main id="main" tabindex="-1">
{body}
</main>
{self.footer()}
</body>
</html>
"""

    def search_form(self, big: bool = False, autofocus: bool = False) -> str:
        cls = "search big" if big else "search"
        ident = "q-big" if big else "q"
        af = " autofocus" if autofocus else ""
        return f"""<form class="{cls}" role="search" action="{self.base}suche/" method="get" autocomplete="off">
      <label class="vh" for="{ident}">Norm oder Suchbegriff</label>
      <input id="{ident}" name="q" type="search" spellcheck="false" autocapitalize="off" enterkeyhint="go"{af}
        role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="{ident}-sugg"
        placeholder="573 bgb · art 1 gg · kündigung vermieter">
      <kbd class="hint" aria-hidden="true">/</kbd>
      <button class="go" type="submit" aria-label="Suchen"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.96 12.05l4.25 4.24-1.42 1.42-4.24-4.25A7.5 7.5 0 1 1 10.5 3zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z" fill="currentColor"/></svg></button>
      <div class="sugg" id="{ident}-sugg" role="listbox" aria-label="Vorschläge" hidden></div>
    </form>"""

    def footer(self) -> str:
        links = "".join(f'<a href="{u}">{t}</a>' for t, u in FOOTER_LINKS)
        return f"""<footer class="site-foot">
  <div class="foot-in">
    <div class="foot-text">
      <p class="disclaimer"><strong>Keine Rechtsberatung.</strong> Maßgeblich ist die amtliche Fassung.</p>
      <p>Quelle: Bundesministerium der Justiz, <a href="{GII}/">gesetze-im-internet.de</a>. Gesetzestexte sind amtliche Werke (§ 5 UrhG). Daten abgerufen am {self.fetched}.</p>
      <p>Ohne Cookies, Tracking und Werbung · <a href="{self.base}hinweise/">Über den Normfinder</a></p>
      <p class="copy">© {dt.date.today().year} Fachschaftsrat Jura der Martin-Luther-Universität Halle-Wittenberg</p>
    </div>
    <nav class="foot-links" aria-label="Rechtliches">{links}</nav>
  </div>
</footer>"""

    # ------------------------------------------------------------ Normtext

    def render_norm_body(self, law: gii.Law, norm: gii.Norm, linker, img_base: str) -> str:
        if norm.gone and not any(a.blocks for a in norm.absaetze):
            what = "Diese Vorschriften sind" if norm.kind == "r" else "Diese Vorschrift ist"
            return f'<p class="gone">{what} weggefallen.</p>'
        ctx = RenderCtx(self, law, norm, linker, img_base)
        return "".join(ctx.absatz(a) for a in norm.absaetze)

    # ------------------------------------------------------------ Seiten

    def unit_path(self, law: gii.Law, idx: int) -> list[int]:
        out = []
        depth = 99
        for i in range(idx, -1, -1):
            u = law.units[i]
            if u.depth < depth:
                out.insert(0, i)
                depth = u.depth
                if depth <= 1:
                    break
        return out

    def norm_page(self, law: gii.Law, k: int, linker, img_base: str) -> str:
        info = self.reg.get(law.slug)
        n = law.norms[k]
        lu = self.law_url(law.slug)
        path = self.unit_path(law, n.unit) if n.unit >= 0 else []
        crumbs = f'<a href="{lu}">{esc(info.abk)}</a>' + "".join(
            f'<a href="{lu}#g-{i}" title="{esc(law.units[i].title)}">{esc(law.units[i].label or law.units[i].title)}</a>'
            for i in path)
        sign_html = esc(n.label)
        m = re.match(r"^(§§|§|Art\.)\s*(.*)$", n.label)
        if m:
            sign_html = f'<i>{esc(m.group(1))}</i>&#8239;{esc(m.group(2))}'
        title = n.title or ("(weggefallen)" if n.gone else "")
        official = f"{GII}/{law.slug}/{n.gii}.html" if n.gii else f"{GII}/{law.slug}/index.html"
        body = self.render_norm_body(law, n, linker, img_base)
        fns = ""
        if n.footnotes:
            ctx = RenderCtx(self, law, n, linker, img_base)
            items = "".join(
                f'<li id="fn-{esc(f.id)}"><span class="fn-m">{esc(f.mark)})</span> {ctx.inline(f.runs)}</li>'
                for f in n.footnotes)
            fns = f'<section class="footnotes" aria-label="Fußnoten"><ol>{items}</ol></section>'
        notes = ""
        if n.notes:
            notes = '<details class="notes"><summary>Hinweise zur Textfassung</summary>' + "".join(
                f"<p>{esc(t)}</p>" for t in n.notes) + "</details>"
        prev = law.norms[k - 1] if k > 0 else None
        nxt = law.norms[k + 1] if k + 1 < len(law.norms) else None

        def pg(x, cls, label, rel):
            if not x:
                return '<span class="spacer"></span>'
            return (f'<a class="{cls}" rel="{rel}" href="{self.norm_url(law.slug, x.id)}"><small>{label}</small>'
                    f'<span>{esc(x.label)}</span><em>{esc(x.title)}</em></a>')

        stand = esc(info.stand) if info.stand else ""
        cite = f"{n.label} {info.abk}"
        rail = self.rail(law, k)
        desc = f"{n.label} {info.abk} – {title}. " if title else f"{n.label} {info.abk}. "
        desc += plain_preview(n)
        page_title = f"{n.label} {info.abk}" + (f" – {title}" if title else "") + " | Normfinder"
        main = f"""<div class="layout">
  {rail}
  <article class="norm" aria-labelledby="norm-h">
    <nav class="crumbs" aria-label="Fundstelle im Gesetz">{crumbs}</nav>
    <header class="norm-head">
      <h1 id="norm-h"><span class="num">{sign_html} <abbr title="{esc(law.title)}">{esc(info.abk)}</abbr></span><span class="tt">{esc(title)}{"".join(f'<sup class="fnr"><a href="#fn-{esc(f)}" aria-label="Fußnote">*</a></sup>' for f in n.head_fns)}</span></h1>
    </header>
    <div class="tools" data-cite="{esc(cite)}">
      <button class="btn js-only" type="button" data-copy="cite"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M8 3h9a2 2 0 0 1 2 2v12h-2V5H8zm-3 4h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zm0 2v10h9V9z" fill="currentColor"/></svg>Zitat kopieren <code>{esc(cite)}</code></button>
      <button class="btn js-only" type="button" data-copy="link"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M10.6 13.4a1 1 0 0 1 0-1.4l3-3a1 1 0 1 1 1.4 1.4l-3 3a1 1 0 0 1-1.4 0zM7.8 19.1a3.9 3.9 0 0 1-2.9-6.7l2.5-2.5 1.4 1.4-2.5 2.5a1.9 1.9 0 0 0 2.7 2.7l2.5-2.5 1.4 1.4-2.5 2.5a3.9 3.9 0 0 1-2.6 1.2zm8.8-5-1.4-1.4 2.5-2.5a1.9 1.9 0 0 0-2.7-2.7l-2.5 2.5-1.4-1.4 2.5-2.5a3.9 3.9 0 0 1 5.5 5.5z" fill="currentColor"/></svg>Link kopieren</button>
      <a class="btn" href="{official}" rel="noopener">Amtliche Fassung<span class="vh"> auf gesetze-im-internet.de</span> <span aria-hidden="true">↗</span></a>
    </div>
    <div class="lawtext">
{body}
    </div>
    {fns}{notes}
    <p class="stand">{stand + " · " if stand else ""}Fassung von gesetze-im-internet.de vom {fmt_date(law.builddate)} · <a href="{official}" rel="noopener">amtliche Fassung</a></p>
    <nav class="pager" aria-label="Blättern">{pg(prev, "prev", "Vorherige Norm", "prev")}{pg(nxt, "next", "Nächste Norm", "next")}</nav>
  </article>
</div>"""
        return self.page(title=page_title, body=main, canonical=self.norm_url(law.slug, n.id),
                         description=desc[:300], law=law.slug, norm=n.id, kind="norm")

    def rail(self, law: gii.Law, k: int) -> str:
        n = law.norms[k]
        lu = self.law_url(law.slug)
        path = self.unit_path(law, n.unit) if n.unit >= 0 else []
        path_html = "".join(
            f'<a href="{lu}#g-{i}"><b>{esc(law.units[i].label)}</b>{esc(law.units[i].title)}</a>' for i in path)
        by_unit = getattr(law, "_by_unit", None)
        if by_unit is None:
            by_unit = {}
            for j, x in enumerate(law.norms):
                by_unit.setdefault(x.unit, []).append(j)
            law._by_unit = by_unit
        sib = by_unit[n.unit]
        pos = sib.index(k)
        lo, hi = max(0, pos - 12), min(len(sib), pos + 13)
        items = []
        if lo > 0:
            items.append(f'<li class="more"><a href="{lu}#g-{n.unit}" aria-label="Weitere Normen in der Gliederung">…</a></li>')
        for j in sib[lo:hi]:
            x = law.norms[j]
            cur = ' aria-current="page"' if j == k else ""
            cls = ' class="gone-l"' if x.gone else ""
            items.append(f'<li><a href="{self.norm_url(law.slug, x.id)}"{cur}{cls}><span>{esc(x.label)}</span><span>{esc(x.title)}</span></a></li>')
        if hi < len(sib):
            items.append(f'<li class="more"><a href="{lu}#g-{n.unit}" aria-label="Weitere Normen in der Gliederung">…</a></li>')
        return (f'<aside class="rail" aria-label="Gliederung"><h2>Gliederung</h2>'
                f'<div class="path">{path_html}</div><ol>{"".join(items)}</ol>'
                f'<a class="all" href="{lu}">Gesamte Gliederung des {esc(self.reg.get(law.slug).abk)}</a></aside>')

    def toc_page(self, law: gii.Law) -> str:
        info = self.reg.get(law.slug)
        lu = self.law_url(law.slug)
        by_unit: dict[int, list] = {}
        for j, x in enumerate(law.norms):
            by_unit.setdefault(x.unit, []).append(j)
        open_all = len(law.norms) <= 120

        def norm_list(js):
            if not js:
                return ""
            return "<ol>" + "".join(
                f'<li><a href="{self.norm_url(law.slug, law.norms[j].id)}"{" class=\"gone-l\"" if law.norms[j].gone else ""}>'
                f'<span>{esc(law.norms[j].label)}</span><span>{esc(law.norms[j].title or ("(weggefallen)" if law.norms[j].gone else ""))}</span></a></li>'
                for j in js) + "</ol>"

        parts = [norm_list(by_unit.get(-1, []))]
        stack: list[int] = []
        for i, u in enumerate(law.units):
            while stack and stack[-1] >= u.depth:
                parts.append("</div></details>")
                stack.pop()
            op = " open" if open_all else ""
            parts.append(f'<details id="g-{i}"{op}><summary><b>{esc(u.label)}</b><span>{esc(u.title)}</span></summary><div class="inner">')
            parts.append(norm_list(by_unit.get(i, [])))
            stack.append(u.depth)
        parts.extend("</div></details>" for _ in stack)
        tree = "".join(parts)
        stand = "".join(f"<li><b>{esc(t)}:</b> {esc(c)}</li>" for t, c in law.stand)
        notes = ""
        if law.notes:
            notes = f'<details class="notes"{" open" if not law.norms else ""}><summary>Hinweise zum Textnachweis</summary>' + "".join(
                f"<p>{esc(t)}</p>" for t in law.notes) + "</details>"
        gone = sum(1 for x in law.norms if x.gone)
        full = law.title if law.title != info.abk else law.short
        tools = "" if len(law.units) < 3 else '<div class="toc-tools js-only"><button class="btn" type="button" data-toc="open">Alle aufklappen</button><button class="btn" type="button" data-toc="close">Alle zuklappen</button></div>'
        main = f"""<section class="toc">
  <nav class="crumbs" aria-label="Pfad"><a href="{self.base}gesetze/">Gesetze</a><a href="{self.base}gesetze/{letter_of(info)}/">{letter_of(info).upper()}</a></nav>
  <h1>{esc(full)} <span class="abk">({esc(info.abk)})</span></h1>
  <p class="sub">{len(law.norms)} Einträge{f", davon {gone} weggefallen" if gone else ""}{" · Ausfertigung " + fmt_date(law.date) if law.date else ""} · <a href="{GII}/{law.slug}/index.html" rel="noopener">Amtliche Fassung ↗</a></p>
  <ul class="standlist">{stand}<li><b>Fassung von gesetze-im-internet.de vom</b> {fmt_date(law.builddate)}</li></ul>
  {notes}
  {tools}
  <div class="tree">{tree}</div>
</section>"""
        return self.page(title=f"{info.abk} – {law.short or law.title} | Normfinder", body=main, canonical=lu,
                         description=f"Gliederung und Normen: {law.title} ({info.abk})", law=law.slug, kind="toc")

    def start_page(self, examples: list[str], landesrecht: dict) -> str:
        groups = []
        for g in self.reg.core["gruppen"]:
            cards = []
            for s in g["gesetze"]:
                info = self.reg.get(s)
                if not info:
                    continue
                cards.append(f'<li><a href="{self.law_url(s)}"><b>{esc(info.abk)}</b><span>{esc(short_name(info))}</span></a></li>')
            groups.append(f'<section class="core-g"><h3>{esc(g["name"])}</h3><ul class="cards">{"".join(cards)}</ul></section>')
        lsa = "".join(
            f'<li><a href="{esc(landesrecht["url"])}" rel="noopener"><b>{esc(x["abk"])}</b><span>{esc(x["name"])}</span><span class="ext" aria-hidden="true">↗</span></a></li>'
            for x in landesrecht["gesetze"])
        chips = "".join(f'<li><a class="chip" href="{self.base}suche/?q={esc(e.replace(" ", "+"))}" data-q="{esc(e)}">{esc(e)}</a></li>' for e in examples)
        count = len(self.reg.by_slug)
        main = f"""<section class="hero">
  <div class="hero-in">
    <h1>Norm eintippen, <em>Enter</em>, fertig.</h1>
    <p class="lede">Alle {count:,} Bundesgesetze und -verordnungen, so schnell aufgerufen, wie man im Gutachten zitiert. Der Normfinder springt direkt an die richtige Stelle und markiert Absatz, Satz oder Nummer.</p>
    {self.search_form(big=True, autofocus=True)}
    <ul class="chips" aria-label="Beispiele">{chips}</ul>
  </div>
</section>
<div class="wrap start">
  <div class="cols">
    <section class="core" aria-labelledby="core-h">
      <h2 id="core-h">Kerngesetze</h2>
      {"".join(groups)}
      <section class="core-g"><h3>{esc(landesrecht["name"])}</h3>
        <p class="note-s">{esc(landesrecht["hinweis"])}</p>
        <ul class="cards ext-cards">{lsa}</ul></section>
      <p class="all-laws"><a class="btn" href="{self.base}gesetze/">Alle Gesetze von A bis Z</a></p>
    </section>
    <section class="cheat" aria-labelledby="cheat-h">
      <h2 id="cheat-h">Was die Suche versteht</h2>
      <table><tbody>
        <tr><th scope="row"><code>573 bgb</code></th><td>Reihenfolge und Schreibweise egal: auch „bgb 573“, „§573 BGB“, „p 573 bgb“, „573bgb“</td></tr>
        <tr><th scope="row"><code>art 1 gg</code></th><td>Paragraf oder Artikel wählt der Normfinder je nach Gesetz selbst: „gg 1“ reicht</td></tr>
        <tr><th scope="row"><code>573 II 1 bgb</code></th><td>Römische Zahl = Absatz, danach Satz</td></tr>
        <tr><th scope="row"><code>§ 573 Abs. 2 Nr. 1 BGB</code></th><td>Springt zur Nummer und markiert sie, ebenso „lit. a“ und „S. 2“</td></tr>
        <tr><th scope="row"><code>§§ 433 ff. BGB</code></th><td>Öffnet die erste Norm der Reihe</td></tr>
        <tr><th scope="row"><code>grundgesetz 1</code></th><td>Gesetzesname statt Abkürzung, kleine Tippfehler inklusive</td></tr>
        <tr><th scope="row"><code>bgb</code></th><td>Gliederung des Gesetzes</td></tr>
        <tr><th scope="row"><code>573</code></th><td>Auf einer Normseite: Norm im selben Gesetz. Sonst: Auswahl aus den Kerngesetzen</td></tr>
        <tr><th scope="row"><code>kündigung vermieter</code></th><td>Alles andere: Volltextsuche in den Normtexten</td></tr>
      </tbody></table>
      <h2 class="keys-h">Tastatur</h2>
      <table class="keys"><tbody>
        <tr><th scope="row"><kbd>/</kbd></th><td>Suchfeld öffnen</td></tr>
        <tr><th scope="row"><kbd>↑</kbd> <kbd>↓</kbd> <kbd>Enter</kbd></th><td>Vorschlag wählen und öffnen</td></tr>
        <tr><th scope="row"><kbd>Esc</kbd></th><td>Vorschläge schließen</td></tr>
        <tr><th scope="row"><kbd>←</kbd> <kbd>→</kbd></th><td>Vorherige oder nächste Norm</td></tr>
      </tbody></table>
    </section>
  </div>
</div>"""
        return self.page(title="Normfinder – Gesetze schnell nachschlagen | FSR Jura Halle", body=main,
                         canonical=self.base, search=False, kind="start",
                         description="Bundesgesetze schnell nachschlagen: „573 bgb“ eingeben und direkt bei § 573 BGB landen. Ein offenes, werbefreies Werkzeug des Fachschaftsrats Jura Halle.")

    def search_page(self) -> str:
        main = """<section class="res" id="results" aria-live="polite">
  <h1>Suche</h1>
  <noscript><p class="msg">Die Suche läuft vollständig in deinem Browser und braucht dafür JavaScript. Ohne JavaScript findest du jedes Gesetz über die <a href="../gesetze/">Liste von A bis Z</a>.</p></noscript>
</section>"""
        return self.page(title="Suche | Normfinder", body=f'<div class="wrap">{main}</div>',
                         canonical=self.base + "suche/", kind="search", noindex=True)

    def letters(self) -> dict[str, list]:
        out: dict[str, list] = {}
        for info in self.reg.by_slug.values():
            out.setdefault(letter_of(info), []).append(info)
        for v in out.values():
            v.sort(key=lambda i: (i.abk.lower(), i.title))
        return dict(sorted(out.items()))

    def az_page(self, letter: str | None) -> str:
        letters = self.letters()
        nav = "".join(
            f'<a href="{self.base}gesetze/{l}/"{" aria-current=\"page\"" if l == letter else ""}>{l.upper() if l != "0" else "0–9"}</a>'
            for l in letters)
        if letter is None:
            body = f"""<section class="az"><h1>Alle Gesetze und Verordnungen</h1>
<p class="sub">{len(self.reg.by_slug):,} Bundesgesetze und -verordnungen von gesetze-im-internet.de, sortiert nach Abkürzung.</p>
<nav class="letters" aria-label="Anfangsbuchstabe">{nav}</nav></section>"""
            return self.page(title="Alle Gesetze A–Z | Normfinder", body=f'<div class="wrap">{body}</div>',
                             canonical=self.base + "gesetze/", kind="az",
                             description="Alle Bundesgesetze und -verordnungen von A bis Z")
        items = "".join(
            f'<li><a href="{self.law_url(i.slug)}"><b>{esc(i.abk)}</b><span>{esc(i.title)}</span></a></li>'
            for i in letters[letter])
        lab = letter.upper() if letter != "0" else "0–9"
        body = f"""<section class="az"><nav class="crumbs" aria-label="Pfad"><a href="{self.base}gesetze/">Gesetze</a></nav>
<h1>Gesetze mit {lab}</h1>
<nav class="letters" aria-label="Anfangsbuchstabe">{nav}</nav>
<ul class="lawlist">{items}</ul></section>"""
        return self.page(title=f"Gesetze {lab} | Normfinder", body=f'<div class="wrap">{body}</div>',
                         canonical=f"{self.base}gesetze/{letter}/", kind="az",
                         description=f"Bundesgesetze und -verordnungen mit {lab}")

    def info_page(self) -> str:
        body = f"""<article class="prose">
<h1>Über den Normfinder</h1>
<p>Der Normfinder ist ein offenes, werbefreies Werkzeug des Fachschaftsrats Jura der Martin-Luther-Universität Halle-Wittenberg. Er zeigt alle Bundesgesetze und Rechtsverordnungen, die das Bundesministerium der Justiz auf <a href="{GII}/">gesetze-im-internet.de</a> veröffentlicht.</p>
<h2>Keine Rechtsberatung</h2>
<p>Der Normfinder ersetzt keine Rechtsberatung. Maßgeblich ist allein die amtliche Fassung. Die Texte werden jede Nacht automatisch aktualisiert; auf jeder Normseite stehen der Datenstand und ein Link zur amtlichen Fassung.</p>
<h2>Quelle und Rechte</h2>
<p>Quelle der Gesetzestexte: Bundesministerium der Justiz, gesetze-im-internet.de. Gesetze und Verordnungen sind amtliche Werke und genießen keinen urheberrechtlichen Schutz (§ 5 Abs. 1 UrhG). Landesrecht aus Sachsen-Anhalt ist nicht enthalten; der Normfinder verlinkt dafür auf das <a href="https://www.landesrecht.sachsen-anhalt.de/">Landesrechtsportal</a>.</p>
<h2>Datenschutz</h2>
<p>Der Normfinder setzt keine Cookies, verwendet kein Tracking und keine Analysewerkzeuge und lädt nichts von fremden Servern. Die Suche läuft vollständig in deinem Browser: Suchanfragen werden nicht an den Server übertragen. Der Server lädt nur die Gesetzesdaten, die für die Anzeige gebraucht werden. Gespeichert wird lokal im Browser allenfalls deine Wahl zwischen hellem und dunklem Farbschema. Weitere Informationen in der <a href="{FSR}/datenschutz/">Datenschutzerklärung des FSR</a>.</p>
<h2>Mitmachen</h2>
<p>Fehler gefunden oder eine Abkürzung fehlt? Schreib uns über die <a href="{FSR}/kontakt/">Kontaktseite</a>.</p>
</article>"""
        return self.page(title="Über den Normfinder", body=f'<div class="wrap">{body}</div>',
                         canonical=self.base + "hinweise/", kind="info")

    def not_found_page(self) -> str:
        body = f"""<section class="msg" id="nf"><h1>Diese Seite gibt es nicht</h1>
<p>Vielleicht hilft die Suche oben weiter, etwa mit „573 bgb“ oder „art 1 gg“.</p>
<p><a class="btn" href="{self.base}">Zur Startseite des Normfinders</a> <a class="btn" href="{self.base}gesetze/">Alle Gesetze A–Z</a></p></section>"""
        return self.page(title="Nicht gefunden | Normfinder", body=f'<div class="wrap">{body}</div>',
                         canonical=self.base + "404", kind="404", noindex=True)

    def redirect_page(self, target: str) -> str:
        return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Weiterleitung</title>
<meta http-equiv="refresh" content="0; url={esc(target)}"><link rel="canonical" href="{esc(SITE + target)}">
<meta name="robots" content="noindex"></head><body><p>Weiter zu <a href="{esc(target)}">{esc(target)}</a>.</p></body></html>"""

    # ------------------------------------------------------------ Daten für den Browser

    def law_index_json(self, law: gii.Law) -> str:
        info = self.reg.get(law.slug)
        norms = [[n.id, n.label, n.title, n.unit, 1 if n.gone else 0] for n in law.norms]
        alias = {c: n.id for n in law.norms for c in n.covers if c != n.id}
        ids = {n.id for n in law.norms}
        for n in law.norms:  # „Art. 229“ ohne eigenen Text → erster Paragraf darin
            head = n.id.split("-")[0]
            if "-" in n.id and re.fullmatch(r"\d+[a-z]{0,2}", head) and head not in ids:
                alias.setdefault(head, n.id)
        data = {"slug": info.url, "gii": law.slug, "abk": info.abk, "title": law.title, "sign": info.sign,
                "stand": info.stand, "units": [[u.depth, u.label, u.title, u.first] for u in law.units],
                "norms": norms, "alias": alias}
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def letter_of(info) -> str:
    c = (info.abk or info.title or "?")[0].lower()
    c = {"ä": "a", "ö": "o", "ü": "u"}.get(c, c)
    return c if c.isalpha() and c.isascii() else "0"


def short_name(info) -> str:
    if info.short and len(info.short) < 60:
        return info.short
    from .laws import is_abbrev
    for a in info.aliases:
        if not is_abbrev(a):
            return a
    t = re.sub(r"\s*\([^)]*\)\s*$", "", info.title)
    return t if len(t) < 70 else t[:67] + "…"


def plain_preview(n: gii.Norm) -> str:
    for a in n.absaetze:
        for b in a.blocks:
            if isinstance(b, Para):
                t = Inline(b.runs).text
                if t:
                    return t[:220]
    return ""


class RenderCtx:
    """Rendert die Absätze einer Norm mit Satznummern, Ankern und Verweisen."""

    def __init__(self, site: Site, law, norm, linker, img_base):
        self.site = site
        self.law = law
        self.norm = norm
        self.linker = linker
        self.img_base = img_base
        self.ids: set[str] = set()
        self.abs_labels = {a.label for a in norm.absaetze if a.label}

    def uid(self, s: str) -> str:
        if s in self.ids:
            return ""
        self.ids.add(s)
        return s

    def links(self, text: str):
        if not self.linker:
            return []
        return self.linker.find(text, self.law.slug, self.abs_labels)

    def inline(self, runs, sentences=None) -> str:
        inl = Inline(runs, img_url=lambda s: self.img_base + s)
        return inl.render(self.links(inl.text), sentences)

    def absatz(self, a: Absatz) -> str:
        prefix = f"abs-{a.label}-" if a.label else ""
        self.state = {"n": 0, "open": False, "prefix": prefix, "max": 0}
        inner = self.blocks(a.blocks, depth=0, prefix=prefix)
        multi = self.state["max"] > 1
        if not multi:
            inner = re.sub(r'<sup class="sn"[^>]*>\d+[a-z]?</sup>', "", inner)
        aid = self.uid(f"abs-{a.label}") if a.label else ""
        idattr = f' id="{aid}"' if aid else ""
        label = f'<span class="al">({esc(a.label)})</span>' if a.label else '<span class="al"></span>'
        return f'<div class="abs"{idattr} data-a="{esc(a.label)}">{label}<div class="ab">{inner}</div></div>\n'

    def blocks(self, blocks, depth: int, prefix: str) -> str:
        out = []
        for b in blocks:
            if isinstance(b, Para):
                if depth == 0:
                    out.append(self.para_sentences(b))
                else:
                    out.append(f"<p>{self.inline(b.runs)}</p>")
                    self.state["open"] = not ends_sentence(Inline(b.runs).text)
            elif isinstance(b, ListBlock):
                out.append(self.list(b, depth, prefix))
            elif isinstance(b, Table):
                out.append(self.table(b))
            elif isinstance(b, Pre):
                out.append(f'<pre class="pre">{esc(b.text)}</pre>')
            elif isinstance(b, Img):
                wh = f' width="{b.width}" height="{b.height}"' if b.width and b.height else ""
                out.append(f'<figure class="img"><img src="{esc(self.img_base + b.src)}" alt="{esc(b.alt)}"{wh} loading="lazy"></figure>')
            elif isinstance(b, Heading):
                out.append(f'<p class="h">{self.inline(b.runs)}</p>')
        return "".join(out)

    def para_sentences(self, b: Para) -> str:
        inl = Inline(b.runs, img_url=lambda s: self.img_base + s)
        text = inl.text
        st = self.state
        official = inl.official_sentences()
        if official:
            starts = [(p, n) for p, n in official]
            if starts[0][0] > 0 and text[:starts[0][0]].strip():
                starts.insert(0, (0, f'+{st["n"]}' if st["open"] and st["n"] else str(st["n"] + 1)))
        else:
            offs = split_sentences(text) if text else [0]
            starts = []
            for j, p in enumerate(offs):
                if j == 0 and st["open"] and st["n"] > 0:
                    starts.append((p, "+" + str(st["n"])))
                else:
                    starts.append((p, str(st["n"] + 1)))
                    st["n"] += 1
        sents = []
        for p, num in starts:
            if num.startswith("+"):  # Fortsetzung eines Satzes nach einer Aufzählung
                num = num[1:]
                sents.append((p, f'<span class="sz" data-s="{esc(num)}">'))
                continue
            try:
                st["n"] = max(st["n"], int(re.match(r"\d+", num).group()))
            except (AttributeError, ValueError):
                pass
            sid = self.uid(f'{st["prefix"]}satz-{num}')
            idattr = f' id="{sid}"' if sid else ""
            sents.append((p, f'<span class="sz"{idattr} data-s="{esc(num)}"><sup class="sn" aria-hidden="true">{esc(num)}</sup>'))
        st["max"] = max(st["max"], st["n"])
        st["open"] = not ends_sentence(text)
        return f"<p>{inl.render(self.links(text), sents)}</p>"

    def list(self, b: ListBlock, depth: int, prefix: str) -> str:
        key = LIST_KEY.get(b.kind, "")
        items = []
        for it in b.items:
            iid = ""
            sub_prefix = prefix
            if key and it.key:
                iid = self.uid(f"{prefix}{key}-{it.key}")
                sub_prefix = f"{prefix}{key}-{it.key}-"
            idattr = f' id="{iid}"' if iid else ""
            inner = self.blocks(it.blocks, depth + 1, sub_prefix)
            items.append(f'<li{idattr} data-l="{esc(it.key)}"><span class="il">{esc(it.label)}</span><div>{inner}</div></li>')
        cls = "items" + (" plain" if b.kind == "plain" else "")
        return f'<ol class="{cls}" data-k="{key}">{"".join(items)}</ol>'

    def table(self, t: Table) -> str:
        rows = []
        for r in t.rows:
            cells = []
            for c in r:
                tag = "th" if c.head else "td"
                attrs = ""
                if c.colspan > 1:
                    attrs += f' colspan="{c.colspan}"'
                if c.rowspan > 1:
                    attrs += f' rowspan="{c.rowspan}"'
                if c.align in ("right", "center"):
                    attrs += f' class="a-{c.align}"'
                if c.head:
                    attrs += ' scope="col"'
                inner = "".join(
                    (f"<p>{self.inline(x.runs)}</p>" if isinstance(x, Para) else self.blocks([x], 1, ""))
                    for x in c.blocks)
                cells.append(f"<{tag}{attrs}>{inner}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return f'<div class="tbl" role="region" aria-label="Tabelle" tabindex="0"><table><tbody>{"".join(rows)}</tbody></table></div>'
