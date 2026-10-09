#!/bin/sh
# SPDX-License-Identifier: MIT
# RAM-only diagnostics; no credentials, association, or disk writes.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
OUT=/tmp/j614s-wifi-diag
mkdir -p "$OUT" || exit 1
SUMMARY="$OUT/summary.txt"
: > "$SUMMARY"
say() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
capture() {
    name=$1
    shift
    "$@" > "$OUT/$name.txt" 2>&1
    rc=$?
    printf '%s exit=%s\n' "$name" "$rc" >> "$SUMMARY"
    return 0
}
say 'J614s Wi-Fi diagnostic: about 45 seconds; leave it running.'
for tool in iw timeout ip modprobe; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        say "STOP: missing $tool; boot the diagnostic bundle."
        exit 1
    fi
done
capture version iw --version
capture kernel uname -a
capture dmesg-before dmesg
cat /proc/interrupts > "$OUT/interrupts-before.txt" 2>/dev/null
# Preload the firmware-vendor helper before probing the radio.
capture helper modprobe brcmfmac-wcc
if [ ! -d /sys/class/net/wlan0 ]; then
    capture load timeout 20 j614s-diag wifi
    sleep 3
fi
if [ ! -d /sys/class/net/wlan0 ]; then
    say 'STOP: wlan0 did not register.'
    capture dmesg-after dmesg
    tail -n 20 "$OUT/dmesg-after.txt"
    exit 1
fi
capture interfaces iw dev
capture regulatory iw reg get
capture capabilities iw phy phy0 info
capture link-before ip link show wlan0
capture power-save iw dev wlan0 get power_save
capture up ip link set wlan0 up
capture cache-before iw dev wlan0 scan dump
scan() {
    label=$1
    shift
    say "RUN: $label (maximum 20 seconds)"
    # iw scan subscribes to completion events before triggering the scan.
    # Its exit code alone is insufficient: it can return 0 for scan aborted.
    timeout -s KILL 20 iw dev wlan0 scan "$@" > "$OUT/$label.txt" 2>&1
    rc=$?
    if grep -qi 'scan aborted' "$OUT/$label.txt"; then
        result=ABORTED
    elif [ "$rc" -ne 0 ]; then
        result="FAILED_OR_TIMED_OUT_exit_$rc"
    elif grep -q '^BSS ' "$OUT/$label.txt"; then
        result=NETWORKS_FOUND
    else
        result=COMPLETED_WITHOUT_BSS
    fi
    say "RESULT: $label $result"
    grep -E 'SSID:|scan aborted|command failed|error|failed' "$OUT/$label.txt" | head -n 12
    # Wait beyond the driver's 10-second timeout before the next request.
    sleep 2
}
scan active-2g freq 2412 2437 2462
scan passive-2g freq 2412 2437 2462 passive
capture cache-after iw dev wlan0 scan dump
capture link-after ip link show wlan0
capture dmesg-after dmesg
cat /proc/interrupts > "$OUT/interrupts-after.txt" 2>/dev/null
say '--- LATEST DRIVER MESSAGES ---'
grep -Ei 'brcmf|cfg80211|firmware|wlan0' "$OUT/dmesg-after.txt" | tail -n 16 | tee -a "$SUMMARY"
say "DONE: logs in $OUT (RAM; lost at reboot)."
say 'Show this again with: cat /tmp/j614s-wifi-diag/summary.txt'
