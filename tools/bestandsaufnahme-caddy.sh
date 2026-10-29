#!/usr/bin/env bash
# Normfinder – Phase 1b: Caddy-Konfiguration und Docker-Logs (NUR LESEND).
#   sudo bash bestandsaufnahme-caddy.sh > bestandsaufnahme-caddy.txt 2>&1

set -u
h() { printf '\n==================== %s ====================\n' "$*"; }
redact() {
  sed -E -e 's/((password|passwd|db_pass|secret|token|api[_-]?key|auth[_-]?key|salt|private[_-]?key|hashed_password|basicauth)[a-z_]*["'"'"']?[[:space:]=:>]+["'"'"']?)[^[:space:];"'"'"']+/\1<GESCHWÄRZT>/Ig' \
         -e 's/(\$2[aby]\$[0-9]+\$)[^[:space:]]+/\1<GESCHWÄRZT>/g'
}
mask_ip() {
  sed -E -e 's/\b([0-9]{1,3})\.([0-9]{1,3})\.[0-9]{1,3}\.[0-9]{1,3}\b/\1.\2.x.x/g' \
         -e 's/\b([0-9a-fA-F]{1,4}):([0-9a-fA-F]{1,4}):[0-9a-fA-F:]{3,}\b/\1:\2:…/g'
}
compose_dir() { docker inspect "$1" --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null; }

h "Stacks"
ls -la /opt/stacks

for c in caddy website-wordpress; do
  h "Container $c"
  docker inspect "$c" --format 'Image: {{.Config.Image}}
Netzwerkmodus: {{.HostConfig.NetworkMode}}
Neustart: {{.HostConfig.RestartPolicy.Name}}
Log-Treiber: {{.HostConfig.LogConfig.Type}} {{json .HostConfig.LogConfig.Config}}
Mounts:{{range .Mounts}}
  {{.Source}} -> {{.Destination}} ({{if .RW}}rw{{else}}ro{{end}}){{end}}' 2>&1
  d=$(compose_dir "$c")
  echo "Compose-Verzeichnis: ${d:-unbekannt}"
  if [ -n "$d" ]; then
    ls -la "$d"
    for f in "$d"/compose.yaml "$d"/compose.yml "$d"/docker-compose.yml "$d"/docker-compose.yaml "$d"/.env; do
      [ -f "$f" ] && { echo "##### $f"; redact < "$f"; }
    done
  fi
done

h "Caddyfile (aus dem laufenden Container)"
docker exec caddy sh -c 'cat /etc/caddy/Caddyfile; for f in /etc/caddy/*.caddy /etc/caddy/conf.d/* ; do [ -f "$f" ] && { echo "##### $f"; cat "$f"; }; done' 2>&1 | redact
docker exec caddy caddy version 2>&1

h "Docker-Daemon (Log-Standard)"
cat /etc/docker/daemon.json 2>&1

h "Speichern Logs IP-Adressen?"
for c in caddy website-wordpress; do
  f=$(docker inspect "$c" --format '{{.LogPath}}' 2>/dev/null)
  [ -n "$f" ] && [ -f "$f" ] && echo "$c: Logdatei $(du -h "$f" | cut -f1), älteste Zeile: $(head -c 300 "$f" | grep -oE '"time":"[^"]+"' | head -1)"
  echo "--- letzte 3 Zeilen von $c (IPs maskiert):"
  docker logs --tail 3 "$c" 2>&1 | cut -c1-220 | mask_ip
  echo "--- Zeilen mit vollständiger IPv4 unter den letzten 200: $(docker logs --tail 200 "$c" 2>&1 | grep -cE '\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b')"
done
echo "--- Von Caddy geschriebene Logdateien:"
docker exec caddy sh -c 'ls -la /var/log/caddy /data/caddy/logs 2>/dev/null' 2>&1

h "Uptime Kuma (für Fehlermeldungen nutzbar?)"
docker inspect uptime-kuma --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' 2>&1

h "Fertig"
echo "Keine Änderungen vorgenommen."
