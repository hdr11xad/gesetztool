// Eingabe-Parser des Normfinders (läuft im Browser und in den Unit-Tests unter Node).
//
// parseQuery("§ 573 Abs. 2 Nr. 1 BGB", { registry }) →
//   { type: "norm", law: "bgb", num: "573", abs: "2", satz: null, nr: "1", lit: null }
//
// Ergebnistypen: norm · law · pick (Nummer ohne Gesetz) · lsa · search · empty

export const ROMAN = { i: 1, ii: 2, iii: 3, iv: 4, v: 5, vi: 6, vii: 7, viii: 8, ix: 9, x: 10, xi: 11, xii: 12, xiii: 13, xiv: 14, xv: 15, xvi: 16, xvii: 17, xviii: 18, xix: 19, xx: 20 };
const FILLER = new Set(["§", "§§", "p", "pp", "par", "para", "paragraf", "paragraph", "paragraphen", "ff", "f", "des", "der", "dem", "den", "die", "das", "im", "sinne", "nach", "gem", "gemäß", "vgl", "iVm", "ivm", "von", "vom", "zum", "zur", "in"]);
const MARKER = new Set(["§", "§§", "p", "pp", "par", "para", "paragraf", "paragraph", "paragraphen", "art", "artt", "artikel"]);
const KEY = { abs: "abs", absatz: "abs", s: "satz", satz: "satz", nr: "nr", nrn: "nr", nummer: "nr", ziff: "nr", ziffer: "nr", lit: "lit", buchst: "lit", buchstabe: "lit", hs: "hs", halbsatz: "hs", alt: "alt", alternative: "alt", var: "alt", variante: "alt", uabs: "uabs", unterabsatz: "uabs" };
const STOP_AT = new Set(["bis", "und", "oder", "sowie", "ivm", "u", "bzw"]);

const LSA = [
  { key: "verf", re: /\b(l?verf)\s*[-.]?\s*(lsa|st|sachsen-anhalt)\b|verfassung (des landes )?sachsen-anhalt|\blsa\s+verf\b/ },
  { key: "sog", re: /\bsog\s*[-.]?\s*(lsa|st)\b|\blsa\s+sog\b/ },
  { key: "kvg", re: /\bkvg\s*[-.]?\s*(lsa|st)\b|\blsa\s+kvg\b/ },
  { key: "bauo", re: /\bbauo\s*[-.]?\s*(lsa|st)\b|\blsa\s+bauo\b|bauordnung sachsen-anhalt/ },
];

export const fold = s => s.toLowerCase().replace(/ä/g, "a").replace(/ö/g, "o").replace(/ü/g, "u").replace(/ß/g, "ss");
export const normKey = s => s.toLowerCase().replace(/[\s._\-]+/g, "");

export function lev(a, b, max = 3) {
  const m = a.length, n = b.length;
  if (Math.abs(m - n) > max) return max + 1;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (cur[j] < best) best = cur[j];
    }
    if (best > max) return max + 1;
    prev = cur;
  }
  return prev[n];
}

/** Register aus data/laws.json: [url, abk, titel, zeichen, [schlüssel], [namen], kerngruppe, normzahl] */
export function buildRegistry(rows) {
  const info = new Map(), byKey = new Map(), names = [], fuzzy = [];
  for (const r of rows) {
    const [url, abk, title, sign, keys, nm, core, count] = r;
    const it = { url, abk, title, sign: sign === "a" ? "Art." : "§", core, count };
    info.set(url, it);
    for (const k of [normKey(abk), ...keys]) if (k && !byKey.has(k)) byKey.set(k, url);
    for (const n of nm || []) {
      const low = n.toLowerCase();
      names.push([low, url]);
      if (core >= 0 || (count > 40 && low.length < 40)) fuzzy.push([low, url]);
    }
  }
  names.sort((a, b) => b[0].length - a[0].length);
  // Kerngesetze zuerst prüfen, damit Tippfehler bei bekannten Namen gewinnen
  fuzzy.sort((a, b) => (info.get(a[1]).core < 0) - (info.get(b[1]).core < 0));
  return { info, byKey, names, fuzzy };
}

function lawFor(reg, tok) {
  if (!reg || !tok) return null;
  return reg.byKey.get(normKey(tok)) || null;
}

