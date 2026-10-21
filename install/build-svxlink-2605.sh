#!/bin/bash
# Build the pinned engine. Run on Debian 13 after installing build-deps.txt.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
work=${1:?Usage: build-svxlink-2605.sh BUILD_DIRECTORY}
mkdir -p "$work"
work=$(realpath "$work")
source_dir="$work/svxlink"
if [ ! -d "$source_dir/.git" ]; then
    git clone --branch 26.05.2 --depth 1 https://github.com/sm0svx/svxlink.git "$source_dir"
fi
[ "$(git -C "$source_dir" rev-parse HEAD)" = 595cf9bb3325be753d05b219bdd39feab6a22b33 ] || { echo 'Unexpected SvxLink source revision' >&2; exit 1; }
cmake -S "$source_dir/src" -B "$work/build" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DLIB_INSTALL_DIR=/usr/local/lib -DSYSCONF_INSTALL_DIR=/etc \
    -DLOCAL_STATE_DIR=/var -DUSE_QT=OFF -DINTERNAL_SAMPLE_RATE=16000 \
    -DDO_INSTALL_CHOWN=OFF
cmake --build "$work/build" --parallel "${BUILD_JOBS:-2}"
cmake --install "$work/build"
printf '/usr/local/lib\n/usr/local/lib/svxlink\n' > /etc/ld.so.conf.d/pi3twe-svxlink.conf
ldconfig
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python3 "$repo/scripts/build-pi3twe-logic.py" --source "$source_dir" --headers / --build-config "$work/build"
