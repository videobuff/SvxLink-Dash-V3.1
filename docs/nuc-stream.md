# NUC-audiostream

Controller J3 → NUC linker opnamekanaal → ALSA `pi3twe_rx` → FFmpeg/Opus →
WireGuard → MediaMTX → HTTPS/WebRTC.

- Server: 5.2.72.156, WireGuard UDP 51821.
- Tunneladressen: server 10.203.72.1, NUC 10.203.72.2.
- RTSP-ingang: 10.203.72.1:8555/pi3twe-nuc, uitsluitend via VPN.
- WebRTC: localhost HTTP 8890, publieke ICE UDP 8190.
- Luisteradres: https://stream.pa0esh.nl/nuc/?muted=false&autoplay=false
- Microfoon: Capture +30 dB, Mic Boost +36 dB, bron Mic.
- ALSA wordt opgeslagen; start-hooks herstellen de gevoeligheid na openen van capture.

De configuratiebestanden staan onder `install/nuc-stream`. De installatiescripts
zijn migratiehulpmiddelen voor deze bestaande NUC en server; ze veronderstellen
het werkpad `/home/erik/pi3twe-nuc-stream`, gegenereerde sleutels en de bestaande
Nginx-vhost. Het zijn geen algemene schone-installatie scripts. Privésleutels
staan uitsluitend lokaal en horen niet in Git.

Oude NUC-streamdiensten zijn gemaskeerd, de oude actieve scripts/configuratie
zijn verplaatst naar root-only back-ups in /var/backups/pi3twe-stream-*.
De bestaande server-MediaMTX is behouden naast de nieuwe instance.

Gecontroleerd: VPN-verkeer, Opus-ontvangst op de server, HTTP 200 voor luisterpagina
en reader.js, actieve SvxLink/stream/dashboard en microfoonniveaus.
Browseraudio is nog door gebruiker te bevestigen.
