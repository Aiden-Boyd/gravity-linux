#!/bin/sh
# SPDX-License-Identifier: MIT
# Enumerate only. No mounts, formats, or user-data writes.
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /tmp/nvme-probe
for driver in apple-mailbox apple-rtkit apple-sart nvme-core nvme-apple; do
    echo "Loading $driver"
    modprobe "$driver"
done
sleep 5
cat /proc/partitions
dmesg > /tmp/nvme-probe/dmesg.txt
grep -Ei 'nvme|ANS|SART|RTKit|panic|assert' /tmp/nvme-probe/dmesg.txt | tail -n 40
echo 'Logs in /tmp/nvme-probe. No filesystem mounted.'
