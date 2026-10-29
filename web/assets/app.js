// Normfinder – Bedienung im Browser: Suchfeld mit Vorschlägen, Direktsprung,
// Zielmarkierung, Kopierknöpfe, Tastatursteuerung, Suchseite.
// Alles läuft lokal; Suchanfragen werden nicht an den Server geschickt,
// geladen werden nur statische Gesetzesdaten.

import { parseQuery, buildRegistry, anchorFor, citation, partsFromAnchor, fold, lev } from "./parser.js";
import { FullText, terms as ftTerms } from "./search.js";

const body = document.body;
const BASE = body.dataset.base || "/normfinder/";
const PAGE = body.dataset.page || "";
const CTX_LAW = body.dataset.law || null;
const CTX_ABK = body.dataset.abk || "";
const CTX_NORM = body.dataset.norm || null;

/* ---------------------------------------------------------------- Daten */
const cache = new Map();
function fetchJSON(url) {
  if (!cache.has(url)) {
    cache.set(url, fetch(url, { credentials: "omit" }).then(r => {
      if (!r.ok) throw new Error(r.status + " " + url);
      return r.json();
    }).catch(e => { cache.delete(url); throw e; }));
  }
  return cache.get(url);
}
let REG = null;
const regReady = () => REG ? Promise.resolve(REG) : fetchJSON(BASE + "data/laws.json").then(rows => (REG = buildRegistry(rows)));
const core = () => fetchJSON(BASE + "data/core.json");
const lawIndex = url => fetchJSON(`${BASE}${url}/index.json`);
const FT = new FullText(BASE, fetchJSON);

function resolveId(idx, num) {
  if (!idx || !num) return null;
  const n = String(num).toLowerCase();
  if (idx.norms.some(x => x[0] === n)) return n;
  if (idx.alias && idx.alias[n]) return idx.alias[n];
  return null;
}
const normHref = (url, id, r) => { const a = r ? anchorFor(r) : ""; return `${BASE}${url}/${id}${a ? "#" + a : ""}`; };
const signFor = url => (REG && REG.info.get(url) && REG.info.get(url).sign) || "§";
const abkFor = url => (REG && REG.info.get(url) && REG.info.get(url).abk) || url.toUpperCase();

/* ---------------------------------------------------------------- Hilfen */
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function markTerms(text, ts) {
  if (!ts || !ts.length) return esc(text);
  // gefalteter Text mit Rückverweis auf die Originalposition (ß → ss verlängert)
  let ft = "";
  const pos = [];
  for (let i = 0; i < text.length; i++) { const f = fold(text[i]); for (const c of f) { ft += c; pos.push(i); } }
  pos.push(text.length);
  const ranges = [];
  for (const w of ts) { let p = -1; while ((p = ft.indexOf(w, p + 1)) !== -1) ranges.push([pos[p], pos[p + w.length - 1] + 1]); }
  ranges.sort((a, b) => a[0] - b[0]);
  let out = "", last = 0;
  for (const [a, b] of ranges) { if (a < last) continue; out += esc(text.slice(last, a)) + "<mark>" + esc(text.slice(a, b)) + "</mark>"; last = b; }
  return out + esc(text.slice(last));
}
function labelFor(url, num) {
  const s = signFor(url);
  if (/^\d+[a-z]*-\d/.test(num)) { const [a, p] = num.split("-"); return `Art. ${a} § ${p}`; }
  return (s === "Art." ? "Art. " : "§ ") + num;
}

/* ---------------------------------------------------------------- Navigation */
function goSearchPage(q) { location.href = `${BASE}suche/?q=${encodeURIComponent(q)}`; }

async function go(raw, r) {
  r = r || parseQuery(raw, { registry: await regReady().catch(() => null), contextLaw: CTX_LAW });
  if (r.type === "norm") {
    try {
      const idx = await lawIndex(r.law);
      const id = resolveId(idx, r.num);
      if (id) {
        const href = normHref(r.law, id, r);
        if (r.law === CTX_LAW && id === CTX_NORM) { location.hash = anchorFor(r); highlight(); return; }
        location.href = href;
        return;
      }
    } catch (e) { /* unbekannt → Suchseite erklärt es */ }
    return goSearchPage(raw);
  }
  if (r.type === "law") { location.href = `${BASE}${r.law}/`; return; }
  if (r.type === "empty") return;
  goSearchPage(raw);
}

