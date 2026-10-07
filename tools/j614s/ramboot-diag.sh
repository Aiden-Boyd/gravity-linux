#!/bin/busybox sh
# SPDX-License-Identifier: MIT
# Staged J614s/T6040 RAM-boot driver smoke helper.
#
# Intentionally no "all" command: each hardware block is enabled separately
# so a failure can be attributed to the last requested subsystem.

set -u

usage()
{
    echo "usage: j614s-diag report|smc|battery|sensors|lid|input|cpufreq|pcie|sd|wifi|bt" >&2
    exit 2
}

load()
{
    mod="$1"
    echo ">>> modprobe $mod"
    if ! modprobe "$mod"; then
        echo "!!! $mod failed; recent dmesg follows" >&2
        dmesg | tail -n 60
        return 1
    fi
}

show_pci()
{
    echo "--- PCI ---"
    found=0
    for d in /sys/bus/pci/devices/*; do
        [ -r "$d/vendor" ] || continue
        found=1
        printf "%s vendor=%s device=%s class=%s driver=%s\n" \
            "${d##*/}" \
            "$(cat "$d/vendor" 2>/dev/null)" \
            "$(cat "$d/device" 2>/dev/null)" \
            "$(cat "$d/class" 2>/dev/null)" \
            "$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)"
    done
    [ "$found" -eq 1 ] || echo "(none)"
}

show_state()
{
    echo "--- CPU ---"
    printf "online: "; cat /sys/devices/system/cpu/online 2>/dev/null || echo "?"
    echo "--- INPUT ---"
    cat /proc/bus/input/devices 2>/dev/null || true
    show_pci
    echo "--- NET ---"
    for n in /sys/class/net/*; do
        [ -e "$n" ] && echo "${n##*/}"
    done
    echo "--- BLUETOOTH ---"
    for h in /sys/class/bluetooth/*; do
        [ -e "$h" ] && echo "${h##*/}"
    done
    echo "--- BLOCK ---"
    for b in /sys/block/*; do
        [ -e "$b" ] && echo "${b##*/}"
    done
    echo "--- POWER ---"
    for p in /sys/class/power_supply/*; do
        [ -d "$p" ] || continue
        echo "${p##*/}"
        grep -E '^(POWER_SUPPLY_(STATUS|CAPACITY|ONLINE|HEALTH|VOLTAGE_NOW|CURRENT_NOW))=' "$p/uevent" 2>/dev/null || true
    done
    echo "--- HWMON ---"
    for h in /sys/class/hwmon/*; do
        [ -d "$h" ] || continue
        printf "%s " "${h##*/}"
        cat "$h/name" 2>/dev/null || true
    done
    echo "--- CPUFREQ ---"
    for p in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -d "$p" ] || continue
        printf "%s: " "${p##*/}"
        cat "$p/scaling_cur_freq" 2>/dev/null || true
    done
}

load_smc()
{
    load pinctrl-apple-gpio &&
    load apple-mailbox &&
    load apple-rtkit &&
    load macsmc &&
    load gpio-macsmc
}

load_pcie()
{
    load_smc &&
    load apple-dart &&
    load pcie-apple
}

cmd="${1:-}"
[ -n "$cmd" ] || usage

case "$cmd" in
report)
    show_state
    ;;
smc)
    load_smc || exit $?
    ;;
battery)
    load_smc &&
    load macsmc-power || exit $?
    ;;
sensors)
    load_smc &&
    load macsmc-hwmon || exit $?
    ;;
lid)
    load_smc &&
    load macsmc-input || exit $?
    ;;
input)
    load apple-dart &&
    load apple-mailbox &&
    load apple-rtkit &&
    load apple-dockchannel &&
    load apple-rtkit-helper &&
    load hid-apple &&
    load hid-magicmouse &&
    load dockchannel-hid || exit $?
    ;;
cpufreq)
    load apple-soc-cpufreq || exit $?
    ;;
pcie)
    load_pcie || exit $?
    ;;
sd)
    load_pcie &&
    load sdhci-pci || exit $?
    ;;
wifi)
    load_pcie &&
    load brcmfmac || exit $?
    ;;
bt)
    load_pcie &&
    load hci_bcm4377 || exit $?
    ;;
*)
    usage
    ;;
esac

echo
show_state
echo "--- RECENT DMESG ---"
dmesg | tail -n 80
