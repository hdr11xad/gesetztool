#!/usr/bin/env bash
# Normfinder – Phase 1: Bestandsaufnahme des Servers (NUR LESEND).
#
# Dieses Skript ändert nichts: keine Schreibzugriffe außer der Ausgabedatei,
# keine Neustarts, keine Paketinstallation, keine Datenbank-Schreibzugriffe.
# Passwörter/Secrets in Konfigurationen werden vor der Ausgabe geschwärzt,
# IP-Adressen in Log-Beispielen maskiert.
#
# Aufruf (root nötig, um Webserver-Konfiguration lesen zu können):
#   sudo bash bestandsaufnahme.sh [domain]  > bestandsaufnahme.txt 2>&1
# Danach bestandsaufnahme.txt durchsehen und an Claude geben.

set -u
DOMAIN="${1:-fsr-jura-halle.de}"
THEME="fsr-jura-theme-redesign"

h() { printf '\n==================== %s ====================\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
redact() {
  sed -E \
    -e 's/((password|passwd|db_pass|secret|token|api[_-]?key|auth[_-]?key|salt|private[_-]?key)[a-z_]*["'"'"']?[[:space:]=:>]+["'"'"']?)[^[:space:];"'"'"']+/\1<GESCHWÄRZT>/Ig' \
    -e "s/(define\(\s*'(DB_PASSWORD|AUTH_KEY|SECURE_AUTH_KEY|LOGGED_IN_KEY|NONCE_KEY|AUTH_SALT|SECURE_AUTH_SALT|LOGGED_IN_SALT|NONCE_SALT)'\s*,\s*)'[^']*'/\1'<GESCHWÄRZT>'/g"
}
mask_ip() {
  sed -E -e 's/\b([0-9]{1,3})\.([0-9]{1,3})\.[0-9]{1,3}\.[0-9]{1,3}\b/\1.\2.x.x/g' \
         -e 's/\b([0-9a-fA-F]{1,4}):([0-9a-fA-F]{1,4}):[0-9a-fA-F:]{3,}\b/\1:\2:…/g'
}

h "Basis"
date -Is
hostnamectl 2>/dev/null || hostname
cat /etc/os-release 2>/dev/null | grep -E '^(PRETTY_NAME|VERSION_ID)='
uname -r
echo "Uptime: $(uptime -p 2>/dev/null)"
nproc; free -h; df -hT -x tmpfs -x devtmpfs -x squashfs -x overlay
echo "Laufe als: $(id)"

h "Hosting-Panels / Container"
for p in /usr/local/psa /usr/local/ispconfig /etc/froxlor /usr/local/cpanel /opt/keyhelp; do
  [ -e "$p" ] && echo "Panel gefunden: $p"
done
if have docker; then docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>&1; fi
if have podman; then podman ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>&1; fi
have snap && snap list 2>/dev/null | grep -Ei 'nextcloud|nginx|apache' || true

h "Lauschende Ports (80/443) und Dienste"
ss -tlnp 2>/dev/null | grep -E ':(80|443|8080|8443)\b' || netstat -tlnp 2>/dev/null | grep -E ':(80|443)\b'
for s in nginx apache2 httpd caddy lighttpd traefik haproxy php-fpm php8.1-fpm php8.2-fpm php8.3-fpm php8.4-fpm; do
  st=$(systemctl is-active "$s" 2>/dev/null) && echo "$s: $st"
done

h "nginx"
if have nginx; then
  nginx -v 2>&1
  echo "--- Server-Blöcke mit $DOMAIN (Dateien):"
  grep -rlE "server_name[^;]*${DOMAIN//./\\.}" /etc/nginx 2>/dev/null
  echo "--- nginx -T (vollständige, aufgelöste Konfiguration, geschwärzt):"
  nginx -T 2>/dev/null | redact
fi

h "Apache"
if have apache2ctl || have apachectl || have httpd; then
  A=$(command -v apache2ctl || command -v apachectl || command -v httpd)
  $A -v 2>&1
  echo "--- VirtualHosts:"; $A -S 2>&1
  echo "--- Module:"; $A -M 2>&1 | tr '\n' ' '; echo
  echo "--- Konfigurationsdateien mit $DOMAIN:"
  FILES=$(grep -rlE "(ServerName|ServerAlias)[[:space:]].*${DOMAIN//./\\.}" /etc/apache2 /etc/httpd 2>/dev/null)
  for f in $FILES; do echo "##### $f"; redact < "$f"; done
  echo "--- LogFormat/CustomLog-Definitionen:"
  grep -rhE '^\s*(LogFormat|CustomLog|ErrorLog|AllowOverride)' /etc/apache2 /etc/httpd 2>/dev/null | sort | uniq -c
fi

h "Weitere Webserver"
have caddy && { caddy version; for f in /etc/caddy/Caddyfile; do [ -f "$f" ] && redact < "$f"; done; }

h "Document Root und WordPress"
ROOTS=$( { nginx -T 2>/dev/null | grep -E '^\s*root\s' | awk '{print $2}' | tr -d ';';
           grep -rhE '^\s*DocumentRoot' /etc/apache2 /etc/httpd 2>/dev/null | awk '{print $2}' | tr -d '"'; } | sort -u)
echo "Gefundene Document Roots:"; echo "$ROOTS"
WPCONF=$(find /var/www /srv /home /opt -maxdepth 5 -name wp-config.php 2>/dev/null)
echo "wp-config.php gefunden:"; echo "$WPCONF"
for c in $WPCONF; do
  d=$(dirname "$c")
  echo "##### WordPress in $d"
  grep -E "^\s*(define\(\s*'(WP_HOME|WP_SITEURL|WP_DEBUG|MULTISITE|WP_CONTENT_DIR|WP_CONTENT_URL|DISALLOW_FILE_EDIT|WP_CACHE)'|\\\$table_prefix)" "$c" | redact
  [ -f "$d/wp-includes/version.php" ] && grep -E '^\$wp_version' "$d/wp-includes/version.php"
  ls -ld "$d" "$d/wp-content" 2>/dev/null
  echo "--- $d/.htaccess:"; [ -f "$d/.htaccess" ] && redact < "$d/.htaccess" || echo "(keine)"
  echo "--- Existiert $d/normfinder ?"; ls -ld "$d/normfinder" 2>&1
  echo "--- Plugins (Verzeichnisse):"; ls "$d/wp-content/plugins" 2>/dev/null | tr '\n' ' '; echo
  echo "--- Caching-Drop-ins:"; ls "$d/wp-content/"{advanced-cache.php,object-cache.php} 2>/dev/null
done

h "WordPress-Seiten und Menüs (nur lesend, falls wp-cli vorhanden)"
if have wp; then
  for c in $WPCONF; do
    d=$(dirname "$c"); owner=$(stat -c %U "$d")
    echo "##### $d (als $owner)"
    sudo -u "$owner" wp --path="$d" option get home 2>&1
    sudo -u "$owner" wp --path="$d" option get permalink_structure 2>&1
    sudo -u "$owner" wp --path="$d" theme list --status=active 2>&1
    echo "--- Kollidiert eine Seite/ein Beitrag mit 'normfinder'?"
    sudo -u "$owner" wp --path="$d" post list --post_type=any --name=normfinder --fields=ID,post_type,post_status 2>&1
    echo "--- Menüs:"; sudo -u "$owner" wp --path="$d" menu list 2>&1
    echo "--- Seiten (Impressum/Datenschutz/Kontakt):"
    sudo -u "$owner" wp --path="$d" post list --post_type=page --post_status=publish --fields=ID,post_name,post_title 2>&1 | grep -Ei 'impressum|datenschutz|kontakt|ID'
  done
else
  echo "wp-cli nicht installiert – übersprungen."
fi

h "Theme $THEME"
TD=$(find /var/www /srv /home /opt -maxdepth 7 -type d -name "$THEME" -path '*wp-content/themes/*' 2>/dev/null | head -1)
echo "Theme-Pfad: ${TD:-nicht gefunden}"
if [ -n "$TD" ]; then
  find "$TD" -type f \( -name '*.css' -o -name '*.scss' -o -name '*.svg' -o -name '*.woff*' -o -name '*.ttf' -o -name '*.otf' -o -name '*.php' -o -name '*.js' -o -name '*.json' \) \
    -not -path '*/node_modules/*' -printf '%8s  %P\n' | sort -k2 | head -300
  echo "--- style.css Header:"; head -20 "$TD/style.css" 2>/dev/null
  echo "--- theme.json vorhanden?"; ls -l "$TD/theme.json" 2>&1
  echo "--- Externe Schrift-/CDN-Referenzen:"
  grep -rnoE '(fonts\.(googleapis|gstatic)\.com|use\.typekit|cdnjs|jsdelivr|unpkg|bunny\.net)[^"'"'"' )]*' "$TD" --include='*.php' --include='*.css' --include='*.js' --include='*.json' 2>/dev/null | head -40
  echo "--- @font-face / font-family:"
  grep -rhoE '(font-family\s*:\s*[^;]+|@font-face)' "$TD" --include='*.css' --include='*.scss' 2>/dev/null | sort | uniq -c | sort -rn | head -30
  echo "--- Lizenzdateien zu Schriften:"
  find "$TD" -iregex '.*\(ofl\|license\|lizenz\).*' -type f 2>/dev/null
fi

h "Nextcloud"
find /var/www /srv /opt -maxdepth 4 -name occ -path '*nextcloud*' 2>/dev/null
grep -rlE 'nextcloud' /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null

h "Zugriffs-Logs und Datenschutz"
echo "--- Log-Pfade und -Formate (nginx):"
nginx -T 2>/dev/null | grep -E '^\s*(access_log|error_log|log_format)' | sort | uniq -c
echo "--- Erste Felder der letzten Access-Log-Zeilen (IPs maskiert):"
for f in /var/log/nginx/*access*.log /var/log/apache2/*access*.log /var/log/httpd/*access*log; do
  [ -f "$f" ] || continue
  echo "## $f ($(wc -l < "$f") Zeilen)"; tail -n 3 "$f" | cut -c1-200 | mask_ip
  echo "   enthält vollständige IPv4-Adressen: $(tail -n 200 "$f" | grep -cE '^[0-9]{1,3}(\.[0-9]{1,3}){3} ') von 200 Zeilen"
done
echo "--- logrotate:"
for f in /etc/logrotate.d/nginx /etc/logrotate.d/apache2 /etc/logrotate.d/httpd; do [ -f "$f" ] && { echo "## $f"; cat "$f"; }; done
echo "--- fail2ban (braucht IPs im Log):"; systemctl is-active fail2ban 2>/dev/null; ls /etc/fail2ban/jail.d 2>/dev/null

h "TLS / Zertifikate"
have certbot && certbot certificates 2>/dev/null | grep -E 'Certificate Name|Domains|Expiry'
ls /etc/letsencrypt/renewal 2>/dev/null

h "Werkzeuge für Build und Update"
for t in python3 pip3 node npm git unzip curl wget xmllint rsync systemctl crontab; do
  printf '%-10s ' "$t"; command -v "$t" >/dev/null && { "$t" --version 2>&1 | head -1; } || echo "fehlt"
done
python3 -c 'import sys; print("python", sys.version.split()[0]); import venv; print("venv: ok")' 2>&1
python3 -c 'import lxml; print("lxml", lxml.__version__)' 2>&1 | tail -1
systemctl --version | head -1
echo "--- Vorhandene Timer:"; systemctl list-timers --all --no-pager 2>/dev/null | head -25
echo "--- Root-Crontab:"; crontab -l 2>&1 | grep -v '^#'

h "Mailversand vom Server"
for m in sendmail msmtp mail mailx s-nail ssmtp; do command -v "$m" >/dev/null && echo "$m: $(command -v $m)"; done
for s in postfix exim4 opensmtpd; do st=$(systemctl is-active "$s" 2>/dev/null) && echo "$s: $st"; done
[ -f /etc/msmtprc ] && { echo "/etc/msmtprc:"; redact < /etc/msmtprc; }
postconf -n 2>/dev/null | grep -E '^(relayhost|myhostname|inet_interfaces|smtp_tls_security_level)'

h "Ausgehende Verbindung zu gesetze-im-internet.de"
curl -sS -o /dev/null -w 'gii-toc.xml: HTTP %{http_code}, %{size_download} Bytes, %{time_total}s\n' --max-time 30 https://www.gesetze-im-internet.de/gii-toc.xml 2>&1
curl -sS -I --max-time 30 https://www.gesetze-im-internet.de/bgb/xml.zip 2>&1 | grep -iE '^(HTTP|etag|last-modified|content-length)'

h "Speicherplatz für Daten (geschätzt ~1–2 GB nötig)"
for p in /var/www /srv /opt /var/lib; do [ -d "$p" ] && df -h "$p" | tail -1; done

h "Fertig"
echo "Keine Änderungen vorgenommen."
