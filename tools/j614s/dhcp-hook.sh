#!/bin/sh
# SPDX-License-Identifier: MIT
BB=/usr/bin/net-busybox
case "$1" in
    deconfig)
        "$BB" ifconfig "$interface" 0.0.0.0
        ;;
    bound|renew)
        "$BB" ifconfig "$interface" "$ip" netmask "${subnet:-255.255.255.0}" up || exit 1
        while "$BB" ip route del default dev "$interface" 2>/dev/null; do :; done
        for gateway in $router; do
            "$BB" ip route add default via "$gateway" dev "$interface" || exit 1
            break
        done
        : > /etc/resolv.conf
        for server in $dns; do printf 'nameserver %s\n' "$server" >> /etc/resolv.conf; done
        ;;
esac