/** Ersetzt ausgeschriebene Gesetzesnamen durch einen Platzhalter „@url“. */
function replaceNames(t, reg) {
  if (!reg) return t;
  for (const [name, url] of reg.names) {
    if (name.length < 6) continue;
    const i = t.indexOf(name);
    if (i >= 0 && /[\s(]/.test(t[i - 1] || " ") && /[\s,.;)]/.test(t[i + name.length] || " ")) {
      return t.slice(0, i) + " @" + url + " " + t.slice(i + name.length);
    }
  }
  // Tippfehler in mehrteiligen Namen („bürgerlichs gesetzbuch“)
  const ws = t.trim().split(/\s+/);
  for (const [name, url] of reg.fuzzy) {
    const parts = name.split(" ");
    const k = parts.length;
    if (k < 2 || k > 5) continue;
    for (let i = 0; i + k <= ws.length; i++) {
      const cand = ws.slice(i, i + k).join(" ");
      const tol = Math.min(3, Math.floor(name.length / 8));
      if (Math.abs(cand.length - name.length) <= tol && lev(cand, name, tol) <= tol) {
        ws.splice(i, k, "@" + url);
        return " " + ws.join(" ") + " ";
      }
    }
  }
  return t;
}

function fuzzyWord(tok, reg) {
  if (!reg || tok.length < 8 || tok.startsWith("@")) return null;
  const tol = tok.length >= 12 ? 2 : 1;
  for (const [name, url] of reg.fuzzy) {
    if (name.includes(" ")) continue;
    if (Math.abs(name.length - tok.length) <= tol && lev(tok, name, tol) <= tol) return url;
  }
  return null;
}

