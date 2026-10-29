# Gestaltung: Design-Tokens

Abgeleitet aus dem Theme **fsr-jura-theme-redesign** (`theme.json`, `style.css`,
`assets/css/schriften.css`), das live auf fsr-jura-halle.de läuft. Die Tokens
stehen als CSS-Variablen in `web/assets/app.css`.

## Farben

| Token | Hell | Dunkel | Herkunft / Einsatz |
|---|---|---|---|
| `--fsr-bordeaux` | `#5e1f27` | – | Theme-Hauptfarbe: Kopfzeile, Überschriften, Akzent |
| `--fsr-dunkel` | `#1a2431` | – | Theme „Dunkelblau – Text, Footer“ |
| `--fsr-blau` | `#1d3b58` | – | Theme-Sekundärfarbe: Fokusrahmen |
| `--fsr-lila` | `#e2a9f1` | – | Theme „große Flächen“: Startseiten-Band |
| `--fsr-rosa` | `#ff99d8` | – | Theme „kleine Schrift auf dunklem Grund“: Fußzeilenlinks, Akzent im Dunkelmodus |
| `--fsr-pink` | `#ff66c4` | – | Theme „Akzent, sparsam“: Hover-Unterstrich in der Kopfzeile |
| `--bg` | `#ffffff` | `#11161e` | Seitenhintergrund |
| `--surface` / `--surface-2` | `#faf7f9` / `#f3edf1` | `#18202b` / `#212b38` | Flächen, Tabellenkopf |
| `--ink` | `#1a2431` | `#ece6ea` | Text |
| `--muted` | `#4b5566` | `#b5bcc7` | Nebentext |
| `--faint` | `#677080` | `#939cab` | Hinweise, Satznummern |
| `--line` | `#e6dfe4` | `#2a3442` | Linien |
| `--accent` | `#5e1f27` | `#ff99d8` | Links, Nummern, Hervorhebung |
| `--mark` | `#f3d9fa` | `#4a2c55` | Zielmarkierung (Lila aus der Palette) |
| `--head-bg` | `#5e1f27` | `#3d141a` | Kopfzeile (wie die Website) |
| `--foot-bg` | `#1a2431` | `#0b0f15` | Fußzeile (wie die Website) |

Kontraste (WCAG 2.2, nachgerechnet): Text `#1a2431` auf Weiß 15,7:1;
`--muted` 7,5:1; `--faint` 5,0:1 (auf `--surface` 4,7:1); Bordeaux auf Weiß
12,3:1; Text auf Zielmarkierung 12,0:1; Bordeaux auf Lila 6,6:1; Rosa auf
Bordeaux 6,3:1. Dunkel: Text 14,8:1, `--muted` 9,5:1, `--faint` 6,6:1,
Rosa 9,3:1. Fokusrahmen 3 px in Blau (11,5:1 zu Weiß) bzw. Rosa.

Dunkelmodus: folgt der Systemeinstellung; der Mond-Knopf in der Kopfzeile
schaltet um (gespeichert nur lokal im Browser, kein Cookie).

## Schriften

Lokal ausgeliefert (SIL Open Font License 1.1, aus dem Theme übernommen,
`web/assets/fonts/OFL.txt`) – keine Google Fonts.

| Rolle | Schrift | Einsatz |
|---|---|---|
| Überschriften **und Gesetzestext** | Newsreader 400–500 | wie die Überschriften der Website |
| Fließtext, Tabellen | Schibsted Grotesk | Textschrift des Themes |
| Bedienung | Instrument Sans | Knöpfe, Navigation, Nummern, Suchfeld (wie im Theme) |

Für den Gesetzestext nehme ich Newsreader statt der Website-Textschrift
Schibsted Grotesk. Newsreader ist eine Leseschrift mit optischen Größen, die
für lange Texte gemacht ist; die Grotesk ermüdet bei langen Normen schneller.
So bleibt der Normtext ruhig und bei der Hausschrift. Größe 19 px
(mobil 17 px), Zeilenabstand 1,65, Zeilenlänge höchstens 68 Zeichen
(`--measure: 68ch`), Mediävalziffern im Text, Versalziffern in Tabellen.

## Abstände, Formen

- Inhaltsbreite 1168 px (`contentSize` des Themes), Seitenrand 16 px mobil, 32 px ab 700 px
- Radien: 6 px (klein), 10 px (Suchfeld, Karten), Pillen für Knöpfe und
  Beispiel-Chips (wie „So funktioniert's“ auf der Startseite)
- Kopfzeile: Logo 46 px, Name in Newsreader, Unterzeile in Rosa – wie die Website
- Fußzeile: Dunkelblau, Links in Rosa (Kontakt, Impressum, Datenschutz →
  WordPress-Seiten)

## Screenshots

`docs/screenshots/`: Startseite, Normseite (hell, dunkel, mobil), Suche.
