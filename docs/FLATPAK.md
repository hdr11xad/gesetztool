# Normfinder als Desktop-App (Flatpak)

Der Normfinder läuft auch als eigenständige Anwendung unter Linux, in einem
eigenen Fenster und vollständig offline. Er braucht dafür keinen Server: Die
App lädt die Gesetze selbst von gesetze-im-internet.de, erzeugt die Seiten
lokal und zeigt sie mit WebKitGTK an.

- **Erster Start:** Zuerst werden die rund 30 Kerngesetze geladen (BGB, StGB,
  GG, ZPO …). Nach etwa einer Minute ist der Normfinder benutzbar. Das übrige
  Bundesrecht (rund 6.150 Gesetze) lädt danach im Hintergrund, etwa 15–20 Minuten.
  Ein Hinweis oben im Fenster meldet, wenn alles da ist.
- **Danach:** Beim Start prüft die App höchstens einmal am Tag, ob es neue
  Fassungen gibt, und lädt nur Geändertes.
- **Platzbedarf:** etwa 2 GB im Benutzerordner
  (`~/.var/app/de.fsr_jura_halle.Normfinder/data/normfinder`).
- **Datenschutz:** Kein Tracking. Ins Internet verbindet sich die App nur
  mit gesetze-im-internet.de. Links nach außen (amtliche Fassung,
  FSR-Website) öffnen sich im normalen Browser.

## Installieren

1. Flatpak einrichten, falls noch nicht geschehen (bei Fedora, Mint u. a.
   schon vorhanden): <https://flathub.org/setup>
2. Die Datei `normfinder.flatpak` herunterladen: auf GitHub unter
   *Actions → Flatpak →* letzter erfolgreicher Lauf *→ Artifacts*
   (als ZIP, darin `normfinder.flatpak`).
3. Installieren (lädt die GNOME-Laufzeit von Flathub nach, falls nötig):

```bash
flatpak install --user normfinder.flatpak
```

4. Starten über das Anwendungsmenü („Normfinder“) oder:

```bash
flatpak run de.fsr_jura_halle.Normfinder
```

## Aktualisieren und entfernen

Neue Programmversion: neue `normfinder.flatpak` installieren wie oben.
Die Gesetzesdaten aktualisiert die App selbst.

Entfernen samt Daten:

```bash
flatpak uninstall --user --delete-data de.fsr_jura_halle.Normfinder
```

## Selbst bauen

Voraussetzung: `flatpak` und `flatpak-builder`, Flathub als Quelle.

```bash
flatpak install --user flathub org.gnome.Platform//50 org.gnome.Sdk//50
```

```bash
flatpak-builder --user --install --force-clean build-dir flatpak/de.fsr_jura_halle.Normfinder.yml
```

Als einzelne Datei zum Weitergeben:

```bash
flatpak-builder --repo=repo --force-clean build-dir flatpak/de.fsr_jura_halle.Normfinder.yml && flatpak build-bundle repo normfinder.flatpak de.fsr_jura_halle.Normfinder
```

GitHub Actions baut das Bundle bei jedem Push automatisch
(`.github/workflows/flatpak.yml`).

## Aufbau

| Datei | Aufgabe |
|---|---|
| `flatpak/de.fsr_jura_halle.Normfinder.yml` | Flatpak-Manifest (GNOME-Laufzeit 50, Rechte: Netzwerk, Wayland/X11) |
| `desktop/normfinder-desktop.py` | Fenster (GTK 4, libadwaita, WebKitGTK), lokaler Server auf 127.0.0.1 |
| `normfinder/desktop.py` | Datenverwaltung: erster Start in zwei Stufen, tägliche Prüfung, Fortschritt |
| `desktop/*.desktop`, `*.metainfo.xml`, `*.svg` | Starter, AppStream-Beschreibung, Symbol |

Die App nutzt dieselbe Pipeline wie der Server (`python3 -m normfinder`), mit
`--keep 1`, damit nur ein Stand auf der Platte liegt.

## Auf Flathub veröffentlichen (optional)

Für eine Veröffentlichung auf Flathub braucht es einen Antrag (Pull Request an
`flathub/flathub`), Screenshots in der AppStream-Datei und eine feste
Quelle (Git-Tag statt `type: dir`). Das lohnt sich, wenn die App breit
genutzt werden soll.
