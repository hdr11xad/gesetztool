# Normfinder auf dem Server einrichten

Diese Anleitung führt Schritt für Schritt durch die Einrichtung auf dem FSR-Server
(Debian 13, Docker, Caddy als Webserver vor WordPress und Nextcloud).
Jeder Schritt sagt, was er verändert. WordPress, das Theme und die Datenbank
werden **nicht** angefasst.

Überblick:

```
gesetze-im-internet.de ──(nachts, systemd-Timer)──► /srv/normfinder/releases/<Stand>/
                                                      ▲ current (Symlink, atomar umgeschaltet)
Browser ──► Caddy ──► /normfinder/*  → statische Dateien aus /srv/normfinder/current
                  └─► alles andere   → WordPress (wie bisher)
```

| Was | Wo |
|---|---|
| Programmcode (dieses Repository) | `/opt/normfinder` |
| Daten: Cache, Stände, Logs | `/srv/normfinder` (Benutzer `normfinder`) |
| Einstellungen | `/etc/normfinder.env` |
| Zeitsteuerung | `normfinder-update.timer` (systemd) |
| Auslieferung | Caddy-Container, Volume `/srv/normfinder` nur lesend |

---

## 1. Code holen

Legt `/opt/normfinder` an. Sonst ändert sich nichts.

```bash
sudo git clone https://github.com/hdr11xad/gesetztool.git /opt/normfinder
```

## 2. Einrichtungsskript ausführen

Legt den Systembenutzer `normfinder`, das Datenverzeichnis `/srv/normfinder`,
die Einstellungsdatei `/etc/normfinder.env` und den systemd-Timer an.
Das Skript kann gefahrlos mehrfach laufen; bestehende Einstellungen bleiben.

```bash
sudo bash /opt/normfinder/deploy/install.sh
```

## 3. Fehlermeldungen über Uptime Kuma

Auf dem Server läuft bereits Uptime Kuma. Darüber meldet der Normfinder jeden
nächtlichen Lauf; Kuma schickt dir dann über die dort eingerichteten
Benachrichtigungen (z. B. Mail) eine Nachricht, wenn etwas schiefgeht – oder
wenn sich der Normfinder gar nicht meldet.

1. Uptime Kuma öffnen (Dockge oder `http://127.0.0.1:3001` per SSH-Tunnel).
2. *Neuen Monitor hinzufügen* → Typ **Push**, Name „Normfinder Update“.
3. **Heartbeat-Intervall: 93600 Sekunden** (26 Stunden), Wiederholungen: 0.
4. Benachrichtigung (Mail) auswählen, speichern.
5. Die angezeigte Push-URL kopieren. Den Teil nach `/api/push/` brauchst du gleich.

Push-URL eintragen (Kuma läuft auf demselben Server, daher `127.0.0.1:3001`):

```bash
sudo nano /etc/normfinder.env
```

Dort die Zeile ausfüllen, zum Beispiel:

```
NORMFINDER_PUSH_URL=http://127.0.0.1:3001/api/push/AbCdEf123
```

> Hat Uptime Kuma noch keine Mail-Benachrichtigung? Unter *Einstellungen →
> Benachrichtigungen* eine SMTP-Benachrichtigung anlegen (z. B. mit dem
> Mailkonto des FSR). Alternativ kann der Normfinder direkt per `sendmail`
> mailen (`NORMFINDER_MAIL=`), dafür bräuchte der Server aber einen
> eingerichteten Mailversand, den es derzeit nicht gibt.

## 4. Ersten Lauf starten

Der erste Lauf lädt alle rund 6.100 Gesetze und Verordnungen (ca. 300 MB) und
erzeugt die Seiten. Das dauert beim ersten Mal 30–60 Minuten. Die Website ist
währenddessen nicht betroffen (niedrige CPU- und Plattenpriorität).

```bash
sudo systemctl start --no-block normfinder-update.service
```

Fortschritt mitlesen (beenden mit Strg+C, der Lauf geht weiter):

```bash
journalctl -u normfinder-update -f
```

Fertig, wenn dort `Umgeschaltet auf …` steht. Kontrolle:

