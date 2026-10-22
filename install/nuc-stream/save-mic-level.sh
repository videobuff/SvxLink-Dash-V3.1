#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Start dit script met sudo.'; exit 1; }
base=/home/erik/pi3twe-nuc-stream
backup=/var/backups/pi3twe-mic-level-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup"
install -m 755 "$base/mic-level/apply" /usr/local/sbin/pi3twe-mic-level
for unit in pi3twe-audio-init.service pi3twe-svxlink.service pi3twe-nuc-stream.service; do
    dir=/etc/systemd/system/$unit.d
    install -d -m 755 "$dir"
    [[ ! -f "$dir/microphone-level.conf" ]] || cp -a "$dir/microphone-level.conf" "$backup/$unit.conf"
    if [[ $unit == pi3twe-audio-init.service ]]; then
        cat > "$dir/microphone-level.conf" <<'UNIT'
[Unit]
After=alsa-restore.service
[Service]
ExecStartPost=/usr/local/sbin/pi3twe-mic-level
UNIT
    else
        cat > "$dir/microphone-level.conf" <<'UNIT'
[Service]
# Reapply after opening capture: the codec can reset gain at that point.
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/local/sbin/pi3twe-mic-level
UNIT
    fi
done
/usr/local/sbin/pi3twe-mic-level
/usr/sbin/alsactl store Generic
systemctl daemon-reload
amixer -c Generic sget Capture
amixer -c Generic sget 'Mic Boost'
echo 'Opnamegevoeligheid opgeslagen: Capture +30 dB, Mic Boost +36 dB.'
echo 'Herstel ingesteld bij boot en starten van SvxLink of de NUC-stream. Geen herstart uitgevoerd.'
