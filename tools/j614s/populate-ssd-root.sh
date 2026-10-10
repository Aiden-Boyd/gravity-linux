#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
device=/dev/nvme0n1p4
uuid=abdb3fe1-f31a-4829-b829-0f95b0023418
grep -qi "^PARTUUID=$uuid$" /sys/class/block/nvme0n1p4/uevent
[ "$(cat /sys/class/block/nvme0n1p4/size)" = 19527680 ]
[ "$(chroot /tmp/storage-tools /usr/sbin/blkid -p -s TYPE -o value "$device")" = ext4 ]
! grep -q "$device " /proc/mounts
[ -s /root/.ssh/authorized_keys ]
[ -s /etc/dropbear/host_ed25519 ]
[ -x /tmp/ssd-root-init.sh ]
[ -x /bin/busybox ]
mkdir -p /mnt/gravity
mount -t ext4 "$device" /mnt/gravity
trap 'umount /mnt/gravity 2>/dev/null || true' EXIT
set --
for directory in bin sbin etc lib usr root; do
    [ ! -e /$directory ] || set -- "$@" "$directory"
done
tar -cpf /tmp/gravity-root.tar -C / "$@"
tar -xpf /tmp/gravity-root.tar -C /mnt/gravity
mkdir -p /mnt/gravity/dev /mnt/gravity/proc /mnt/gravity/sys /mnt/gravity/run /mnt/gravity/tmp /mnt/gravity/mnt
chmod 1777 /mnt/gravity/tmp
cp /tmp/ssd-root-init.sh /mnt/gravity/sbin/gravity-init
chmod 755 /mnt/gravity/sbin/gravity-init
printf '%s\n' "$uuid" > /mnt/gravity/etc/gravity-root-partuuid
if [ -s /tmp/wifi.conf ]; then
    cp /tmp/wifi.conf /mnt/gravity/etc/wpa_supplicant.conf
    chmod 600 /mnt/gravity/etc/wpa_supplicant.conf
else
    echo 'No saved Wi-Fi configuration; run net-start from the SSD console after boot.'
fi
cmp /bin/busybox /mnt/gravity/bin/busybox
cmp /root/.ssh/authorized_keys /mnt/gravity/root/.ssh/authorized_keys
sync
umount /mnt/gravity
chroot /tmp/storage-tools /usr/sbin/e2fsck -f -n "$device"
mount -t ext4 -o ro "$device" /mnt/gravity
cmp /bin/busybox /mnt/gravity/bin/busybox
grep -qx "$uuid" /mnt/gravity/etc/gravity-root-partuuid
umount /mnt/gravity
trap - EXIT
rm /tmp/gravity-root.tar
echo 'READY: GRAVITYROOT populated, filesystem checked, read-back verified.'
