#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Start met sudo bash install-server.sh'; exit 1; }
# A separate endpoint for the new NUC stream. Existing streams are retained
# until reception of the replacement has been verified.
for file in /etc/wireguard/wg-pi3twe.conf /etc/mediamtx/pi3twe-nuc.yml /etc/systemd/system/mediamtx-pi3twe.service; do
    [[ ! -e $file ]] || { echo "Bestaat al: $file; niets gewijzigd"; exit 1; }
done
command -v /usr/local/bin/mediamtx >/dev/null
id mediamtx >/dev/null
for port in 51821 8555 8890 8190; do
    if ss -H -ltnu "sport = :$port" | read -r _; then
        echo "Poort $port is bezet; afgebroken"; exit 1
    fi
done
apt-get update
apt-get install -y wireguard-tools
modprobe wireguard
install -d -m 700 /etc/wireguard
umask 077
wg genkey > /etc/wireguard/pi3twe-server.key
wg pubkey < /etc/wireguard/pi3twe-server.key > /home/erik/pi3twe-stream-server.pub
chmod 644 /home/erik/pi3twe-stream-server.pub
{
    echo '[Interface]'
    echo 'Address = 10.203.72.1/30'
    echo 'ListenPort = 51821'
    printf 'PrivateKey = '; cat /etc/wireguard/pi3twe-server.key
} > /etc/wireguard/wg-pi3twe.conf
install -d -m 750 -o root -g mediamtx /etc/mediamtx
cat > /etc/mediamtx/pi3twe-nuc.yml <<'YAML'
logLevel: info
rtsp: true
rtspAddress: 10.203.72.1:8555
rtspTransports: [tcp]
rtmp: false
hls: false
srt: false
webrtc: true
webrtcAddress: 127.0.0.1:8890
webrtcLocalUDPAddress: :8190
webrtcAdditionalHosts: [5.2.72.156]
authMethod: internal
authInternalUsers:
  - user: any
    ips: [10.203.72.2/32]
    permissions:
      - action: publish
        path: pi3twe-nuc
  - user: any
    ips: []
    permissions:
      - action: read
        path: pi3twe-nuc
paths:
  pi3twe-nuc:
    source: publisher
YAML
chmod 640 /etc/mediamtx/pi3twe-nuc.yml
chown root:mediamtx /etc/mediamtx/pi3twe-nuc.yml
cat > /etc/systemd/system/mediamtx-pi3twe.service <<'UNIT'
[Unit]
Description=PI3TWE NUC audio via eigen VPN
Requires=wg-quick@wg-pi3twe.service
After=network-online.target wg-quick@wg-pi3twe.service
[Service]
User=mediamtx
Group=mediamtx
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx/pi3twe-nuc.yml
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now wg-quick@wg-pi3twe.service
systemctl enable --now mediamtx-pi3twe.service
systemctl is-active wg-quick@wg-pi3twe.service mediamtx-pi3twe.service
echo 'Server voorbereid. NUC-peer en audiozender worden hierna aangesloten.'
echo 'Eventuele firewall moet UDP 51821 (VPN) en UDP 8190 (WebRTC) toelaten.'
