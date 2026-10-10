#!/bin/busybox sh
# SPDX-License-Identifier: MIT
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
/bin/busybox --install -s /bin
mkdir -p /proc /sys /dev /run /tmp /newroot
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
boot_ssd() {
    for module in apple-mailbox apple-rtkit apple-sart nvme-core nvme-apple; do
        modprobe "$module" || return 1
    done
    device=
    for attempt in $(seq 1 30); do
        for part in /sys/class/block/nvme0n1p*; do
            if grep -qi '^PARTUUID=abdb3fe1-f31a-4829-b829-0f95b0023418$' "$part/uevent"; then
                device=/dev/${part##*/}; break
            fi
        done
        [ -n "$device" ] && break
        sleep 1
    done
    [ -n "$device" ] || return 1
    mount -t ext4 "$device" /newroot || return 1
    grep -qx 'abdb3fe1-f31a-4829-b829-0f95b0023418' /newroot/etc/gravity-root-partuuid || return 1
    [ -x /newroot/bin/busybox ] && [ -x /newroot/sbin/gravity-init ] || return 1
    for directory in proc sys dev; do
        mount --move /$directory /newroot/$directory || return 1
    done
    exec switch_root /newroot /sbin/gravity-init
}
boot_ssd
echo 'SSD root boot failed. Recovery RAM shell; no formatting performed.'
j614s-diag input
exec setsid cttyhack sh
