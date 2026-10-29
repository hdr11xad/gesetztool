# Normfinder in WordPress verlinken

Der Normfinder ist eine eigenständige Seite neben WordPress. In WordPress kommen
nur ein Menüpunkt und eine Kachel dazu. Beides ist in fünf Minuten erledigt und
lässt sich jederzeit wieder entfernen.

## Menüpunkt

1. WordPress-Admin → **Design → Editor → Navigation** (Block-Theme).
   Alternativ in der Kopfzeile das Navigationsmenü anklicken und bearbeiten.
2. Im Menü „Studium“ (oder auf oberster Ebene) **+** → **Benutzerdefinierter Link**.
3. URL: `/normfinder/` · Beschriftung: `Normfinder`
4. Speichern.

Der Link ist relativ und funktioniert damit auch nach einem Domainwechsel.

## Kachel bei „Nützliche Links“ auf der Startseite

Die Kacheln sind Bild-Blöcke mit 64×64-Symbolen (`assets/images/links/*.svg`).
Für den Normfinder liegt ein passendes Symbol bereit:
[`docs/wordpress/normfinder.svg`](wordpress/normfinder.svg) – weißes § auf
Bordeaux, in Newsreader gesetzt, im Stil der übrigen Kacheln.

1. Symbol in die Mediathek hochladen: WordPress-Admin → **Medien → Datei hinzufügen**,
   `normfinder.svg` auswählen. (Falls SVG-Uploads gesperrt sind: die Datei per
   SFTP nach `wp-content/themes/fsr-jura-theme-redesign/assets/images/links/`
   kopieren – das ist eine Theme-Datei, also vorher kurz absprechen.)
2. **Seiten → Startseite** bearbeiten, zum Abschnitt „Nützliche Links“ scrollen.
3. Eine vorhandene Kachel (z. B. „Klausurenpool“) markieren → **⋮ → Duplizieren**.
4. In der Kopie: Bild ersetzen → `normfinder.svg`; Alternativtext `Normfinder`;
   Link `/normfinder/` (ohne „In neuem Tab öffnen“, es ist eine eigene Seite);
   Bildunterschrift `Normfinder`.
5. Kachel an die gewünschte Stelle ziehen (z. B. direkt nach StudIP), **Aktualisieren**.

Als HTML (Ansicht „Als HTML bearbeiten“), passend zu den übrigen Kacheln:

```html
<figure class="wp-block-image"><a href="/normfinder/"><img src="/wp-content/themes/fsr-jura-theme-redesign/assets/images/links/normfinder.svg" alt="Normfinder"/></a><figcaption class="wp-element-caption">Normfinder</figcaption></figure>
```

## Datenschutzerklärung

Der Normfinder setzt keine Cookies, nutzt kein Tracking und lädt nichts von
fremden Servern; ein Consent-Banner ist dafür nicht nötig. Optional ein Satz in
der Datenschutzerklärung:

> **Normfinder.** Unter /normfinder/ stellen wir Bundesgesetze zum Nachschlagen
> bereit. Dabei werden keine Cookies gesetzt und keine Zugriffe protokolliert.
> Die Suche läuft vollständig im Browser; Suchbegriffe werden nicht an uns
> übertragen. Lokal im Browser wird allenfalls die Wahl zwischen hellem und
> dunklem Farbschema gespeichert.
