#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 repack-radio-diag.py radio-test radio-diag

Add a single-command Wi-Fi diagnostic to a COPY of a local RAM bundle.
Preserves locally extracted firmware, kernel, DTB, and boot arguments.
"""
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


DIAGNOSTIC = '#!/bin/sh\n# SPDX-License-Identifier: MIT\n# RAM-only diagnostics; no credentials, association, or disk writes.\nexport PATH=/usr/sbin:/usr/bin:/sbin:/bin\nOUT=/tmp/j614s-wifi-diag\nmkdir -p "$OUT" || exit 1\nSUMMARY="$OUT/summary.txt"\n: > "$SUMMARY"\nsay() { printf \'%s\\n\' "$*" | tee -a "$SUMMARY"; }\ncapture() {\n    name=$1\n    shift\n    "$@" > "$OUT/$name.txt" 2>&1\n    rc=$?\n    printf \'%s exit=%s\\n\' "$name" "$rc" >> "$SUMMARY"\n    return 0\n}\nsay \'J614s Wi-Fi diagnostic: about 45 seconds; leave it running.\'\nfor tool in iw timeout ip modprobe; do\n    if ! command -v "$tool" >/dev/null 2>&1; then\n        say "STOP: missing $tool; boot the diagnostic bundle."\n        exit 1\n    fi\ndone\ncapture version iw --version\ncapture kernel uname -a\ncapture dmesg-before dmesg\ncat /proc/interrupts > "$OUT/interrupts-before.txt" 2>/dev/null\n# Preload the firmware-vendor helper before probing the radio.\ncapture helper modprobe brcmfmac-wcc\nif [ ! -d /sys/class/net/wlan0 ]; then\n    capture load timeout 20 j614s-diag wifi\n    sleep 3\nfi\nif [ ! -d /sys/class/net/wlan0 ]; then\n    say \'STOP: wlan0 did not register.\'\n    capture dmesg-after dmesg\n    tail -n 20 "$OUT/dmesg-after.txt"\n    exit 1\nfi\ncapture interfaces iw dev\ncapture regulatory iw reg get\ncapture capabilities iw phy phy0 info\ncapture link-before ip link show wlan0\ncapture power-save iw dev wlan0 get power_save\ncapture up ip link set wlan0 up\ncapture cache-before iw dev wlan0 scan dump\nscan() {\n    label=$1\n    shift\n    say "RUN: $label (maximum 20 seconds)"\n    # iw scan subscribes to completion events before triggering the scan.\n    # Its exit code alone is insufficient: it can return 0 for scan aborted.\n    timeout -s KILL 20 iw dev wlan0 scan "$@" > "$OUT/$label.txt" 2>&1\n    rc=$?\n    if grep -qi \'scan aborted\' "$OUT/$label.txt"; then\n        result=ABORTED\n    elif [ "$rc" -ne 0 ]; then\n        result="FAILED_OR_TIMED_OUT_exit_$rc"\n    elif grep -q \'^BSS \' "$OUT/$label.txt"; then\n        result=NETWORKS_FOUND\n    else\n        result=COMPLETED_WITHOUT_BSS\n    fi\n    say "RESULT: $label $result"\n    grep -E \'SSID:|scan aborted|command failed|error|failed\' "$OUT/$label.txt" | head -n 12\n    # Wait beyond the driver\'s 10-second timeout before the next request.\n    sleep 2\n}\nscan active-2g freq 2412 2437 2462\nscan passive-2g freq 2412 2437 2462 passive\ncapture cache-after iw dev wlan0 scan dump\ncapture link-after ip link show wlan0\ncapture dmesg-after dmesg\ncat /proc/interrupts > "$OUT/interrupts-after.txt" 2>/dev/null\nsay \'--- LATEST DRIVER MESSAGES ---\'\ngrep -Ei \'brcmf|cfg80211|firmware|wlan0\' "$OUT/dmesg-after.txt" | tail -n 16 | tee -a "$SUMMARY"\nsay "DONE: logs in $OUT (RAM; lost at reboot)."\nsay \'Show this again with: cat /tmp/j614s-wifi-diag/summary.txt\'\n'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    bundle, output = [Path(p).resolve() for p in sys.argv[1:]]
    if output.exists():
        raise SystemExit('Output already exists; choose a new directory.')
    for directory in (bundle,):
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=directory, check=True)
    original = {name: sha(bundle / name) for name in ('Image.gz', 't6040-j614s.dtb', 'BOOTARGS.txt')}
    with tempfile.TemporaryDirectory(prefix='j614s-tools-') as temp:
        work = Path(temp)
        root = work / 'root'
        root.mkdir()
        subprocess.run(['cpio', '-id', '--no-absolute-filenames'], cwd=root, check=True,
                       input=gzip.decompress((bundle / 'initramfs.cpio.gz').read_bytes()),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for name in ('iw', 'wpa_supplicant', 'wpa_cli', 'wpa_passphrase', 'btmgmt'):
            matches = [p for p in root.rglob(name) if p.is_file()]
            if len(matches) != 1:
                raise SystemExit(f'Missing or ambiguous tool: {name}')
            binary = matches[0].read_bytes()
            if binary[:4] != b'\x7fELF' or int.from_bytes(binary[18:20], 'little') != 183:
                raise SystemExit(f'Tool is not an ARM64 ELF: {name}')
        diagnostic = root / 'bin/wifi-diag'
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_text(DIAGNOSTIC)
        diagnostic.chmod(0o755)
        subprocess.run(['sh', '-n', str(diagnostic)], check=True)
        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        result = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
                                input=('\0'.join(names) + '\0').encode(), check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        staged = work / 'bundle'
        shutil.copytree(bundle, staged)
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(result.stdout, compresslevel=9, mtime=0))
        (staged / 'WIFI_DIAG.txt').write_text('Run wifi-diag on the Mac. Logs: /tmp/j614s-wifi-diag. RAM only; lost at reboot.\n')
        for name, expected in original.items():
            assert sha(staged / name) == expected
        (staged / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(staged.iterdir())
                                                if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output.name}; wifi-diag added; kernel, DTB and boot arguments unchanged.')


if __name__ == '__main__':
    main()