export function parseQuery(raw, { registry = null, contextLaw = null } = {}) {
  if (!raw || !raw.trim()) return { type: "empty" };
  let t = " " + raw.toLowerCase().replace(/[   ]/g, " ") + " ";
  for (const l of LSA) if (l.re.test(t)) return { type: "lsa", key: l.key };

  t = t.replace(/\bi\.?\s*v\.?\s*m\.?(?=\s|\d|$)/g, " ivm ");
  t = t.replace(/(\d[a-z]?)\s*,\s*(?=(?:§\s*)?\d)/g, "$1 und "); // „§§ 433, 434“ = Aufzählung
  t = replaceNames(t, registry);
  t = t.replace(/§/g, " § ")
    .replace(/(\d[a-z]{0,2})\s*f{1,2}\.?(?=\s|$|[,;])/g, "$1 ")
    .replace(/\b(abs|nr|nrn|lit|buchst|art|artt|ziff|hs|alt|var|uabs|s|p|par)\.(?=\s|\d)/g, "$1 ")
    .replace(/(\d)\.(?=\s|$)/g, "$1 ")
    .replace(/[,;:()„“"']/g, " ")
    .replace(/\.(?=\s|$)/g, " ")
    .replace(/\s+/g, " ").trim();

  // Tokens trennen: „573bgb“, „bgb573“, „§573“, „abs2“, „sgbv“
  let toks = [];
  for (const tok of t.split(" ")) {
    let m;
    if (tok.startsWith("@")) { toks.push(tok); continue; }
    if ((m = tok.match(/^(\d+)([a-zäöü][\wäöü-]{1,})$/)) && lawFor(registry, m[2])) toks.push(m[1], m[2]);
    else if ((m = tok.match(/^(\d+[a-z])([a-zäöü][\wäöü-]{1,})$/)) && lawFor(registry, m[2])) toks.push(m[1], m[2]);
    else if ((m = tok.match(/^([a-zäöü][a-zäöü-]*?)(\d+[a-z]?)$/)) && (lawFor(registry, m[1]) || KEY[m[1]] || MARKER.has(m[1]) || FILLER.has(m[1]))) toks.push(m[1], m[2]);
    else toks.push(tok);
  }

  // Gesetzeskürzel erkennen (auch zweiteilig: „sgb v“, „vvg 2008“)
  const out = [];
  let law = null, lawWeak = null;
  const rawLow = raw;
  for (let i = 0; i < toks.length; i++) {
    const tok = toks[i];
    if (tok.startsWith("@")) { if (!law) law = tok.slice(1); continue; }
    if (!law && i + 1 < toks.length && /^([ivx]+|\d{4}|lsa)$/.test(toks[i + 1])) {
      const two = lawFor(registry, tok + toks[i + 1]);
      if (two && !lawFor(registry, tok)) { law = two; i++; continue; }
    }
    const l = /^\d/.test(tok) || KEY[tok] || MARKER.has(tok) ? null : lawFor(registry, tok);
    if (l && !law) {
      const strong = registry.info.get(l).core >= 0 || /\d/.test(rawLow) || toks.length === 1
        || new RegExp("(^|[^A-Za-zÄÖÜäöüß])" + tok.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![a-zäöüß])", "i").test(rawLow) && /[A-ZÄÖÜ]{2}/.test(rawLow);
      if (strong) { law = l; continue; }
      lawWeak = l;
    }
    out.push(tok);
  }
  if (!law) {
    for (let i = 0; i < out.length; i++) {
      const u = fuzzyWord(out[i], registry);
      if (u) { law = u; out.splice(i, 1); break; }
    }
  }

  const r = { num: null, abs: null, satz: null, nr: null, lit: null };
  const words = [];
  let expect = null, stop = false, art = false, hasMarker = false, artPara = false;
  for (const tok of out) {
    if (stop) continue;
    if (MARKER.has(tok)) {
      hasMarker = true;
      if (tok.startsWith("art")) art = true;
      else if (r.num !== null && art && r.abs === null) artPara = true; // „Art. 229 § 6 EGBGB“
      continue;
    }
    if (expect) {
      const want = expect;
      expect = null;
      if (want === "hs" || want === "alt" || want === "uabs") { if (/^\d+$|^[ivx]+$/.test(tok)) continue; }
      else if (want === "lit" ? /^[a-z]{1,2}$/.test(tok) : /^\d+[a-z]?$/.test(tok)) { r[want] = tok; continue; }
      else if (want === "abs" && ROMAN[tok]) { r.abs = String(ROMAN[tok]); continue; }
    }
    if (r.num === null && /^\d+[a-z]{0,2}$/.test(tok)) { r.num = tok; continue; }
    if (artPara && /^\d+[a-z]?$/.test(tok)) { r.num = r.num + "-" + tok; artPara = false; continue; }
    if (r.num !== null) {
      if (KEY[tok]) { expect = KEY[tok]; continue; }
      if (ROMAN[tok] && r.abs === null) { r.abs = String(ROMAN[tok]); continue; }
      if (STOP_AT.has(tok)) { stop = true; continue; }
      if (/^\d+[a-z]?$/.test(tok)) {
        if (r.abs === null) r.abs = tok;
        else if (r.satz === null && r.nr === null) r.satz = tok;
        else if (r.nr === null) r.nr = tok;
        continue;
      }
      if (/^[a-z]$/.test(tok) && r.nr !== null && r.lit === null) { r.lit = tok; continue; }
    }
    if (FILLER.has(tok) || STOP_AT.has(tok)) continue;
    words.push(tok);
  }
  if (r.num !== null) {
    if (law && (words.length === 0 || hasMarker))
      return { type: "norm", law, assumed: false, art, ...r };
    if (!law && (hasMarker || words.length === 0)) {
      if (contextLaw) return { type: "norm", law: contextLaw, assumed: true, art, ...r };
      return { type: "pick", art, ...r };
    }
  }
  if (r.num === null && law && words.length === 0) return { type: "law", law };
  const q = words.length ? words.join(" ") : raw.replace(/§/g, " ").trim();
  return { type: "search", q, law: law || null, weakLaw: lawWeak };
}

/** Anker auf der Normseite: abs-2-satz-1, abs-2-nr-1-lit-a, nr-3 … */
export function anchorFor(r) {
  const p = [];
  if (r.abs) p.push("abs-" + r.abs);
  if (r.nr) { p.push("nr-" + r.nr); if (r.lit) p.push("lit-" + r.lit); }
  else if (r.satz) p.push("satz-" + r.satz);
  else if (r.lit) p.push("lit-" + r.lit);
  return p.join("-");
}

/** Zitierform: „§ 573 Abs. 2 S. 1 BGB“, „Art. 1 Abs. 1 GG“ */
export function citation(label, abk, r = {}) {
  let s = label;
  if (r.abs) s += " Abs. " + r.abs;
  if (r.satz) s += " S. " + r.satz;
  if (r.nr) s += " Nr. " + r.nr;
  if (r.lit) s += " lit. " + r.lit;
  return s + " " + abk;
}

/** Liest die Teile aus einem Anker („abs-2-nr-1-lit-a“). */
export function partsFromAnchor(h) {
  const r = { abs: null, satz: null, nr: null, lit: null };
  const re = /(abs|satz|nr|lit)-([0-9a-z]+?)(?=-(?:abs|satz|nr|lit|dlit)-|$)/g;
  let m;
  while ((m = re.exec(h))) r[m[1]] = m[2];
  return r;
}