```bash
cd /opt/normfinder && sudo -u normfinder python3 -m normfinder --root /srv/normfinder status
```

## 5. Caddy erweitern

Erst jetzt wird der Normfinder öffentlich. Zwei Änderungen am Caddy-Stack:
ein zusätzliches Volume (nur lesend) und ein Block in der Caddy-Konfiguration.

### 5.1 Caddy-Stack finden und sichern

Verzeichnis des Caddy-Stacks anzeigen (vermutlich `/opt/stacks/caddy`):

```bash
docker inspect caddy --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
```

Im Folgenden steht `CADDY=/opt/stacks/caddy` – ersetze es, falls der Befehl
etwas anderes zeigt. Sicherung des ganzen Stack-Verzeichnisses:

```bash
sudo cp -a /opt/stacks/caddy /opt/stacks/caddy.bak-$(date +%Y%m%d-%H%M)
```

Welche Dateien gibt es, und wo liegt das Caddyfile?

```bash
ls -la /opt/stacks/caddy
```

```bash
docker inspect caddy --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

### 5.2 Volume ergänzen

In `compose.yaml` (oder `docker-compose.yml`) beim Dienst `caddy` unter
`volumes:` eine Zeile ergänzen – gern auch über Dockge (*Bearbeiten*):

```yaml
      - /srv/normfinder:/srv/normfinder:ro
