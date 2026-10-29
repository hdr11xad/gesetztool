// Volltextsuche im Browser über den in Teildateien gegliederten Index (data/fts/).
// Geladen werden nur die Teildateien der Suchwörter – nie das gesamte Bundesrecht.

import { fold } from "./parser.js";

const STOP = new Set(`aber als am an auch auf aus bei bis da dabei damit dann dar darf daruber das dass dem den
denen der deren des dessen die dies diese diesem diesen dieser dieses doch dort durch ein eine einem einen einer
eines er es fur gegen hat haben hier ihm ihn ihr ihre ihrem ihren ihrer ihres im in ist jede jedem jeden jeder
jedes kann kein keine keinem keinen keiner konnen man mit muss mussen nach nicht noch nur ob oder ohne sein seine
seinem seinen seiner seines sich sie sind so soll sollen soweit sofern sowie uber um und uns unter vom von vor war
wenn werden wer wie wird wo zu zum zur zwar abs absatz absatzes nr nummer satz satzes buchstabe buchst gemass gem
vgl bzw sinne`.split(/\s+/));

export function terms(q) {
  return [...new Set((fold(q).match(/[a-z0-9]+/g) || []).filter(t => t.length >= 2 && !STOP.has(t) && !/^\d+$/.test(t)))];
}

export class FullText {
  constructor(base, fetchJSON) {
    this.base = base;
    this.json = fetchJSON;
    this.manifest = null;
  }

  async init() {
    if (!this.manifest) this.manifest = await this.json(this.base + "data/fts/manifest.json");
    return this.manifest;
  }

  shardsFor(term) {
    const s = this.manifest.shards;
    let lo = 0, hi = s.length - 1, idx = 0;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (s[mid] <= term) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
    const out = [idx];
    for (let i = idx + 1; i < s.length && s[i].startsWith(term) && out.length < 6; i++) out.push(i);
    return out;
  }

  async postings(term) {
    const shards = await Promise.all(this.shardsFor(term).map(i => this.json(`${this.base}data/fts/${i}.json`)));
    const docs = new Map();
    let keys = 0;
    for (const sh of shards) {
      for (const k in sh) {
        if (k !== term && !(term.length >= 4 && k.startsWith(term))) continue;
        if (++keys > 80 && k !== term) continue;
        const exact = k === term;
        let doc = 0;
        for (const v of sh[k]) {
          doc += Math.floor(v / 32);
          const w = v % 32;
          // Gewicht: Titeltreffer zählt am meisten, exakte Wörter mehr als Wortanfänge
          const val = ((w >= 16 ? 6 : 0) + Math.min(w & 15, 8) / (1 + Math.min(w & 15, 8) * 0.25) + 0.2) * (exact ? 1 : 0.8);
          const old = docs.get(doc) || 0;
          if (val > old) docs.set(doc, val);
        }
      }
    }
    return docs;
  }

  lawOf(doc) {
    const L = this.manifest.laws;
    let lo = 0, hi = L.length - 1, idx = 0;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (L[mid][2] <= doc) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
    return { url: L[idx][0], abk: L[idx][1], local: doc - L[idx][2], idx };
  }

  lawRange(url) {
    const L = this.manifest.laws;
    const i = L.findIndex(l => l[0] === url);
    if (i < 0) return null;
    return [L[i][2], i + 1 < L.length ? L[i + 1][2] : this.manifest.docs];
  }

  /** → { hits: [{doc, score, url, abk, local}], total, terms } */
  async search(q, { law = null, limit = 300 } = {}) {
    await this.init();
    const ts = terms(q);
    if (!ts.length) return { hits: [], total: 0, terms: ts };
    const lists = await Promise.all(ts.map(t => this.postings(t)));
    const N = this.manifest.docs;
    lists.sort((a, b) => a.size - b.size);
    const range = law ? this.lawRange(law) : null;
    const scored = [];
    for (const [doc, w0] of lists[0]) {
      if (range && (doc < range[0] || doc >= range[1])) continue;
      let score = 0, ok = true;
      for (let i = 0; i < lists.length; i++) {
        const w = i === 0 ? w0 : lists[i].get(doc);
        if (!w) { ok = false; break; }
        score += Math.log(1 + N / lists[i].size) * w;
      }
      if (ok) scored.push([doc, score]);
    }
    scored.sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    return {
      total: scored.length, terms: ts,
      hits: scored.slice(0, limit).map(([doc, score]) => ({ doc, score, ...this.lawOf(doc) })),
      counts: countByLaw(scored, this),
    };
  }
}

function countByLaw(scored, ft) {
  const m = new Map();
  for (const [doc] of scored) {
    const l = ft.lawOf(doc);
    const e = m.get(l.url) || { url: l.url, abk: l.abk, n: 0 };
    e.n++;
    m.set(l.url, e);
  }
  return [...m.values()].sort((a, b) => b.n - a.n);
}