/* ---------------------------------------------------------------- Vorschläge */
async function suggestionsFor(raw) {
  const reg = await regReady().catch(() => null);
  const r = parseQuery(raw, { registry: reg, contextLaw: CTX_LAW });
  const out = [];
  if (r.type === "norm") {
    const idx = await lawIndex(r.law).catch(() => null);
    const abk = abkFor(r.law);
    const id = resolveId(idx, r.num);
    if (id) {
      const n = idx.norms.find(x => x[0] === id);
      out.push({ k: citation(n[1], abk, r), t: n[2] || "", meta: r.assumed ? `${abk} (aktuelles Gesetz)` : "Enter", href: normHref(r.law, id, r) });
    }
    if (idx) {
      const base = (r.num.match(/^\d+/) || [""])[0];
      idx.norms.filter(n => (n[0].match(/^\d+/) || [""])[0] === base && n[0] !== id).slice(0, 6)
        .forEach(n => out.push({ k: `${n[1]} ${abk}`, t: n[2] || (n[4] ? "(weggefallen)" : ""), href: normHref(r.law, n[0]) }));
    }
    if (!id) out.unshift({ k: `${labelFor(r.law, r.num)} ${abk}`, t: "gibt es nicht – ähnliche Normen anzeigen", act: () => goSearchPage(raw) });
  } else if (r.type === "pick") {
    const c = await core().catch(() => null);
    const num = r.num.toLowerCase();
    const hits = c ? c.norms.filter(n => n[1] === num) : [];
    if (hits.length) out.push({ sec: `${r.art ? "Art." : "§"} ${r.num} in den Kerngesetzen – Gesetz wählen` });
    for (const n of hits.slice(0, 8)) {
      const rr = { ...r, law: n[0] };
      out.push({ k: citation(n[2], abkFor(n[0]), rr), t: n[3], href: normHref(n[0], n[1], rr) });
    }
    if (!hits.length) out.push({ k: r.num, t: "Gesetz dazuschreiben, z. B. „" + r.num + " bgb“", act: () => goSearchPage(raw) });
  } else if (r.type === "law") {
    const info = reg.info.get(r.law);
    out.push({ k: info.abk, t: info.title, meta: "Gliederung", href: `${BASE}${r.law}/` });
  } else if (r.type === "lsa") {
    const c = await core().catch(() => null);
    if (c) {
      const l = c.landesrecht.gesetze.find(x => x.aliase.some(a => a.startsWith(r.key))) || c.landesrecht.gesetze[0];
      out.push({ k: l.abk, t: "Landesrechtsportal Sachsen-Anhalt ↗", href: c.landesrecht.url, ext: true });
    }
  } else if (r.type === "search") {
    // Gesetze, deren Kürzel oder Name passt
    if (reg) {
      const q = fold(raw.trim());
      const laws = [];
      if (q.length >= 2 && !/\s/.test(q)) {
        for (const [url, it] of reg.info) {
          const a = fold(it.abk);
          if (a.startsWith(q)) laws.push([a === q ? 0 : 1, it.core >= 0 ? 0 : 1, a.length, it]);
          if (laws.length > 400) break;
        }
      }
      laws.sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2]);
      for (const [, , , it] of laws.slice(0, 4)) out.push({ k: it.abk, t: it.title, meta: "Gesetz", href: `${BASE}${it.url}/` });
    }
    // Überschriften der Kerngesetze
    const c = await core().catch(() => null);
    const ts = ftTerms(r.q);
    if (c && ts.length) {
      const hits = [];
      for (const n of c.norms) {
        if (r.law && n[0] !== r.law) continue;
        const ft = fold(n[3] || "");
        if (ts.every(t => ft.includes(t))) hits.push(n);
        if (hits.length > 60) break;
      }
      hits.sort((a, b) => (fold(a[3]).startsWith(ts[0]) ? 0 : 1) - (fold(b[3]).startsWith(ts[0]) ? 0 : 1));
      for (const n of hits.slice(0, 6)) out.push({ k: `${n[2]} ${abkFor(n[0])}`, t: n[3], mark: ts, href: normHref(n[0], n[1]) });
    }
    out.push({ k: "Volltext", t: `„${r.q}“${r.law ? " im " + abkFor(r.law) : ""} in den Normtexten suchen`, act: () => goSearchPage(raw), full: true });
  }
  return out;
}

