#!/bin/busybox sh
# SPDX-License-Identifier: MIT
# Staged J614s/T6040 RAM-boot driver smoke helper.
#
# Intentionally no "all" command: each hardware block is enabled separately
# so a failure can be attributed to the last requested subsystem.

set -u

usage()
{
    echo "usage: j614s-diag report|smc|input|cpufreq|pcie|sd|wifi|bt" >&2
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
    echo "--- POWER ---"
    for p in /sys/class/power_supply/*; do
        [ -e "$p" ] && echo "${p##*/}"
    done
    echo "--- HWMON ---"
    for h in /sys/class/hwmon/*; do
        [ -e "$h" ] && printf "%s: " "${h##*/}" && cat "$h/name" 2>/dev/null
    done
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
    echo "--- CPUFREQ ---"
    for p in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -d "$p" ] || continue
        printf "%s: " "${p##*/}"
        cat "$p/scaling_cur_freq" 2>/dev/null || true
    done
}

load_smc_base()
{
    load pinctrl-apple-gpio &&
    load apple-mailbox &&
    load apple-rtkit &&
    load macsmc &&
    load gpio-macsmc
}

load_smc_telemetry()
{
    load_smc_base &&
    load macsmc-input &&
    load macsmc-power &&
    load macsmc-hwmon
}

load_pcie()
{
    load_smc_base &&
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
    load_smc_telemetry || exit $?
    ;;
input)
    # Register the exact Apple HID consumers before DockChannel creates the
    # BUS_HOST devices; there is no udev here to auto-load modalias drivers.
    load hid-apple &&
    load hid-magicmouse &&
    load hid-multitouch &&
    load apple-dart &&
    load apple-mailbox &&
    load apple-rtkit &&
    load apple-dockchannel &&
    load apple-rtkit-helper &&
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
