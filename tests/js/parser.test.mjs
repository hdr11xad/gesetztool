// Unit-Tests für den Eingabe-Parser:  node --test tests/js/
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseQuery, buildRegistry, anchorFor, citation, partsFromAnchor, lev } from "../../web/assets/parser.js";

const rows = JSON.parse(readFileSync(new URL("../fixtures/laws.json", import.meta.url), "utf8"));
const registry = buildRegistry(rows);
const P = (q, ctx) => parseQuery(q, { registry, contextLaw: ctx || null });

function norm(q, law, num, parts = {}, ctx) {
  const r = P(q, ctx);
  assert.equal(r.type, "norm", `${q} → ${JSON.stringify(r)}`);
  assert.equal(r.law, law, q);
  assert.equal(r.num, num, q);
  for (const k of ["abs", "satz", "nr", "lit"]) assert.equal(r[k], parts[k] ?? null, `${q}: ${k}`);
}

test("Norm + Gesetz in beliebiger Schreibweise", () => {
  for (const q of ["573 bgb", "bgb 573", "§573 BGB", "§ 573 BGB", "p 573 bgb", "573bgb", "bgb573", "BGB 573",
    "Paragraph 573 BGB", "§573bgb", "  573   bgb  "]) norm(q, "bgb", "573");
});

test("Artikel oder Paragraf je nach Gesetz", () => {
  for (const q of ["art 1 gg", "Art. 1 GG", "gg 1", "Artikel 1 GG", "GG Art 1", "gg1", "§ 1 GG"]) norm(q, "gg", "1");
  assert.equal(registry.info.get("gg").sign, "Art.");
  assert.equal(registry.info.get("bgb").sign, "§");
});

test("Buchstabenparagrafen", () => {
  norm("573a bgb", "bgb", "573a");
  norm("§ 573a BGB", "bgb", "573a");
  norm("573abgb", "bgb", "573a");
  norm("§ 312b bgb", "bgb", "312b");
});

test("Absatz, Satz, Nummer, Buchstabe", () => {
  norm("§ 573 Abs. 2 Nr. 1 BGB", "bgb", "573", { abs: "2", nr: "1" });
  norm("573 II 1 bgb", "bgb", "573", { abs: "2", satz: "1" });
  norm("§ 204 Abs. 1 Nr. 4 lit. a BGB", "bgb", "204", { abs: "1", nr: "4", lit: "a" });
  norm("§ 1004 I S. 2 BGB", "bgb", "1004", { abs: "1", satz: "2" });
  norm("§ 1004 Abs. 1 Satz 2 BGB", "bgb", "1004", { abs: "1", satz: "2" });
  norm("§ 280 I 2 bgb", "bgb", "280", { abs: "1", satz: "2" });
  norm("Art. 20 Abs. 3 GG", "gg", "20", { abs: "3" });
  norm("Art. 1 Abs. 1 S. 1 GG", "gg", "1", { abs: "1", satz: "1" });
  norm("263 I stgb", "stgb", "263", { abs: "1" });
  norm("§ 204 Abs. 1 Nr. 4 Buchst. a BGB", "bgb", "204", { abs: "1", nr: "4", lit: "a" });
  norm("§ 573 abs2 nr1 bgb", "bgb", "573", { abs: "2", nr: "1" });
});

test("ff. und Normketten", () => {
  norm("§§ 433 ff. BGB", "bgb", "433");
  norm("433 ff bgb", "bgb", "433");
  norm("§ 433 f. BGB", "bgb", "433");
  norm("§§ 433, 434 BGB", "bgb", "433");
  norm("§ 573 BGB i.V.m. § 574 BGB", "bgb", "573");
  norm("§ 823 I iVm § 31 BGB", "bgb", "823", { abs: "1" });
});

test("Gesetzesnamen und Tippfehler", () => {
  norm("grundgesetz 1", "gg", "1");
  norm("Grundgesetz Art. 20", "gg", "20");
  norm("bürgerlichs gesetzbuch 573", "bgb", "573");
  norm("bürgerliches gesetzbuch 573", "bgb", "573");
  norm("strafgesetzbuch 263", "stgb", "263");
  norm("strafgesezbuch 263", "stgb", "263");
  norm("zivilprozessordnung 29", "zpo", "29");
  norm("§ 29 der Zivilprozessordnung", "zpo", "29");
});

