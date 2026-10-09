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

# One explicit boot argument selects the first hardware smoke test.
# Report results on screen even when the keyboard has not been brought up.
case " $(cat /proc/cmdline) " in
    *" j614s.autotest=smc-battery "*)
        if [ "$PROFILE" = diagnostic ]; then
            echo "=== J614S_SMC_BATTERY_START ==="
            if j614s-diag battery; then
                battery_found=0
                for attempt in 1 2 3 4 5 6 7 8 9 10; do
                    for supply in /sys/class/power_supply/*; do
                        [ -r "$supply/type" ] || continue
                        [ "$(cat "$supply/type")" = Battery ] || continue
                        battery_found=1
                        cat "$supply/uevent"
                    done
                    [ "$battery_found" = 1 ] && break
                    sleep 1
                done
                if [ "$battery_found" = 1 ]; then
                    echo "=== J614S_SMC_BATTERY_OK ==="
                else
                    echo "=== J614S_SMC_BATTERY_NO_DEVICE ==="
                fi
            else
                echo "=== J614S_SMC_BATTERY_LOAD_FAILED ==="
            fi
        else
            echo "SMC battery autotest refused outside diagnostic profile"
        fi
        ;;
esac

exec setsid cttyhack sh
