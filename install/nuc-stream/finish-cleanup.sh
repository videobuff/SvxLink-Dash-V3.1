#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
cd /home/erik/pi3twe-nuc-stream
backup=/var/backups/pi3twe-stream-cleanup-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup"
archive() {
    local file=$1 target="$backup$1"
    if [[ -e $file || -L $file ]]; then
        mkdir -p "$(dirname "$target")"
        mv "$file" "$target"
    fi
}
systemctl disable --now pi3twe-stream-source.path || true
archive /etc/systemd/system/pi3twe-stream-source.path
systemctl mask pi3twe-stream-source.path
for file in /usr/local/bin/pi3twe-mediamtx-publish /usr/local/bin/pi3twe-rf-monitor /usr/local/bin/pi3twe-pcm-pad /usr/local/sbin/pi3twe-apply-stream-source /usr/local/sbin/pi3twe-stream-watchdog /usr/local/sbin/pi3twe-rf-monitor-watchdog /usr/local/sbin/pi3twe-set-rf-frequency /etc/pi3twe/pi3twe-stream-source /etc/pi3twe/pi3twe-audio.liq.before-webrtc /etc/systemd/system/pi3twe-audio- /opt/dashboard/pi3twe/controller/rf_monitor.py /opt/dashboard/pi3twe/controller/stream_source.py; do
    archive "$file"
done
for file in pi3twe/runtime.py pi3twe/routes.py static/pi3twe.js templates/pi3twe.html; do
    mkdir -p "$backup/opt/dashboard/$(dirname "$file")"
    cp -a "/opt/dashboard/$file" "$backup/opt/dashboard/$file"
    # Retain existing ownership and permissions.
    cat "cleanup-files/$file" > "/opt/dashboard/$file"
done
for file in pi3twe-svxlink-check pi3twe-dashboard-control; do
    cp -a "/usr/local/sbin/$file" "$backup/$file"
    install -m 755 "cleanup-files/$file" "/usr/local/sbin/$file"
done
cp -a /etc/systemd/system/pi3twe-svxlink.service "$backup/"
install -m 644 cleanup-files/pi3twe-svxlink.service /etc/systemd/system/
cp -a /etc/systemd/system/pi3twe-audio-init.service "$backup/"
sed -i '/^Before=pi3twe-liquidsoap.service pi3twe-audio.service$/d' /etc/systemd/system/pi3twe-audio-init.service
# The old standalone controller unit must not require deleted stream files.
if [[ -f /etc/systemd/system/pi3twe.service ]]; then
    cp -a /etc/systemd/system/pi3twe.service "$backup/pi3twe.service"
    sed -i 's@ /etc/pi3twe/pi3twe-rf-monitor.conf /etc/pi3twe/pi3twe-stream-source@@' /etc/systemd/system/pi3twe.service
fi
systemctl daemon-reload
systemctl restart svxlink-dash.service
systemctl enable --now pi3twe-nuc-stream.service
systemctl restart pi3twe-nuc-stream.service
# Keep the fail-closed POWER check. Never invent a hardware state.
if /usr/bin/usbrelay | grep -q '^QAAMZ_1=[01]$'; then
    systemctl restart pi3twe-svxlink.service
else
    echo 'USB-relaismodule QAAMZ ontbreekt; SvxLink kan nog niet starten.'
fi
printf 'Oude streamingbestanden verwijderd uit actieve paden; back-up: %s\n' "$backup"
