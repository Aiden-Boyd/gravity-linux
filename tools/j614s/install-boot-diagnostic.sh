#!/bin/sh
# SPDX-License-Identifier: MIT
# Recovery-only diagnostic install. No partition or root filesystem writes.
set -eu
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
[ "$(uname -s)" = Darwin ] && [ "$(sysctl -n hw.model)" = Mac16,8 ]
[ "$#" = 1 ] && [ "$1" = --install ] || { echo "Usage: sh install-boot-diagnostic.sh --install"; exit 2; }
[ "$(id -u)" = 0 ] || { echo "Run in Recovery Terminal."; exit 1; }
data_uuid=1B517D62-C96F-4CC6-BD52-6320F1AC845D
system_uuid=7BB3DC62-3D93-4B51-8D8B-A922DE5E5CCB
diskutil mount "$data_uuid"
diskutil mount "$system_uuid"
data=$(diskutil info -plist "$data_uuid" | plutil -extract MountPoint raw -o - -)
system=$(diskutil info -plist "$system_uuid" | plutil -extract MountPoint raw -o - -)
actual=$(diskutil info -plist "$system" | plutil -extract VolumeUUID raw -o - -)
[ "$actual" = "$system_uuid" ]
stage="$data/boot-check"
payload="$stage/gravity-diagnostic.bin"
[ -s "$payload" ] && [ -s "$payload.sha256" ]
if [ -x /sbin/sha256sum ]; then
  (cd "$stage" && /sbin/sha256sum -c gravity-diagnostic.bin.sha256)
elif command -v shasum >/dev/null 2>&1; then
  (cd "$stage" && shasum -a 256 -c gravity-diagnostic.bin.sha256)
else
  echo "STOP: SHA256 verification tool missing."; exit 1
fi
# Preserve the fresh Recovery report on persistent APFS before another reboot.
out="$stage/recovery-report"
mkdir -p "$out"
find /Library/Logs/DiagnosticReports -type f -name '*socd*.panic' -exec cp {} "$out/" \;
ls -lh "$out"
sync

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

echo "Installing experimental diagnostic payload in the Gravity entry."
echo "This changes only Gravity's custom boot object and its associated boot policy."
kmutil configure-boot -c "$payload" --raw --entry-point 2048 --lowest-virtual-address 0 -v "$system"
sync
echo "DONE. Shut down and choose Gravity Linux J614s Dev in Startup Options."
echo "Photograph any text before the restart. If it loops, return to Macintosh HD."