class Box {
  constructor(input) {
    this.input = input;
    input._box = this;
    this.moved = false;
    this.box = document.getElementById(input.getAttribute("aria-controls"));
    this.items = [];
    this.sel = -1;
    this.seq = 0;
    this.timer = null;
    input.addEventListener("input", () => { this.moved = false; clearTimeout(this.timer); this.timer = setTimeout(() => this.open(), 70); });
    input.addEventListener("focus", () => { regReady().catch(() => {}); if (input.value.trim()) this.open(); });
    input.addEventListener("keydown", e => this.key(e));
    input.form.addEventListener("submit", e => { e.preventDefault(); this.enter(); });
    this.box.addEventListener("mousedown", e => {
      const li = e.target.closest("li[data-i]");
      if (li) { e.preventDefault(); this.choose(+li.dataset.i); }
    });
    document.addEventListener("click", e => { if (!e.target.closest(".search")) this.close(); });
  }
  async open() {
    const raw = this.input.value;
    this.moved = false;
    const seq = ++this.seq;
    if (!raw.trim()) return this.close();
    let items;
    try { items = await suggestionsFor(raw); } catch (e) { items = [{ k: "Volltext", t: `„${raw}“ suchen`, act: () => goSearchPage(raw) }]; }
    if (seq !== this.seq || this.input.value !== raw) return;
    this.items = items;
    this.sel = items.findIndex(it => !it.sec);
    if (!items.length) return this.close();
    const id = this.box.id;
    this.box.innerHTML = `<ul>${items.map((it, i) => it.sec
      ? `<li class="sec" role="presentation">${esc(it.sec)}</li>`
      : `<li role="option" id="${id}-${i}" data-i="${i}" aria-selected="${i === this.sel}"><span class="k">${esc(it.k)}</span><span class="t">${it.mark ? markTerms(it.t, it.mark) : esc(it.t)}</span>${it.meta ? `<span class="meta">${esc(it.meta)}</span>` : ""}</li>`).join("")}</ul><div class="foot" aria-hidden="true">↑ ↓ auswählen · Enter öffnen · Esc schließen</div>`;
    this.box.hidden = false;
    this.input.setAttribute("aria-expanded", "true");
    if (this.sel >= 0) this.input.setAttribute("aria-activedescendant", `${id}-${this.sel}`);
  }
  close() {
    this.box.hidden = true;
    this.input.setAttribute("aria-expanded", "false");
    this.input.removeAttribute("aria-activedescendant");
  }
  move(d) {
    if (!this.items.length) return;
    this.moved = true;
    let i = this.sel;
    do { i = (i + d + this.items.length) % this.items.length; } while (this.items[i].sec);
    this.sel = i;
    this.box.querySelectorAll("li[role=option]").forEach(li => li.setAttribute("aria-selected", String(+li.dataset.i === i)));
    this.input.setAttribute("aria-activedescendant", `${this.box.id}-${i}`);
    const li = this.box.querySelector(`li[data-i="${i}"]`);
    if (li) li.scrollIntoView({ block: "nearest" });
  }
  key(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); if (this.box.hidden) this.open(); else this.move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); this.move(-1); }
    else if (e.key === "Escape") { if (!this.box.hidden) { e.preventDefault(); this.close(); } else this.input.blur(); }
  }
  async enter() {
    clearTimeout(this.timer);
    const raw = this.input.value;
    if (!raw.trim()) return;
    // Explizit gewählter Vorschlag (Pfeiltasten) hat Vorrang
    if (!this.box.hidden && this.items.length && this.sel >= 0 && this.moved) return this.choose(this.sel);
    const r = parseQuery(raw, { registry: await regReady().catch(() => null), contextLaw: CTX_LAW });
    if (r.type === "pick") return goSearchPage(raw); // nicht raten: Auswahlseite
    if (r.type === "lsa") return goSearchPage(raw);
    this.close();
    go(raw, r);
  }
  choose(i) {
    const it = this.items[i];
    if (!it || it.sec) return;
    this.close();
    if (it.href) { if (it.ext) window.open(it.href, "_blank", "noopener"); else location.href = it.href; }
    else if (it.act) it.act();
  }
}

