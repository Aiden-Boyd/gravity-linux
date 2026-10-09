#!/bin/sh
# SPDX-License-Identifier: MIT
# Local Wi-Fi credentials, DHCP, and key-only SSH in the RAM diagnostic.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
mkdir -p /dev/pts
grep -q ' /dev/pts ' /proc/mounts || mount -t devpts devpts /dev/pts || exit 1
if [ ! -d /sys/class/net/wlan0 ]; then
    modprobe brcmfmac-wcc || exit 1
    j614s-diag wifi > /tmp/net-load.log 2>&1
    sleep 3
fi
ip link set wlan0 up || exit 1
mkdir -p /run/wpa_supplicant /etc/dropbear
if ! wpa_cli -i wlan0 -p /run/wpa_supplicant status 2>/dev/null | grep -q '^wpa_state=COMPLETED$'; then
    killall wpa_supplicant 2>/dev/null || true
    sleep 2
    rm -f /run/wpa_supplicant/wlan0
    printf 'Wi-Fi name [Amazing_Grace_Core]: '
    read -r ssid
    ssid=${ssid:-Amazing_Grace_Core}
    printf 'Wi-Fi password (hidden): '
    trap 'stty echo' EXIT HUP INT TERM
    stty -echo
    printf 'disable_scan_offload=1\nctrl_interface=/run/wpa_supplicant\n' > /tmp/wifi.conf
    wpa_passphrase "$ssid" | sed '/^[[:space:]]*#psk=/d' >> /tmp/wifi.conf
    stty echo
    printf '\n'
    trap - EXIT HUP INT TERM
    wpa_supplicant -B -i wlan0 -c /tmp/wifi.conf -f /tmp/wpa.log || exit 1
    connected=no
    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        if wpa_cli -i wlan0 -p /run/wpa_supplicant status 2>/dev/null | grep -q '^wpa_state=COMPLETED$'; then
            connected=yes
            break
        fi
        sleep 2
    done
    if [ "$connected" != yes ]; then
        echo 'Wi-Fi association did not finish; inspect /tmp/wpa.log.'
        exit 1
    fi
fi
/usr/lib/j614s/busybox udhcpc -i wlan0 -s /bin/j614s-dhcp -n -q -t 5 -T 3 || exit 1
if [ ! -s /etc/dropbear/host_ed25519 ]; then
    dropbearkey -t ed25519 -f /etc/dropbear/host_ed25519 > /tmp/ssh-host-key.txt 2>&1 || exit 1
fi
if ! pidof dropbear >/dev/null; then
    # Password authentication and TCP forwarding disabled; host's public key only.
    dropbear -s -j -k -r /etc/dropbear/host_ed25519 -P /run/dropbear.pid || exit 1
fi
address=$(ip -4 addr show dev wlan0 | awk '/inet / {split($2,a,"/"); print a[1]; exit}')
echo "READY: on the Bazzite PC run: ssh root@$address"
echo 'Host key is temporary and will change after reboot. Fingerprint:'
grep -E 'Fingerprint:|SHA256:' /tmp/ssh-host-key.txt
