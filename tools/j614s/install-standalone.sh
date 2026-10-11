#!/bin/sh
# SPDX-License-Identifier: MIT
# Run from macOS Recovery after the identical payload passed the USB test.
# Usage: sh install-standalone.sh /path/gravity-standalone.bin --install
set -eu
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
[ "$(id -u)" = 0 ] || { echo "Run in Recovery Terminal."; exit 1; }
[ "$#" = 2 ] && [ "$2" = --install ] || {
    echo 'Usage: sh install-standalone.sh /path/gravity-standalone.bin --install'; exit 2;
}
[ "$(uname -s)" = Darwin ]
[ "$(sysctl -n hw.model)" = Mac16,8 ]
payload=$1
[ -s "$payload" ] && [ -s "$payload.sha256" ]
directory=$(dirname "$payload")
if [ -x /sbin/sha256sum ]; then
    (cd "$directory" && /sbin/sha256sum -c "$(basename "$payload").sha256")
elif command -v shasum >/dev/null 2>&1; then
    (cd "$directory" && shasum -a 256 -c "$(basename "$payload").sha256")
elif command -v openssl >/dev/null 2>&1; then
    expected=$(awk 'NR == 1 {print $1}' "$payload.sha256")
    actual=$(openssl dgst -sha256 "$payload" | awk '{print $NF}')
    [ -n "$expected" ] && [ "$actual" = "$expected" ] || {
        echo 'STOP: standalone payload checksum mismatch'; exit 1;
    }
    echo 'Standalone payload SHA256: OK'
else
    echo 'STOP: SHA256 verification tool missing; checksum not verified.'
    exit 1
fi
volume='/Volumes/Gravity Linux J614s Dev'
[ -d "$volume" ]
info=$(diskutil info -plist "$volume")
uuid=$(printf '%s' "$info" | plutil -extract VolumeUUID raw -o - -)
[ "$uuid" = 7BB3DC62-3D93-4B51-8D8B-A922DE5E5CCB ] || {
    echo 'STOP: Gravity System volume UUID mismatch'; exit 1;
}

# Check the target's Recovery authorization, not whether Data happens to be mounted.
policy=$(mktemp /tmp/gravity-policy.XXXXXX)
if ! bputil -d -v 1B517D62-C96F-4CC6-BD52-6320F1AC845D >"$policy"; then
    rm -f "$policy"
    echo 'STOP: unable to read Gravity boot policy.'; exit 1
fi
if ! grep -q ': Paired' "$policy"; then
    rm -f "$policy"
    echo 'STOP: this Recovery session is not paired with Gravity.'
    echo 'Make Gravity the default startup OS, shut down, then hold Power continuously to enter its Recovery.'
    exit 1
fi
if ! grep -q 'one true recoveryOS' "$policy"; then
    rm -f "$policy"
    echo 'STOP: this session is not physical-presence Recovery (1TR).'
    echo 'Shut down, then hold Power continuously from power-off to Startup Options.'
    exit 1
fi
rm -f "$policy"

echo 'Installing the tested standalone payload into the Gravity boot entry.'
kmutil configure-boot -c "$payload" --raw --entry-point 2048 --lowest-virtual-address 0 -v "$volume"
echo 'Installed. Shut down and choose Gravity Linux J614s Dev in Startup Options.'
