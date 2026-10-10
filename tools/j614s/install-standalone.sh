#!/bin/sh
# SPDX-License-Identifier: MIT
# Run from macOS Recovery after the identical payload passed the USB test.
# Usage: sh install-standalone.sh /path/gravity-standalone.bin --install
set -eu
[ "$#" = 2 ] && [ "$2" = --install ] || {
    echo 'Usage: sh install-standalone.sh /path/gravity-standalone.bin --install'; exit 2;
}
[ "$(uname -s)" = Darwin ]
[ "$(sysctl -n hw.model)" = Mac16,8 ]
payload=$1
[ -s "$payload" ] && [ -s "$payload.sha256" ]
directory=$(dirname "$payload")
if command -v shasum >/dev/null 2>&1; then
    (cd "$directory" && shasum -a 256 -c "$(basename "$payload").sha256")
elif command -v openssl >/dev/null 2>&1; then
    expected=$(awk 'NR == 1 {print $1}' "$payload.sha256")
    actual=$(openssl dgst -sha256 "$payload" | awk '{print $NF}')
    [ -n "$expected" ] && [ "$actual" = "$expected" ] || {
        echo 'STOP: standalone payload checksum mismatch'; exit 1;
    }
    echo 'Standalone payload SHA256: OK'
else
    echo 'STOP: neither shasum nor openssl is available; checksum not verified.'
    exit 1
fi
volume='/Volumes/Gravity Linux J614s Dev'
[ -d "$volume" ]
info=$(diskutil info -plist "$volume")
uuid=$(printf '%s' "$info" | plutil -extract VolumeUUID raw -o - -)
[ "$uuid" = 7BB3DC62-3D93-4B51-8D8B-A922DE5E5CCB ] || {
    echo 'STOP: Gravity System volume UUID mismatch'; exit 1;
}
echo 'Installing the tested standalone payload into the Gravity boot entry.'
kmutil configure-boot -c "$payload" --raw --entry-point 2048 --lowest-virtual-address 0 -v "$volume"
echo 'Installed. Shut down and choose Gravity Linux J614s Dev in Startup Options.'
