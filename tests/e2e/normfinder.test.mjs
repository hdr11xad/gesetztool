// End-to-End-Tests mit Playwright:  node --test tests/e2e/*.test.mjs
// Baut einen Stand aus tests/fixtures, startet den lokalen Testserver und prüft
// die Oberfläche im echten Browser (Chromium).
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, mkdirSync, copyFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PORT = 8700 + Math.floor(Math.random() * 200);
const BASE = `http://127.0.0.1:${PORT}/normfinder/`;
let tmp, server, browser;

before(async () => {
  tmp = mkdtempSync(join(tmpdir(), "nf-e2e-"));
  mkdirSync(join(tmp, "cache", "zips"), { recursive: true });
  for (const f of readdirSync(join(ROOT, "tests", "fixtures")).filter(f => f.endsWith(".zip")))
    copyFileSync(join(ROOT, "tests", "fixtures", f), join(tmp, "cache", "zips", f));
  execFileSync("python3", ["-m", "normfinder", "--root", join(tmp, "site"), "--cache", join(tmp, "cache"), "build", "--no-check"],
    { cwd: ROOT, stdio: "ignore" });
  server = spawn("python3", ["-m", "normfinder", "--root", join(tmp, "site"), "serve", "--port", String(PORT)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(BASE); if (r.ok) break; } catch (e) { /* noch nicht bereit */ }
    await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  server?.kill();
  rmSync(tmp, { recursive: true, force: true });
});

async function open(path = "", opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1280, height: 900 }, colorScheme: opts.dark ? "dark" : "light", javaScriptEnabled: opts.js !== false });
  const page = await ctx.newPage();
  page.problems = [];
  page.on("pageerror", e => page.problems.push("JS-Fehler: " + e.message));
  page.on("console", m => { if (m.type() === "error") page.problems.push("Konsole: " + m.text()); });
  page.on("request", r => { if (!r.url().startsWith(`http://127.0.0.1:${PORT}/`)) page.problems.push("Externe Anfrage: " + r.url()); });
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  return page;
}
async function type(page, text) {
  const input = page.locator(".search input").last();
  await input.click();
  await input.fill(text);
  await page.waitForTimeout(250);
  return input;
}
async function enter(page, text) {
  const input = await type(page, text);
  const before = page.url();
  await input.press("Enter");
  await page.waitForURL(u => u.href !== before, { timeout: 5000 }).catch(() => {});
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(150);
}
const path = page => decodeURIComponent(new URL(page.url()).pathname + new URL(page.url()).hash);

test("Startseite: Suchfeld, Beispiele, Kerngesetze, keine externen Anfragen, keine Cookies", async () => {
  const page = await open();
  assert.equal(await page.title(), "Normfinder – Gesetze schnell nachschlagen | FSR Jura Halle");
  assert.ok(await page.locator("#q-big").isVisible());
  assert.ok(await page.locator(".chips .chip").count() >= 6);
  assert.ok(await page.locator(".cards a[href='/normfinder/bgb/']").isVisible());
  assert.ok(await page.locator("text=Keine Rechtsberatung.").isVisible());
  assert.equal(await page.evaluate(() => document.activeElement.id), "q-big");
  assert.deepEqual(await page.context().cookies(), []);
  assert.deepEqual(page.problems, []);
  await page.context().close();
});

test("Direkteingabe springt zur Norm", async () => {
  const page = await open();
  for (const [q, want] of [["573 bgb", "/normfinder/bgb/573"], ["bgb573", "/normfinder/bgb/573"], ["art 1 gg", "/normfinder/gg/1"],
    ["gg 20", "/normfinder/gg/20"], ["grundgesetz 1", "/normfinder/gg/1"], ["§§ 433 ff. BGB", "/normfinder/bgb/433"],
    ["bürgerlichs gesetzbuch 573", "/normfinder/bgb/573"], ["263 stgb", "/normfinder/stgb/263"], ["bgb", "/normfinder/bgb/"],
    ["art 229 § 6 egbgb", "/normfinder/egbgb/229-6"]]) {
    await page.goto(BASE);
    await enter(page, q);
    assert.equal(new URL(page.url()).pathname, want, q);
  }
  assert.deepEqual(page.problems, []);
  await page.context().close();
});

test("Zielmarkierung für Absatz, Satz, Nummer und Buchstabe", async () => {
  const page = await open();
  await enter(page, "§ 573 Abs. 2 Nr. 1 BGB");
  assert.equal(path(page), "/normfinder/bgb/573#abs-2-nr-1");
  assert.ok(await page.locator("#abs-2-nr-1.is-target").isVisible());
  assert.match(await page.locator("[data-copy=cite] code").textContent(), /§ 573 Abs\. 2 Nr\. 1 BGB/);
  await page.goto(BASE);
  await enter(page, "573 II 1 bgb");
  assert.equal(path(page), "/normfinder/bgb/573#abs-2-satz-1");
  await page.goto(BASE);
  await enter(page, "§ 204 Abs. 1 Nr. 4 lit. a BGB");
  assert.ok(await page.locator("#abs-1-nr-4-lit-a.is-target").count() === 1);
  await page.goto(BASE);
  await enter(page, "§ 1004 I S. 2 BGB");
  const sz = page.locator("#abs-1-satz-2");
  assert.ok(await sz.evaluate(el => el.classList.contains("is-target")));
  const bg = await sz.evaluate(el => getComputedStyle(el).backgroundColor);
  assert.notEqual(bg, "rgba(0, 0, 0, 0)");
  await page.context().close();
});

