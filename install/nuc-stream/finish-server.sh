#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
key=$(cat /home/erik/pi3twe-nuc-stream.pub)
[[ $key =~ ^[A-Za-z0-9+/]{43}=$ ]] || exit 1
config=/etc/wireguard/wg-pi3twe.conf
if ! grep -Fq "PublicKey = $key" "$config"; then
    if grep -q '^\[Peer\]' "$config"; then
        echo 'Onverwachte VPN-peer: geen wijziging uitgevoerd'; exit 1
    fi
    cp -a "$config" "$config.before-nuc-peer"
    printf '\n[Peer]\nPublicKey = %s\nAllowedIPs = 10.203.72.2/32\n' "$key" >> "$config"
fi
wg set wg-pi3twe peer "$key" allowed-ips 10.203.72.2/32
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow 51821/udp comment 'PI3TWE NUC WireGuard'
    ufw allow 8190/udp comment 'PI3TWE NUC WebRTC'
    ufw allow in on wg-pi3twe from 10.203.72.2 to 10.203.72.1 port 8555 proto tcp comment 'PI3TWE NUC audio'
fi
backup=/var/backups/pi3twe-stream-server-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup"
cp -a /etc/nginx/conf.d/stream.pa0esh.nl.conf "$backup/"
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/conf.d/stream.pa0esh.nl.conf')
s=p.read_text()
if 'location ^~ /nuc/' not in s:
    marker='    ssl_certificate_key /etc/letsencrypt/live/stream.pa0esh.nl/privkey.pem;'
    assert s.count(marker)==1, 'Onverwachte Nginx-configuratie'
    locations='''

    location = /nuc { return 301 /nuc/; }
    location ^~ /nuc/ {
        proxy_pass http://127.0.0.1:8890/pi3twe-nuc/;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 1h;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_redirect ~^/pi3twe-nuc/(.*)$ /nuc/$1;
    }
'''
    p.write_text(s.replace(marker,marker+locations))
PY
if ! nginx -t; then
    cp -a "$backup/stream.pa0esh.nl.conf" /etc/nginx/conf.d/
    echo 'Nginx-configuratie hersteld na mislukte controle'; exit 1
fi
systemctl enable --now wg-quick@wg-pi3twe.service mediamtx-pi3twe.service
systemctl reload nginx
{
    date --iso-8601=seconds
    wg show wg-pi3twe public-key
    wg show wg-pi3twe peers
    wg show wg-pi3twe latest-handshakes
    wg show wg-pi3twe transfer
    if command -v ufw >/dev/null; then ufw status; fi
    journalctl -b -u mediamtx-pi3twe.service -n 20 --no-pager
} > /home/erik/pi3twe-stream-server-diagnose.log 2>&1
chown erik:erik /home/erik/pi3twe-stream-server-diagnose.log
chmod 600 /home/erik/pi3twe-stream-server-diagnose.log
echo 'Server ingericht: VPN + eigen MediaMTX + https://stream.pa0esh.nl/nuc/'
