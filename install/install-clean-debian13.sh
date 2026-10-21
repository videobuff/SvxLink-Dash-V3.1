#!/bin/bash
# Dedicated fresh-host installer; never run this on an existing repeater.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[ "$(id -u)" = 0 ] || { echo 'Gebruik sudo.' >&2; exit 1; }
. /etc/os-release
[ "$ID" = debian ] && [ "$VERSION_ID" = 13 ] || { echo 'Debian 13 vereist.' >&2; exit 1; }
[ ! -e /opt/dashboard ] && [ ! -e /etc/pi3twe ] || { echo 'Bestaande installatie gevonden; gebruik de migratieprocedure.' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
apt-get update
mapfile -t packages < "$repo/install/build-deps.txt"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
getent group svxlink >/dev/null || groupadd --system svxlink
id svxlink >/dev/null 2>&1 || useradd --system --gid svxlink --home-dir /var/lib/svxlink --create-home --shell /usr/sbin/nologin svxlink
usermod -a -G audio,plugdev,dialout svxlink
bash "$repo/install/build-svxlink-2605.sh" "${1:-/var/tmp/pi3twe-build}"
python3 "$repo/install/provision-clean-host.py"
echo 'Geïnstalleerd, maar geen services gestart. Lees docs/BOUW-EN-BEHEER-NL.md voor inbedrijfstelling.'
