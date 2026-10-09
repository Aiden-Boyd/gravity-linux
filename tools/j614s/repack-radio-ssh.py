#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 repack-radio-ssh.py radio-diag ssh-tools radio-ssh ~/.ssh/id_ed25519.pub

Add DHCP and key-only SSH to a COPY of a local RAM bundle.
Preserves locally extracted firmware, kernel, DTB, and boot arguments.
"""
import base64
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


SCRIPTS = {'bin/net-start': '#!/bin/sh\n# SPDX-License-Identifier: MIT\n# Local Wi-Fi credentials, DHCP, and key-only SSH in the RAM diagnostic.\nexport PATH=/usr/sbin:/usr/bin:/sbin:/bin\numask 077\nif [ ! -d /sys/class/net/wlan0 ]; then\n    modprobe brcmfmac-wcc || exit 1\n    j614s-diag wifi > /tmp/net-load.log 2>&1\n    sleep 3\nfi\nip link set wlan0 up || exit 1\nmkdir -p /run/wpa_supplicant /etc/dropbear\nif ! wpa_cli -i wlan0 -p /run/wpa_supplicant status 2>/dev/null | grep -q \'^wpa_state=COMPLETED$\'; then\n    printf \'Wi-Fi name [Amazing_Grace_Core]: \'\n    read -r ssid\n    ssid=${ssid:-Amazing_Grace_Core}\n    printf \'Wi-Fi password (hidden): \'\n    trap \'stty echo\' EXIT HUP INT TERM\n    stty -echo\n    printf \'ctrl_interface=/run/wpa_supplicant\\n\' > /tmp/wifi.conf\n    wpa_passphrase "$ssid" | sed \'/^[[:space:]]*#psk=/d\' >> /tmp/wifi.conf\n    stty echo\n    printf \'\\n\'\n    trap - EXIT HUP INT TERM\n    wpa_supplicant -B -i wlan0 -c /tmp/wifi.conf -f /tmp/wpa.log || exit 1\n    connected=no\n    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do\n        if wpa_cli -i wlan0 -p /run/wpa_supplicant status 2>/dev/null | grep -q \'^wpa_state=COMPLETED$\'; then\n            connected=yes\n            break\n        fi\n        sleep 2\n    done\n    if [ "$connected" != yes ]; then\n        echo \'Wi-Fi association did not finish; inspect /tmp/wpa.log.\'\n        exit 1\n    fi\nfi\n/usr/bin/net-busybox udhcpc -i wlan0 -s /bin/j614s-dhcp -n -q -t 5 -T 3 || exit 1\nif [ ! -s /etc/dropbear/host_ed25519 ]; then\n    dropbearkey -t ed25519 -f /etc/dropbear/host_ed25519 > /tmp/ssh-host-key.txt 2>&1 || exit 1\nfi\nif ! pidof dropbear >/dev/null; then\n    # Password authentication and TCP forwarding disabled; host\'s public key only.\n    dropbear -s -j -k -r /etc/dropbear/host_ed25519 -P /run/dropbear.pid || exit 1\nfi\naddress=$(ip -4 addr show dev wlan0 | awk \'/inet / {split($2,a,"/"); print a[1]; exit}\')\necho "READY: on the Bazzite PC run: ssh root@$address"\necho \'Host key is temporary and will change after reboot. Fingerprint:\'\ngrep -E \'Fingerprint:|SHA256:\' /tmp/ssh-host-key.txt\n', 'bin/j614s-dhcp': '#!/bin/sh\n# SPDX-License-Identifier: MIT\nBB=/usr/bin/net-busybox\ncase "$1" in\n    deconfig)\n        "$BB" ifconfig "$interface" 0.0.0.0\n        ;;\n    bound|renew)\n        "$BB" ifconfig "$interface" "$ip" netmask "${subnet:-255.255.255.0}" up || exit 1\n        while "$BB" ip route del default dev "$interface" 2>/dev/null; do :; done\n        for gateway in $router; do\n            "$BB" ip route add default via "$gateway" dev "$interface" || exit 1\n            break\n        done\n        : > /etc/resolv.conf\n        for server in $dns; do printf \'nameserver %s\\n\' "$server" >> /etc/resolv.conf; done\n        ;;\nesac\n'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    bundle, tools, output, keyfile = [Path(p).expanduser().resolve() for p in sys.argv[1:]]
    key = keyfile.read_text().strip()
    fields = key.split()
    if len(key.splitlines()) != 1 or len(fields) < 2 or fields[0] != 'ssh-ed25519':
        raise SystemExit('Provide one Ed25519 public key (.pub), never a private key.')
    raw = base64.b64decode(fields[1], validate=True)
    if len(raw) != 51 or raw[:19] != b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20':
        raise SystemExit('Malformed Ed25519 public key.')
    if output.exists():
        raise SystemExit('Output already exists; choose a new directory.')
    for directory in (bundle, tools):
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=directory, check=True)
    original = {name: sha(bundle / name) for name in ('Image.gz', 't6040-j614s.dtb', 'BOOTARGS.txt')}
    with tempfile.TemporaryDirectory(prefix='j614s-tools-') as temp:
        work = Path(temp)
        root = work / 'root'
        root.mkdir()
        subprocess.run(['cpio', '-id', '--no-absolute-filenames'], cwd=root, check=True,
                       input=gzip.decompress((bundle / 'initramfs.cpio.gz').read_bytes()),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with tarfile.open(tools / 'radio-userspace.tar.gz') as archive:
            for member in archive:
                destination = root / member.name
                if not destination.resolve().is_relative_to(root):
                    raise SystemExit('Tool archive path escapes RAM root.')
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source:
                        destination.write_bytes(source.read())
                    destination.chmod(member.mode & 0o777)
                else:
                    raise SystemExit('Unexpected archive member type.')
        for name in ('iw', 'wpa_supplicant', 'wpa_cli', 'wpa_passphrase', 'btmgmt', 'dropbear', 'dropbearkey', 'net-busybox'):
            matches = [p for p in root.rglob(name) if p.is_file()]
            if len(matches) != 1:
                raise SystemExit(f'Missing or ambiguous tool: {name}')
            binary = matches[0].read_bytes()
            if binary[:4] != b'\x7fELF' or int.from_bytes(binary[18:20], 'little') != 183:
                raise SystemExit(f'Tool is not an ARM64 ELF: {name}')
        for name, content in SCRIPTS.items():
            script = root / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(content)
            script.chmod(0o755)
            subprocess.run(['sh', '-n', str(script)], check=True)
        sshdir = root / 'root/.ssh'
        sshdir.mkdir(parents=True, exist_ok=True)
        (root / 'root').chmod(0o700)
        sshdir.chmod(0o700)
        (sshdir / 'authorized_keys').write_text(key + '\n')
        (sshdir / 'authorized_keys').chmod(0o600)
        etc = root / 'etc'
        etc.mkdir(exist_ok=True)
        accounts = {
            'passwd': 'root:x:0:0:root:/root:/bin/sh',
            'group': 'root:x:0:',
            'shadow': 'root::0:0:99999:7:::',
        }
        for name, entry in accounts.items():
            target = etc / name
            lines = target.read_text().splitlines() if target.exists() else []
            lines = [line for line in lines if not line.startswith('root:')]
            target.write_text('\n'.join([entry] + lines) + '\n')
            target.chmod(0o600 if name == 'shadow' else 0o644)
        (etc / 'shells').write_text('/bin/sh\n')
        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        result = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
                                input=('\0'.join(names) + '\0').encode(), check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        staged = work / 'bundle'
        shutil.copytree(bundle, staged)
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(result.stdout, compresslevel=9, mtime=0))
        shutil.copyfile(tools / 'PACKAGE_VERSIONS.txt', staged / 'USERSPACE_PACKAGES.txt')
        (staged / 'SSH.txt').write_text('Run net-start on the Mac; then use the printed SSH command on your PC. Key-only root login, TCP forwarding disabled. RAM only.\n')
        for name, expected in original.items():
            assert sha(staged / name) == expected
        (staged / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(staged.iterdir())
                                                if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output.name}; net-start, DHCP and key-only SSH added; kernel, DTB and boot arguments unchanged.')


if __name__ == '__main__':
    main()
