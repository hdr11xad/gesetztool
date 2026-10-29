# Normfinder – FSR Jura Halle

Ein offenes, werbefreies Werkzeug zum Nachschlagen von Normen: `573 bgb`
eingeben, Enter, und man landet bei § 573 BGB, mit markiertem Absatz, Satz
oder Nummer. Enthalten sind alle Bundesgesetze und -verordnungen von
[gesetze-im-internet.de](https://www.gesetze-im-internet.de/), jede Nacht
aktualisiert. Läuft unter <https://fsr-jura-halle.de/normfinder/> als
eigenständige statische Seite neben WordPress.

- Jede Norm hat eine echte, teilbare Adresse: `/normfinder/bgb/573#abs-2-nr-1`
- Seiten sind statisch erzeugt: funktionieren ohne JavaScript, sind für
  Suchmaschinen sichtbar und schnell
- Suche, Vorschläge und Volltextsuche laufen im Browser; Suchanfragen gehen
  nicht an den Server
- Keine Cookies, kein Tracking, keine externen Anfragen (Schriften lokal)
- Gestaltung nach dem Theme von fsr-jura-halle.de, mit Dark Mode,
  mobil zuerst und barrierearm

**Einrichtung auf dem Server:** [docs/SERVER.md](docs/SERVER.md) ·
**Verlinkung in WordPress:** [docs/WORDPRESS.md](docs/WORDPRESS.md) ·
**Gestaltung:** [docs/DESIGN.md](docs/DESIGN.md)

---

## Aufbau

```
                 nachts (systemd-Timer)                         Browser
gesetze-im-internet.de ─► fetch.py ─► gii.py ─► render.py ─►  /srv/normfinder/releases/<Stand>/
   gii-toc.xml + xml.zip   ETag-Cache   XML→Modell  HTML, JSON,       ▲ current (Symlink)
                                        refs.py     Suchindex          │
                                        text.py                Caddy liefert /normfinder/* aus
```

| Datei | Aufgabe |
|---|---|
| `normfinder/fetch.py` | Inhaltsverzeichnis und Archive laden: nur Geändertes (ETag/Last-Modified), eine Keep-Alive-Verbindung, Rate-Limit, Timeouts, Wiederholungen, ZIP-Prüfung |
| `normfinder/gii.py` | Parser für das amtliche XML (`gii-norm.dtd`): Stammdaten, Gliederung, Normen, Absätze, Aufzählungen, Tabellen (CALS), Bilder, Fußnoten, weggefallene Normen, Artikel mit Paragrafen (EGBGB) |
| `normfinder/text.py` | Satzerkennung (an den amtlichen Satznummern des EStG geprüft: > 99 % Treffer) und HTML-Ausgabe von Fließtext |
| `normfinder/refs.py` | Verweise verlinken: `§ 573 Abs. 2 Nr. 1`, `§§ 433 bis 435`, `§ 29 ZPO`, `§ 1 des Handelsgesetzbuchs`, „dieses Gesetzes“ |
| `normfinder/laws.py` | Gesetzesregister: URL-Kennungen, Abkürzungen, Namen (auch im Genitiv) |
| `normfinder/render.py` | HTML-Seiten (Norm, Gliederung, Startseite, A–Z, Suche, 404) |
| `normfinder/search_index.py` | Volltextindex, aufgeteilt nach Wortanfang |
| `normfinder/build.py` | Stand erzeugen, prüfen, atomar umschalten, alte Stände aufräumen, Rückfall |
| `normfinder/__main__.py` | Kommandozeile: `update`, `fetch`, `build`, `status`, `rollback`, `serve` |
| `web/assets/` | Oberfläche: `parser.js` (Eingabe-Parser), `app.js` (Vorschläge, Sprung, Markierung, Kopieren, Tastatur), `search.js` (Volltext), `app.css`, Schriften, Logo |
| `data/aliases.json` | zusätzliche Abkürzungen und Namen aus der Studienpraxis |
| `data/core.json` | Kerngesetze (Startseite, Vorschläge) und Landesrecht Sachsen-Anhalt (nur Links) |
| `deploy/` | systemd-Dienst und -Timer, Caddy-Block, Einstellungen, Einrichtungsskript |
| `tests/` | Unit-Tests (Python, Node) und End-to-End-Tests (Playwright) |

Nur die Python-Standardbibliothek wird gebraucht (Python ≥ 3.11); auf dem
Server ist nichts zu installieren. Node und Playwright braucht es nur für die
Tests.

### Erzeugte Dateien eines Stands

```
index.html                 Startseite
bgb/index.html             Gliederung des BGB
bgb/573.html               § 573 BGB  (Adresse: /normfinder/bgb/573)
bgb/index.json             Normliste des BGB für Vorschläge und Prüfung im Browser
bgb/img/…                  Bilder aus dem amtlichen Archiv (z. B. Verkehrszeichen)
gesetze/a/index.html …     alle Gesetze von A bis Z
suche/index.html           Suchergebnisse (im Browser berechnet)
data/laws.json             alle Gesetze: Kürzel, Titel, §/Art., Aliase (für den Eingabe-Parser)
data/core.json             Normen der Kerngesetze mit Überschrift (Vorschläge ohne Gesetzesangabe)
data/fts/manifest.json     Volltextindex: Gesetze, Dokumentnummern, Grenzen der Teildateien
data/fts/<n>.json          Teildateien: Begriff → Liste aus (Δ Dokumentnummer × 32 + Gewicht)
sitemap.xml, sitemap-N.xml für Suchmaschinen
build.json                 Statistik des Stands (Anzahl, Fehler, Code-Version)
```

Ein Aufruf lädt nur, was er braucht: Normseiten sind fertiges HTML;
`laws.json` wird beim ersten Tippen geladen, eine `index.json` nur für das
Gesetz, das man gerade eingibt, und für die Volltextsuche nur die Teildateien
der Suchwörter. Keine Seite lädt das gesamte Bundesrecht.

### URLs

`/normfinder/<gesetz>/<norm>` mit Kennungen in Kleinbuchstaben:
`bgb/573a`, `gg/1`, `egbgb/229-6` (Art. 229 § 6 EGBGB), `estg/anlage-1`,
`gg/praeambel`. Die Gesetzeskennung ist die amtliche Abkürzung
(`bgb`, `stvo`, `sgb-v`); Kerngesetze mit abweichender Studienabkürzung
bekommen diese (`egbgb`, `weg`). Die Kennung von gesetze-im-internet.de leitet
weiter (`/normfinder/bgbeg/` → `/normfinder/egbgb/`). Anker:
`#abs-2`, `#abs-2-satz-1`, `#abs-2-nr-1`, `#abs-1-nr-4-lit-a`, ohne Absätze
`#satz-2` bzw. `#nr-3`. Zielmarkierung klappt auch ohne JavaScript (`:target`).

## Update-Ablauf

`python3 -m normfinder update` (nächtlich per `normfinder-update.timer`):

1. Inhaltsverzeichnis und geänderte Archive laden.
2. Nichts geändert (Daten und Code)? → fertig, alter Stand bleibt.
3. Neuen Stand in `releases/<Zeit>.tmp` erzeugen; unveränderte Dateien werden
   aus dem Vorstand hart verlinkt.
4. Prüfen (Mindestumfang, Stichproben, Kerngesetze, höchstens −5 % zum Vorstand).
5. Bestanden → Symlink `current` atomar umschalten; sonst bleibt der alte
   Stand online, der neue wird als `.failed` aufgehoben.
6. Meldung an Uptime Kuma (Push-Monitor), optional Mail per `sendmail`.
7. Die letzten drei Stände bleiben erhalten.

## Logs

- systemd-Journal: `journalctl -u normfinder-update`
- Datei je Lauf: `/srv/normfinder/logs/update-JJJJ-MM-TT.log` (30 Tage)
- Statistik des aktiven Stands: `python3 -m normfinder --root /srv/normfinder status`

## Rückfall (Rollback)

```bash
cd /opt/normfinder && sudo -u normfinder python3 -m normfinder --root /srv/normfinder rollback
```

Schaltet sofort auf den vorherigen Stand um.

## Gesetze und Aliase ergänzen

Alle Bundesgesetze kommen automatisch aus dem Inhaltsverzeichnis von
gesetze-im-internet.de; neue Gesetze erscheinen nach dem nächsten Lauf von selbst.
Amtliche Abkürzung, juris-Abkürzung, Kurz- und Langtitel werden ebenfalls
automatisch übernommen.

**Weitere Abkürzung oder Name** (z. B. aus der Studienpraxis): in
`data/aliases.json` beim Gesetz eintragen. Schlüssel ist die Kennung auf
gesetze-im-internet.de (steht in der Adresse der amtlichen Fassung):

```json
"woeigg": ["WEG", "WoEigG", "Wohnungseigentumsgesetz"],
```

Abkürzungen (ohne Leerzeichen, mehrere Großbuchstaben) werden als Kürzel
erkannt, alles andere als Name. Steht ein Kerngesetz mit einer Abkürzung an
erster Stelle, wird sie zur URL (`/normfinder/weg/`).

**Kerngesetz** (Startseite, Vorschläge bei Nummern ohne Gesetz): in
`data/core.json` in die passende Gruppe und in `vorschlag_reihenfolge`.

Danach `git pull` auf dem Server; der nächste Lauf erzeugt alles neu.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

```bash
npm test
```

```bash
npm run test:e2e
```

- **Python** (`tests/test_*.py`): XML-Parser an echten Archiven (BGB, GG,
  StGB, ZPO, EStG mit Tabellen und Anlagen, BauNVO, EGBGB), Satzerkennung
  (gegen amtliche Satznummern), Verweiserkennung, Erzeugung, Prüfung,
  Umschalten, harte Links, Rückfall.
- **Node** (`tests/js/`): Eingabe-Parser mit allen Beispieleingaben
  („573 bgb“, „§ 204 Abs. 1 Nr. 4 lit. a BGB“, „bürgerlichs gesetzbuch 573“ …)
  und Randfällen.
- **Playwright** (`tests/e2e/`): Startseite, Direkteingabe, Zielmarkierung,
  Vorschläge und Tastatur, Volltextsuche mit Filter, mobile Breite, Dark Mode,
  ohne JavaScript, keine externen Anfragen, keine Cookies.
  Braucht `npm install playwright` und einen Chromium (`npx playwright install chromium`).

## Lokal entwickeln

```bash
python3 -m normfinder --root ./site --cache ./cache fetch --only bgb,gg,stgb,zpo
```

```bash
python3 -m normfinder --root ./site --cache ./cache build --no-check
```

```bash
python3 -m normfinder --root ./site serve
```

Dann <http://127.0.0.1:8000/normfinder/> öffnen. Der Testserver verhält sich
wie die Caddy-Konfiguration (saubere URLs, 404-Seite, Content-Security-Policy).

## Rechtliches

- Code: [EUPL-1.2](LICENSE)
- Schriften Newsreader, Schibsted Grotesk, Instrument Sans: SIL Open Font
  License 1.1 (`web/assets/fonts/OFL.txt`), lokal ausgeliefert
- Logo: Fachschaftsrat Jura Halle-Wittenberg
- Gesetzestexte: Bundesministerium der Justiz, gesetze-im-internet.de; amtliche
  Werke (§ 5 UrhG). Keine Rechtsberatung, maßgeblich ist die amtliche Fassung.
- Landesrecht Sachsen-Anhalt wird nicht übernommen, sondern nur verlinkt.
