#!/bin/busybox sh
# SPDX-License-Identifier: MIT

/bin/busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /run /tmp
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp

PROFILE="$(cat /etc/j614s-profile 2>/dev/null || echo diagnostic)"
PROFILE_TAG="$(echo "$PROFILE" | tr '[:lower:]-' '[:upper:]_')"

echo
echo "=== J614S_${PROFILE_TAG}_RAMBOOT_OK ==="
uname -a
printf "model: "
cat /proc/device-tree/model 2>/dev/null || true
echo
echo
echo "No persistent filesystem is mounted automatically."
echo "Internal storage, if it appears, must NOT be mounted read-write during bring-up."
echo
echo "Useful commands:"
echo "  dmesg"
echo "  ls /sys/bus/platform/devices"
echo "  ls /sys/bus/pci/devices"
echo "  ls /sys/block"
echo "  modprobe <module>          # FULL-DIAGNOSTIC only"
echo "  j614s-diag report          # passive capability snapshot"
echo "  j614s-diag <subsystem>     # staged diagnostic helper"
echo "  poweroff -f                # or physically power-cycle"
echo

exec setsid cttyhack sh
