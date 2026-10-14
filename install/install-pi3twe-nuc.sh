#!/bin/bash
set -euo pipefail

DASH_SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SVX_STAGE=${1:?Usage: install-pi3twe-nuc.sh SVXLINK_STAGED_INSTALL PI3TWE_PLUGIN}
NATIVE_PLUGIN=${2:?Supply the ABI-matched Pi3tweLogic.so}
REPO=/opt/pi3twe/pi3twe-controller

test -d "$DASH_SOURCE"
test -x "$SVX_STAGE/bin/svxlink"
test -f "$NATIVE_PLUGIN"
id svxlink >/dev/null

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-flask python3-jinja2 python3-werkzeug python3-psutil

install -d -o root -g root -m 0755 /opt/dashboard
if [ -f /opt/dashboard/app.py ]; then
    install -d -o root -g root -m 0755 /var/backups/pi3twe-svxlink-dashboard
    cp -a /opt/dashboard "/var/backups/pi3twe-svxlink-dashboard/dashboard-$(date +%Y%m%d-%H%M%S)"
fi
cp -a "$DASH_SOURCE/." /opt/dashboard/
chown -R svxlink:svxlink /opt/dashboard
chmod -R u+rwX,g+rwX,o+rX /opt/dashboard
install -d -o svxlink -g svxlink -m 0775 /opt/dashboard/backups /opt/dashboard/config /var/lib/svxlink-dash/sounds/idents /var/lib/svxlink-dash/backups
install -d -o svxlink -g svxlink -m 0775 /usr/share/svxlink/events.d/local

# Place the upstream release under /usr/local so Debian's package remains recoverable.
cp -a "$SVX_STAGE/." /usr/local/
install -d -o root -g root -m 0755 /usr/local/lib/pi3twe-svxlink
install -o root -g root -m 0644 "$NATIVE_PLUGIN" /usr/local/lib/pi3twe-svxlink/Pi3tweLogic.so
sed -e 's|"/usr/bin/svxlink",|"/usr/local/bin/svxlink",|' \
    "$DASH_SOURCE/install/pi3twe-svxlink-ptt" >/tmp/pi3twe-svxlink-ptt
install -o root -g root -m 0755 /tmp/pi3twe-svxlink-ptt /usr/local/sbin/pi3twe-svxlink-ptt
install -d -o root -g root -m 0755 /usr/local/share/pi3twe-svxlink
install -o root -g root -m 0644 "$DASH_SOURCE/install/pi3twe-svxlink-events/events.tcl" /usr/local/share/pi3twe-svxlink/events.tcl
for helper in pi3twe-svxlink-control pi3twe-svxlink-mode-check pi3twe-svxlink-audio-init pi3twe-svxlink-check; do
    install -o root -g root -m 0755 "$DASH_SOURCE/install/$helper" "/usr/local/sbin/$helper"
done
rm -f /tmp/pi3twe-svxlink-ptt
python3 - <<'PY'
import hashlib, json
from pathlib import Path
files = (Path('/usr/local/bin/svxlink'), Path('/usr/local/lib/svxlink/RepeaterLogic.so'))
Path('/usr/local/lib/pi3twe-svxlink/manifest.json').write_text(
    json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2) + '\n'
)
PY
printf '/usr/local/lib\n/usr/local/lib/svxlink\n' >/etc/ld.so.conf.d/pi3twe-svxlink.conf
ldconfig
install -d -o root -g root -m 0755 /etc/systemd/system/pi3twe-svxlink.service.d
cat >/etc/systemd/system/pi3twe-svxlink.service.d/svxlink26.conf <<'EOF'
[Service]
Environment=LD_LIBRARY_PATH=/usr/local/lib/svxlink:/usr/local/lib
EOF

# The dashboard edits the bridge's source configuration; it cannot write GPIO/serial PTT settings.
install -d -o svxlink -g svxlink -m 0775 /etc/pi3twe/svxlink /etc/pi3twe/svxlink/svxlink.d
chown -R svxlink:svxlink /etc/pi3twe/svxlink
chmod 0775 /etc/pi3twe/svxlink
chmod 0664 /etc/pi3twe/svxlink/svxlink.conf

install -o root -g root -m 0755 /dev/stdin /usr/local/sbin/pi3twe-dashboard-control <<'EOF'
#!/bin/sh
set -eu
case "${1:-}" in
  restart-all) /usr/bin/systemctl restart pi3twe-svxlink.service svxlink-dash.service ;;
  reboot) /usr/bin/systemctl reboot ;;
  shutdown) /usr/bin/systemctl poweroff ;;
  *) echo "Gebruik: pi3twe-dashboard-control {restart-all|reboot|shutdown}" >&2; exit 2 ;;
esac
EOF

install -o root -g root -m 0644 "$DASH_SOURCE/install/svxlink-dash.service" /etc/systemd/system/svxlink-dash.service
cat >/etc/sudoers.d/svxlink-dash <<'EOF'
svxlink ALL=(root) NOPASSWD: \
    /usr/local/sbin/pi3twe-svxlink-control start, \
    /usr/local/sbin/pi3twe-svxlink-control stop, \
    /usr/local/sbin/pi3twe-svxlink-control restart, \
    /usr/local/sbin/pi3twe-dashboard-control restart-all, \
    /usr/local/sbin/pi3twe-dashboard-control reboot, \
    /usr/local/sbin/pi3twe-dashboard-control shutdown
EOF
chmod 0440 /etc/sudoers.d/svxlink-dash
visudo -cf /etc/sudoers.d/svxlink-dash

systemctl daemon-reload
systemctl enable svxlink-dash.service
systemctl restart pi3twe-svxlink.service
systemctl restart svxlink-dash.service
systemctl --no-pager --full is-active pi3twe-svxlink.service svxlink-dash.service
"/usr/local/bin/svxlink" --version