test("Nummer ohne Gesetz: Normseite nutzt aktuelles Gesetz, Startseite fragt nach", async () => {
  const page = await open("bgb/573");
  await enter(page, "574");
  assert.equal(new URL(page.url()).pathname, "/normfinder/bgb/574");
  await page.goto(BASE);
  await enter(page, "263");
  assert.equal(new URL(page.url()).pathname, "/normfinder/suche/");
  await page.waitForSelector(".hits a");
  const hits = await page.locator(".hits .h-k").allTextContents();
  assert.ok(hits.some(h => h.includes("StGB")), hits.join());
  assert.ok(hits.some(h => h.includes("BGB")), hits.join());
  await page.context().close();
});

test("Nicht existierende Norm: Meldung und ähnliche Normen", async () => {
  const page = await open();
  await enter(page, "§ 573z BGB");
  await page.waitForSelector("#results h1");
  assert.match(await page.locator("#results h1").textContent(), /§ 573z BGB gibt es nicht/);
  const near = await page.locator(".hits .h-k").allTextContents();
  assert.ok(near.includes("§ 573a BGB"), near.join());
  await page.context().close();
});

test("Vorschläge beim Tippen und Tastatursteuerung", async () => {
  const page = await open("bgb/573");
  await page.keyboard.press("/");
  assert.equal(await page.evaluate(() => document.activeElement.id), "q");
  await page.keyboard.type("573 bgb");
  await page.waitForSelector("#q-sugg li[role=option]");
  await page.waitForTimeout(400);
  const first = await page.locator("#q-sugg li[role=option]").first().textContent();
  assert.match(first, /§ 573 BGB/);
  assert.equal(await page.locator("#q").getAttribute("aria-expanded"), "true");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/bgb\/573a$/);
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("Escape");
  await page.locator("h1").click();
  await page.keyboard.press("ArrowRight");
  await page.waitForURL(/\/bgb\/573b$/);
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("ArrowLeft");
  await page.waitForURL(/\/bgb\/573a$/);
  await page.context().close();
});

test("Volltextsuche mit Relevanz und Gesetzesfilter", async () => {
  const page = await open();
  await enter(page, "kündigung vermieter");
  await page.waitForSelector(".hits a");
  const keys = await page.locator(".hits .h-k").allTextContents();
  assert.ok(keys.slice(0, 5).includes("§ 573 BGB"), keys.slice(0, 8).join());
  assert.ok(await page.locator(".filters button").count() >= 2);
  await page.goto(BASE + "suche/?q=gerichtsstand");
  await page.waitForSelector(".filters button[data-f='zpo']");
  await page.locator(".filters button[data-f='zpo']").click();
  await page.waitForSelector(".hits a");
  const all = await page.locator(".hits .h-k").allTextContents();
  assert.ok(all.length > 0 && all.every(k => k.endsWith("ZPO")), all.join());
  assert.match(page.url(), /gesetz=zpo/);
  assert.deepEqual(page.problems, []);
  await page.context().close();
});

test("Landesrecht nur als Link", async () => {
  const page = await open();
  await enter(page, "sog lsa");
  await page.waitForSelector("#results a.btn");
  assert.match(await page.locator("#results a.btn").getAttribute("href"), /landesrecht\.sachsen-anhalt\.de/);
  await page.context().close();
});

test("Mobile Breite: kein waagrechtes Scrollen, Suchfeld voll nutzbar", async () => {
  for (const p of ["", "bgb/573", "bgb/", "estg/32a", "suche/?q=kündigung"]) {
    const page = await open(p, { viewport: { width: 360, height: 740 } });
    await page.waitForTimeout(300);
    const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    assert.ok(sw <= iw, `${p}: ${sw} > ${iw}`);
    assert.ok(await page.locator(".search input").last().isVisible(), p);
    await page.context().close();
  }
});

test("Dark Mode folgt dem System und lässt sich umschalten", async () => {
  const page = await open("bgb/573", { dark: true });
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  assert.equal(bg, "rgb(17, 22, 30)");
  await page.locator(".theme-btn").click();
  const bg2 = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  assert.equal(bg2, "rgb(255, 255, 255)");
  await page.reload();
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "light");
  await page.context().close();
});

test("Ohne JavaScript: Normtext, Links und Zielmarkierung per :target", async () => {
  const page = await open("bgb/573#abs-2-nr-2", { js: false });
  assert.match(await page.locator(".lawtext").textContent(), /berechtigtes Interesse/);
  const bg = await page.locator("#abs-2-nr-2").evaluate(el => getComputedStyle(el).backgroundColor);
  assert.notEqual(bg, "rgba(0, 0, 0, 0)");
  assert.equal(await page.locator(".js-only").first().isVisible(), false);
  await page.locator(".pager a.next").click();
  assert.equal(new URL(page.url()).pathname, "/normfinder/bgb/573a");
  await page.context().close();
});

test("Barrierearmut: Sprungmarke, Überschriften, sichtbarer Fokus", async () => {
  const page = await open("bgb/573");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.className), "skip");
  assert.ok(await page.locator(".skip").isVisible());
  assert.equal(await page.locator("h1").count(), 1);
  assert.equal(await page.locator("html").getAttribute("lang"), "de");
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  assert.notEqual(outline, "none");
  const imgsWithoutAlt = await page.locator("img:not([alt])").count();
  assert.equal(imgsWithoutAlt, 0);
  await page.context().close();
});