/* ---------------------------------------------------------------- Normseite */
function targetEl() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h) return null;
  let el = document.getElementById(h);
  if (!el && /^(satz|nr|lit)-/.test(h)) el = document.querySelector(`.lawtext [id$="-${CSS.escape(h)}"]`);
  return el;
}
function highlight() {
  document.querySelectorAll(".is-target").forEach(x => x.classList.remove("is-target"));
  const el = targetEl();
  if (!el) return;
  el.classList.add("is-target");
  if (el.classList.contains("sz")) {
    const n = el.dataset.s;
    el.closest(".abs")?.querySelectorAll(`.sz[data-s="${CSS.escape(n)}"]`).forEach(s => s.classList.add("is-target"));
  }
  document.body.classList.add("has-target");
  requestAnimationFrame(() => el.scrollIntoView({ block: "center", behavior: "instant" }));
}
function currentParts() { return partsFromAnchor(decodeURIComponent(location.hash.slice(1))); }

function wireCopy() {
  const tools = document.querySelector(".tools[data-cite]");
  if (!tools) return;
  const base = tools.dataset.cite; // „§ 573 BGB“
  const codeEl = tools.querySelector("[data-copy=cite] code");
  const label = base.slice(0, base.length - CTX_ABK.length - 1);
  const update = () => { if (codeEl) codeEl.textContent = citation(label, CTX_ABK, currentParts()); };
  update();
  window.addEventListener("hashchange", update);
  tools.addEventListener("click", e => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const val = btn.dataset.copy === "cite" ? citation(label, CTX_ABK, currentParts())
      : location.origin + location.pathname + location.hash;
    const done = () => {
      const old = btn.innerHTML;
      btn.classList.add("ok");
      btn.textContent = "Kopiert ✓";
      setTimeout(() => { btn.classList.remove("ok"); btn.innerHTML = old; }, 1400);
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(val).then(done, () => fallbackCopy(val, done));
    else fallbackCopy(val, done);
  });
}
function fallbackCopy(val, done) {
  const ta = document.createElement("textarea");
  ta.value = val; ta.setAttribute("readonly", ""); ta.className = "vh";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { /* bleibt markiert */ }
  setTimeout(() => ta.remove(), 50);
}

/* ---------------------------------------------------------------- Gliederungsseite */
function tocTarget() {
  const h = location.hash.slice(1);
  const el = h && document.getElementById(h);
  if (!el || el.tagName !== "DETAILS") return;
  document.querySelectorAll("details.is-target").forEach(d => d.classList.remove("is-target"));
  for (let d = el; d; d = d.parentElement && d.parentElement.closest("details")) d.open = true;
  el.classList.add("is-target");
  requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
}

/* ---------------------------------------------------------------- Suchseite */
async function searchPage() {
  const box = document.getElementById("results");
  const params = new URLSearchParams(location.search);
  const raw = (params.get("q") || "").trim();
  const filter = params.get("gesetz");
  const inp = document.getElementById("q");
  if (inp) inp.value = raw;
  if (!raw) { box.innerHTML = `<h1>Suche</h1><p class="sub">Gib oben eine Norm oder einen Suchbegriff ein.</p>`; return; }
  document.title = `„${raw}“ – Suche | Normfinder`;
  box.innerHTML = `<h1>„${esc(raw)}“</h1><p class="spinner">Suche läuft …</p>`;
  const reg = await regReady();
  const r = parseQuery(raw, { registry: reg });
  if (r.type === "norm") return notFound(box, r, raw);
  if (r.type === "law") { location.replace(`${BASE}${r.law}/`); return; }
  if (r.type === "pick") return pick(box, r);
  if (r.type === "lsa") return lsa(box, r);
  return fullText(box, r, filter || r.law);
}

