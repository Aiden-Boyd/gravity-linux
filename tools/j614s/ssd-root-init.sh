#!/bin/sh
# SPDX-License-Identifier: MIT
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
mkdir -p /proc /sys /dev /run /tmp /dev/pts
grep -q ' /proc ' /proc/mounts || mount -t proc proc /proc
grep -q ' /sys ' /proc/mounts || mount -t sysfs sysfs /sys
grep -q ' /dev ' /proc/mounts || mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
mkdir -p /dev/pts /run/wpa_supplicant
mount -t devpts devpts /dev/pts
j614s-diag input > /tmp/input-load.log 2>&1
echo 'GRAVITY SSD ROOT: '
grep ' / ' /proc/mounts
if [ -s /etc/wpa_supplicant.conf ]; then
    (
        j614s-diag wifi > /tmp/net-load.log 2>&1
        ip link set wlan0 up || exit 1
        wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf -f /tmp/wpa.log || exit 1
        connected=no
        for attempt in $(seq 1 30); do
            if wpa_cli -i wlan0 -p /run/wpa_supplicant status | grep -q '^wpa_state=COMPLETED$'; then
                connected=yes; break
            fi
            sleep 1
        done
        [ "$connected" = yes ] || exit 1
        /usr/lib/j614s/busybox udhcpc -i wlan0 -s /bin/j614s-dhcp -n -q -t 5 -T 3 || exit 1
        dropbear -s -j -k -r /etc/dropbear/host_ed25519 -P /run/dropbear.pid
        ip -4 addr show wlan0
    ) > /tmp/net-start.log 2>&1 &
fi
while :; do
    setsid cttyhack sh
    echo 'Console exited; restarting shell.'
done
