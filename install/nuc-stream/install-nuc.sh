#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Start dit script met sudo'; exit 1; }
cd /home/erik/pi3twe-nuc-stream
for file in /etc/wireguard/wg-pi3twe.conf /etc/systemd/system/pi3twe-nuc-stream.service; do
    [[ ! -e $file ]] || { echo "Bestaat al: $file; niets gewijzigd"; exit 1; }
done
[[ ! -e /etc/asound.conf ]] || { echo '/etc/asound.conf bestaat al; eerst samenvoegen'; exit 1; }
[[ -f nuc.key && -f server.pub && -f /etc/pi3twe/svxlink/svxlink.conf ]] || exit 1
apt-get update
apt-get install -y wireguard-tools ffmpeg alsa-utils
modprobe wireguard
# Archive the replaced streaming configuration, including credentials, root-only.
backup=/var/backups/pi3twe-old-stream-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup"
units=(pi3twe-audio.service pi3twe-liquidsoap.service pi3twe-rf-monitor.service pi3twe-stream-watchdog.timer pi3twe-stream-watchdog.service pi3twe-rf-monitor-watchdog.timer pi3twe-rf-monitor-watchdog.service pi3twe-stream-source.service)
for unit in "${units[@]}"; do
    systemctl disable --now "$unit" || true
    if [[ -f /etc/systemd/system/$unit && ! -L /etc/systemd/system/$unit ]]; then
        mv "/etc/systemd/system/$unit" "$backup/"
    fi
    systemctl mask "$unit"
done
for file in /etc/pi3twe/darkice.cfg /etc/pi3twe/pi3twe-audio.liq /etc/pi3twe/pi3twe-rf-monitor.conf /etc/pi3twe/mediamtx-publisher.password /etc/pi3twe/mediamtx-rf-monitor-publisher.password; do
    [[ ! -f $file ]] || mv "$file" "$backup/"
done
cp -a /etc/pi3twe/svxlink/svxlink.conf "$backup/svxlink.conf"
install -m 644 asound.conf /etc/asound.conf
python3 - <<'PY'
from pathlib import Path
import re
p=Path('/etc/pi3twe/svxlink/svxlink.conf')
s=p.read_text()
parts=re.split(r'(?m)(?=^\[)',s)
found=False
for i,part in enumerate(parts):
    if part.startswith('[Rx1]'):
        parts[i],count=re.subn(r'(?m)^AUDIO_DEV=.*$', 'AUDIO_DEV=alsa:pi3twe_rx',part)
        if count != 1: raise SystemExit('Rx1 AUDIO_DEV niet eenduidig')
        found=True
if not found: raise SystemExit('Rx1 niet gevonden')
p.write_text(''.join(parts))
PY
install -d -m 700 /etc/wireguard
umask 077
{
    echo '[Interface]'
    echo 'Address = 10.203.72.2/30'
    printf 'PrivateKey = '; cat nuc.key
    echo '[Peer]'
    printf 'PublicKey = '; cat server.pub
    echo 'Endpoint = 5.2.72.156:51821'
    echo 'AllowedIPs = 10.203.72.1/32'
    echo 'PersistentKeepalive = 25'
} > /etc/wireguard/wg-pi3twe.conf
install -m 644 pi3twe-nuc-stream.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wg-quick@wg-pi3twe.service
cp -a /usr/local/sbin/pi3twe-svxlink-check "$backup/pi3twe-svxlink-check"
install -m 755 pi3twe-svxlink-check /usr/local/sbin/pi3twe-svxlink-check
systemctl restart pi3twe-svxlink.service
systemctl enable --now pi3twe-nuc-stream.service
sleep 3
systemctl is-active wg-quick@wg-pi3twe.service pi3twe-svxlink.service pi3twe-nuc-stream.service
wg show wg-pi3twe latest-handshakes
printf 'Oude streaming gearchiveerd in %s\n' "$backup"