async function notFound(box, r, raw) {
  const idx = await lawIndex(r.law);
  const id = resolveId(idx, r.num);
  if (id) { location.replace(normHref(r.law, id, r)); return; }
  const abk = idx.abk;
  const base = (r.num.match(/^\d+/) || [""])[0];
  let near = idx.norms.filter(n => (n[0].match(/^\d+/) || [""])[0] === base);
  if (!near.length) {
    const num = parseInt(base, 10);
    near = idx.norms.filter(n => /^\d/.test(n[0])).map((n, i) => [n, i])
      .sort((a, b) => Math.abs(parseInt(a[0][0]) - num) - Math.abs(parseInt(b[0][0]) - num)).slice(0, 6)
      .sort((a, b) => a[1] - b[1]).map(x => x[0]);
  }
  box.innerHTML = `<h1>${esc(labelFor(r.law, r.num))} ${esc(abk)} gibt es nicht</h1>
    <p class="sub">Im ${esc(idx.title)} gibt es keine Norm mit dieser Nummer. Vielleicht ist eine dieser gemeint:</p>
    <ul class="hits">${near.slice(0, 8).map(n => `<li><a href="${normHref(r.law, n[0])}"><span class="h-k">${esc(n[1])} ${esc(abk)}</span><span class="h-t">${esc(n[2] || (n[4] ? "(weggefallen)" : ""))}</span></a></li>`).join("")}</ul>
    <div class="row"><a class="btn" href="${BASE}${r.law}/">Gliederung des ${esc(abk)}</a></div>`;
}

async function pick(box, r) {
  const c = await core();
  const num = r.num.toLowerCase();
  const hits = c.norms.filter(n => n[1] === num);
  box.innerHTML = `<h1>${r.art ? "Art." : "§"} ${esc(r.num)} – welches Gesetz?</h1>
    <p class="sub">Ohne Gesetzesangabe rät der Normfinder nicht. ${hits.length ? "Diese Kerngesetze haben eine Norm mit dieser Nummer:" : "Keines der Kerngesetze hat eine Norm mit dieser Nummer. Schreib das Gesetz dazu, z. B. „" + esc(r.num) + " bgb“."}</p>
    <ul class="hits">${hits.map(n => { const rr = { ...r, law: n[0] }; return `<li><a href="${normHref(n[0], n[1], rr)}"><span class="h-k">${esc(citation(n[2], abkFor(n[0]), rr))}</span><span class="h-t">${esc(n[3])}</span></a></li>`; }).join("")}</ul>`;
}

async function lsa(box, r) {
  const c = await core();
  const L = c.landesrecht;
  const l = L.gesetze.find(x => x.aliase.some(a => a.startsWith(r.key))) || L.gesetze[0];
  box.innerHTML = `<h1>${esc(l.name)} (${esc(l.abk)})</h1><p class="sub">${esc(L.hinweis)}</p>
    <div class="row"><a class="btn" href="${esc(L.url)}" rel="noopener">${esc(L.name)}: Landesrechtsportal ↗</a></div>`;
}

async function fullText(box, r, filter) {
  const q = r.q;
  let res;
  try { res = await FT.search(q, { law: filter }); } catch (e) {
    box.innerHTML = `<h1>„${esc(q)}“</h1><p class="msg">Der Suchindex konnte nicht geladen werden. Bitte später erneut versuchen.</p>`;
    return;
  }
  const head = `<h1>${res.total ? res.total.toLocaleString("de-DE") : "Keine"} ${res.total === 1 ? "Norm" : "Normen"} zu „${esc(q)}“${filter ? " im " + esc(abkFor(filter)) : ""}</h1>`;
  if (!res.total) {
    box.innerHTML = head + `<p class="sub">${res.terms.length ? "Versuch es mit einem anderen oder kürzeren Begriff" : "Bitte ein aussagekräftiges Wort eingeben"}, oder mit einer Norm wie „573 bgb“.${filter ? ` <a href="?q=${encodeURIComponent(q)}">In allen Gesetzen suchen</a>` : ""}</p>`;
    return;
  }
  const counts = (res.counts || []).slice(0, 14);
  const filters = `<div class="filters" role="group" aria-label="Nach Gesetz filtern"><button type="button" data-f="" aria-pressed="${!filter}">Alle<span>${res.total}</span></button>${
    (filter && !counts.some(c => c.url === filter) ? [{ url: filter, abk: abkFor(filter), n: res.total }] : []).concat(counts)
      .map(c => `<button type="button" data-f="${esc(c.url)}" aria-pressed="${c.url === filter}">${esc(c.abk)}<span>${c.n}</span></button>`).join("")}</div>`;
  const shown = res.hits.slice(0, 50);
  const laws = [...new Set(shown.map(h => h.url))].slice(0, 24);
  const idxs = new Map(await Promise.all(laws.map(u => lawIndex(u).then(i => [u, i]).catch(() => [u, null]))));
  const items = shown.filter(h => idxs.get(h.url)).map(h => {
    const idx = idxs.get(h.url), n = idx.norms[h.local];
    if (!n) return "";
    return `<li><a href="${normHref(h.url, n[0])}" data-snip="${esc(h.url)}/${esc(n[0])}"><span class="h-k">${esc(n[1])} ${esc(idx.abk)}</span><span class="h-t">${markTerms(n[2] || "", res.terms)}</span><span class="h-s"></span></a></li>`;
  }).join("");
  box.innerHTML = head + `<p class="sub">Sortiert nach Relevanz; Treffer in der Überschrift zählen mehr.</p>` + filters + `<ul class="hits">${items}</ul>` +
    (res.total > 50 ? `<p class="sub">Die 50 besten von ${res.total.toLocaleString("de-DE")} Treffern. Engere Begriffe oder ein Gesetzesfilter grenzen weiter ein.</p>` : "");
  box.querySelector(".filters").addEventListener("click", e => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    const u = new URL(location.href);
    if (b.dataset.f) u.searchParams.set("gesetz", b.dataset.f); else u.searchParams.delete("gesetz");
    history.pushState(null, "", u);
    searchPage();
  });
  snippets(box, res.terms);
}