test("Groß-/Kleinschreibung egal", () => {
  for (const q of ["StGB 263", "stgb 263", "STGB 263", "sTgB 263"]) norm(q, "stgb", "263");
});

test("Nur Gesetz → Gliederung", () => {
  for (const q of ["bgb", "BGB", "stgb", "Grundgesetz", "zpo "]) {
    const r = P(q);
    assert.equal(r.type, "law", q);
  }
  assert.equal(P("bgb").law, "bgb");
  assert.equal(P("grundgesetz").law, "gg");
});

test("Nummer ohne Gesetz", () => {
  assert.equal(P("573").type, "pick");
  assert.equal(P("§ 573").type, "pick");
  assert.equal(P("§ 573 Abs. 2").abs, "2");
  norm("573", "bgb", "573", {}, "bgb");                 // auf einer BGB-Normseite
  norm("§ 29", "zpo", "29", {}, "zpo");
  norm("573 II", "bgb", "573", { abs: "2" }, "bgb");
  assert.equal(P("573", "bgb").assumed, true);
  norm("art 1 gg", "gg", "1", {}, "bgb");               // explizites Gesetz schlägt Kontext
});

test("Volltextsuche", () => {
  let r = P("kündigung vermieter");
  assert.equal(r.type, "search");
  assert.equal(r.q, "kündigung vermieter");
  assert.equal(r.law, null);
  r = P("kündigung bgb");
  assert.equal(r.type, "search");
  assert.equal(r.law, "bgb");
  assert.equal(r.q, "kündigung");
  r = P("Würde des Menschen");
  assert.equal(r.type, "search");
  assert.equal(P("Treu und Glauben").type, "search");
});

test("Landesrecht Sachsen-Anhalt", () => {
  for (const [q, k] of [["sog lsa", "sog"], ["SOG LSA", "sog"], ["Verf LSA", "verf"], ["kvg lsa", "kvg"],
    ["BauO LSA", "bauo"], ["verfassung sachsen-anhalt", "verf"], ["§ 13 SOG LSA", "sog"]]) {
    const r = P(q);
    assert.equal(r.type, "lsa", q);
    assert.equal(r.key, k, q);
  }
});

test("Randfälle", () => {
  assert.equal(P("").type, "empty");
  assert.equal(P("   ").type, "empty");
  assert.equal(P("§").type, "search");
  assert.equal(P("§§§ 573 bgb").num, "573");
  assert.equal(P("573 BGB.").num, "573");
  assert.equal(P("(§ 573 BGB)").num, "573");
  assert.equal(P("„§ 573 BGB“").num, "573");
  assert.equal(P("§ 573 Abs. 2 Nr. 1 BGB").law, "bgb");
  assert.equal(P("§ 573 BGB").num, "573");
});

test("Anker und Zitierform", () => {
  assert.equal(anchorFor({ abs: "2", nr: "1" }), "abs-2-nr-1");
  assert.equal(anchorFor({ abs: "1", nr: "4", lit: "a" }), "abs-1-nr-4-lit-a");
  assert.equal(anchorFor({ abs: "2", satz: "1" }), "abs-2-satz-1");
  assert.equal(anchorFor({ satz: "2" }), "satz-2");
  assert.equal(anchorFor({}), "");
  assert.equal(citation("§ 573", "BGB", { abs: "2", satz: "1" }), "§ 573 Abs. 2 S. 1 BGB");
  assert.equal(citation("Art. 1", "GG", { abs: "1" }), "Art. 1 Abs. 1 GG");
  assert.deepEqual(partsFromAnchor("abs-2-nr-1-lit-a"), { abs: "2", satz: null, nr: "1", lit: "a" });
  assert.deepEqual(partsFromAnchor("abs-2a-satz-3"), { abs: "2a", satz: "3", nr: null, lit: null });
});

test("Levenshtein", () => {
  assert.equal(lev("gesetzbuch", "gesetzbuch"), 0);
  assert.equal(lev("bürgerlichs", "bürgerliches"), 1);
  assert.ok(lev("abc", "xyzxyz") > 3);
});
