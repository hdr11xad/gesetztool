#!/usr/bin/env bash
# Normfinder einrichten (einmalig, als root). Wiederholbar: bereits Vorhandenes bleibt.
#
# Ändert NICHT: WordPress, Theme, Datenbank, Caddy, Docker. Die Caddy-Änderung
# machst du danach selbst nach docs/SERVER.md.
#
#   sudo bash /opt/normfinder/deploy/install.sh
set -euo pipefail

APP=/opt/normfinder
DATA=/srv/normfinder
ENVFILE=/etc/normfinder.env

[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
[ -f "$APP/normfinder/__main__.py" ] || { echo "Code nicht unter $APP gefunden (erst git clone, siehe docs/SERVER.md)."; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11 oder neuer nötig."; exit 1; }

echo "1/4 Systembenutzer normfinder"
if ! id normfinder >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA" --no-create-home --shell /usr/sbin/nologin normfinder
  echo "    angelegt"
else
  echo "    vorhanden"
fi

echo "2/4 Datenverzeichnis $DATA"
install -d -o normfinder -g normfinder -m 0755 "$DATA" "$DATA/cache" "$DATA/releases" "$DATA/logs"
echo "    ok (Caddy liest daraus nur, Schreibrechte hat nur normfinder)"

echo "3/4 Einstellungen $ENVFILE"
if [ ! -f "$ENVFILE" ]; then
  install -o root -g normfinder -m 0640 "$APP/deploy/normfinder.env.example" "$ENVFILE"
  echo "    angelegt – bitte NORMFINDER_PUSH_URL eintragen (Uptime Kuma)"
else
  echo "    vorhanden, unverändert"
fi

echo "4/4 systemd-Timer"
for u in normfinder-update.service normfinder-update.timer; do
  if [ -f "/etc/systemd/system/$u" ] && ! cmp -s "$APP/deploy/$u" "/etc/systemd/system/$u"; then
    cp "/etc/systemd/system/$u" "/etc/systemd/system/$u.bak-$(date +%Y%m%d%H%M%S)"
    echo "    Sicherung von $u angelegt"
  fi
  install -m 0644 "$APP/deploy/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now normfinder-update.timer >/dev/null
systemctl list-timers normfinder-update.timer --no-pager | head -3

cat <<EOF

Fertig. Nächste Schritte (docs/SERVER.md):
  1. Ersten Lauf starten (dauert beim ersten Mal 30–60 Minuten):
       sudo systemctl start --no-block normfinder-update.service
       journalctl -u normfinder-update -f
  2. Danach Caddy erweitern (Volume + Konfigurationsblock), Abschnitt 4 der Anleitung.
EOF