async function snippets(box, ts) {
  const links = [...box.querySelectorAll("a[data-snip]")].slice(0, 12);
  for (const a of links) {
    try {
      const html = await fetch(BASE + a.dataset.snip, { credentials: "omit" }).then(r => r.text());
      const doc = new DOMParser().parseFromString(html, "text/html");
      doc.querySelectorAll(".sn").forEach(x => x.remove());
      doc.querySelectorAll(".lawtext .al, .lawtext .il, .lawtext p, .lawtext td").forEach(x => x.append(" "));
      const text = (doc.querySelector(".lawtext")?.textContent || "").replace(/\s+/g, " ").trim();
      const ft = fold(text); // Position nur ungefähr nötig (ß → ss verschiebt minimal)
      let p = -1;
      for (const t of ts) { p = ft.indexOf(t); if (p >= 0) break; }
      p = Math.max(0, p);
      let from = Math.max(0, p - 80), to = Math.min(text.length, p + 180);
      if (from > 0) { const sp = text.indexOf(" ", from); if (sp > -1 && sp < p) from = sp + 1; }
      if (to < text.length) { const sp = text.lastIndexOf(" ", to); if (sp > p) to = sp; }
      a.querySelector(".h-s").innerHTML = (from ? "… " : "") + markTerms(text.slice(from, to), ts) + (to < text.length ? " …" : "");
    } catch (e) { /* ohne Auszug */ }
  }
}

/* ---------------------------------------------------------------- Start */
function init() {
  document.querySelectorAll(".search input[aria-controls]").forEach(i => new Box(i));
  const boxes = [...document.querySelectorAll(".search input")];
  const main = boxes[boxes.length - 1];

  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if (!typing && main && (e.key === "/" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k"))) {
      e.preventDefault(); main.focus(); main.select();
    }
    if (!typing && !e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      const a = document.querySelector(e.key === "ArrowLeft" ? ".pager a.prev" : ".pager a.next");
      if (a) { e.preventDefault(); location.href = a.href; }
    }
  });

  const btn = document.querySelector(".theme-btn");
  if (btn) btn.hidden = false;
  if (btn) btn.addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("nf-theme", next); } catch (e) { /* egal */ }
  });

  if (PAGE === "norm") {
    highlight();
    window.addEventListener("hashchange", highlight);
    wireCopy();
  }
  if (PAGE === "toc") {
    tocTarget();
    window.addEventListener("hashchange", tocTarget);
    document.querySelector(".toc-tools")?.addEventListener("click", e => {
      const b = e.target.closest("[data-toc]");
      if (b) document.querySelectorAll(".tree details").forEach(d => { d.open = b.dataset.toc === "open"; });
    });
  }
  if (PAGE === "search") { searchPage(); window.addEventListener("popstate", searchPage); }
  // Gesetzesverzeichnis im Leerlauf vorladen (kleine Datei, danach aus dem Cache)
  (window.requestIdleCallback || setTimeout)(() => regReady().catch(() => {}), { timeout: 2000 });
}

init();