```

### 5.3 Konfigurationsblock einfügen

Den Inhalt von `/opt/normfinder/deploy/Caddyfile.normfinder` in den Block
`fsr-jura-halle.de { … }` des Caddyfiles kopieren, **vor** die Zeile mit
`reverse_proxy` zu WordPress. Ergebnis (schematisch):

```
fsr-jura-halle.de {
	# ---------- Normfinder … ----------
	redir /normfinder /normfinder/ 308
	handle /normfinder/* {
		…
	}
	handle_errors 404 { … }
	# ---------- Ende Normfinder ----------

	reverse_proxy 127.0.0.1:8081     # ← bestehende WordPress-Zeile, unverändert
}
```

Hat der Block schon ein eigenes `handle_errors`, sag mir Bescheid – dann
führen wir beides zusammen.

### 5.4 Prüfen und aktivieren

Konfiguration prüfen, bevor etwas live geht (ändert nichts):

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Erwartet: `Valid configuration`. Bei einer Fehlermeldung nichts weiter tun und
mir die Meldung schicken.

Container mit dem neuen Volume neu erstellen (kurze Unterbrechung von wenigen
Sekunden für alle Seiten, auch Nextcloud):

```bash
cd /opt/stacks/caddy && sudo docker compose up -d
```

### 5.5 Testen

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://fsr-jura-halle.de/normfinder/
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://fsr-jura-halle.de/normfinder/bgb/573
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://fsr-jura-halle.de/normfinder/gibt-es-nicht
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://fsr-jura-halle.de/
```

Erwartet: `200`, `200`, `404`, `200`. Zusätzlich im Browser
https://fsr-jura-halle.de/normfinder/ öffnen und „573 bgb“ eingeben.

### 5.6 Zurück, falls etwas nicht stimmt

Sicherung zurückspielen und Container neu erstellen:

```bash
sudo rsync -a --delete /opt/stacks/caddy.bak-DATUM/ /opt/stacks/caddy/ && cd /opt/stacks/caddy && sudo docker compose up -d
```

(`DATUM` durch den Namen der Sicherung aus 5.1 ersetzen; ohne `rsync` geht es
mit `cp -a` und vorherigem Löschen.)

---

## Betrieb

### Nächtliches Update

Der Timer startet jede Nacht gegen 3:40 Uhr (± 20 Minuten):

1. Inhaltsverzeichnis und nur **geänderte** Archive laden (ETag/Last-Modified,
   eine Verbindung, max. ~3–10 Anfragen pro Sekunde, Timeouts, bis zu
   4 Wiederholungen mit wachsender Pause).
2. Hat sich nichts geändert (weder Daten noch Code), bleibt alles, wie es ist.
3. Sonst neuen Stand in `releases/<Zeit>.tmp` erzeugen. Unveränderte Dateien
   werden aus dem vorherigen Stand hart verlinkt – das spart Platz.
4. Prüfen: mindestens 4.000 Gesetze und 80.000 Normen, Stichproben (§ 573 BGB,
   Art. 1 GG, § 263 StGB, § 29 ZPO), alle Kerngesetze vorhanden, nicht mehr als
   5 % weniger als im Vorstand.
5. Nur wenn alles stimmt: Symlink `current` atomar umschalten. Sonst bleibt der
   alte Stand online, der fehlgeschlagene liegt als `releases/<Zeit>.failed`
   zur Analyse da, und Uptime Kuma meldet den Fehler.
6. Die letzten drei Stände bleiben erhalten.

Wann läuft der Timer als Nächstes?

```bash
systemctl list-timers normfinder-update.timer
```

Sofort aktualisieren:

```bash
sudo systemctl start --no-block normfinder-update.service
```

### Logs

Ausgaben jedes Laufs stehen im systemd-Journal und zusätzlich in
`/srv/normfinder/logs/update-JJJJ-MM-TT.log` (30 Tage aufbewahrt).

```bash
journalctl -u normfinder-update --since yesterday
```

### Rückfall auf den vorherigen Stand

```bash
cd /opt/normfinder && sudo -u normfinder python3 -m normfinder --root /srv/normfinder rollback
```

Wirkt sofort, ohne Neustart von Caddy.

### Code aktualisieren

```bash
cd /opt/normfinder && sudo git pull
```

Der nächste Lauf erkennt den geänderten Code und erzeugt alles neu. Sofort:

```bash
sudo systemctl start --no-block normfinder-update.service
```

### Speicherbedarf

Cache ca. 300 MB, ein vollständiger Stand ca. 2–3 GB; weitere Stände belegen
dank harter Links nur den Platz geänderter Dateien.

---

## Datenschutz: Server-Logs

**Normfinder:** Der Caddy-Block enthält `log_skip`. Aufrufe unter
`/normfinder/` werden also nicht protokolliert, und sie erreichen WordPress
gar nicht. Suchanfragen verlassen den Browser ohnehin nicht.

**Übrige Website:** Die Bestandsaufnahme zeigt, dass WordPress in einem
Docker-Container mit Apache läuft. Das offizielle WordPress-Image schreibt
Zugriffe mit **vollständiger IP-Adresse** in das Docker-Log
(`docker logs website-wordpress`), und Docker hebt diese Logs ohne
Begrenzung auf. Prüfen:

```bash
docker logs --tail 3 website-wordpress 2>&1 | cut -c1-80
```

```bash
docker inspect website-wordpress caddy --format '{{.Name}}: {{.HostConfig.LogConfig.Type}} {{.HostConfig.LogConfig.Config}}'
```

```bash
docker exec caddy grep -n "log" /etc/caddy/Caddyfile
```

Vorschlag (bitte erst nach Rücksprache umsetzen):

1. **Aufbewahrung begrenzen:** In den Compose-Dateien von `website-wordpress`
   und `caddy` je Dienst
   ```yaml
       logging:
         driver: json-file
         options:
           max-size: "10m"
           max-file: "3"
   ```
   Damit bleiben höchstens ~30 MB je Container, typischerweise wenige Tage.
2. **IP-Adressen kürzen:** Falls Caddy Zugriffe protokolliert (`log` im
   Caddyfile), die Adressen kürzen – IPv4 auf /16, IPv6 auf /32:
   ```
   log {
   	format filter {
   		request>remote_ip ip_mask 16 32
   		request>client_ip ip_mask 16 32
   	}
   }
   ```
   (Mit `caddy validate` prüfen; ältere Caddy-Versionen verlangen die Form
   `format filter { wrap json  fields { … } }`.)
3. **WordPress-Zugriffslog abschalten**, weil Caddy (gekürzt) bereits
   protokolliert: Im WordPress-Container eine Datei
   `/etc/apache2/conf-enabled/zz-nolog.conf` mit `CustomLog /dev/null common`
   per Volume einbinden. Fehlerlogs bleiben erhalten.

fail2ban läuft nicht, braucht also keine vollständigen IP-Adressen.
