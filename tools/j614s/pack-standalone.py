#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 pack-standalone.py ssd-root m1n1-ssd gravity-standalone.bin"""
import gzip
import hashlib
from pathlib import Path
import struct
import subprocess
import sys

if len(sys.argv) != 4:
    raise SystemExit(__doc__)
bundle, bootloader, output = map(Path, sys.argv[1:])
if output.exists():
    raise SystemExit('Output exists; choose a new filename.')
for directory in (bundle, bootloader):
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=directory, check=True)
base = (bootloader / 'm1n1.bin').read_bytes()
if b'J614S_SSD_PAYLOAD:' not in base:
    raise SystemExit('Missing standalone NVMe handoff patch.')
args = (bundle / 'BOOTARGS.txt').read_text().strip()
if '\n' in args or len(args) > 1000 or 'rdinit=/init' not in args:
    raise SystemExit('Unexpected boot arguments.')
kernel = (bundle / 'Image.gz').read_bytes()
if gzip.decompress(kernel)[0x38:0x3c] != b'ARM\x64':
    raise SystemExit('Not an ARM64 Linux kernel.')
dt = (bundle / 't6040-j614s.dtb').read_bytes()
if dt[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack('>I', dt[4:8])[0] != len(dt):
    raise SystemExit('Invalid DTB length/header.')
if b'apple,j614s\0' not in dt:
    raise SystemExit('Wrong target DTB.')
initrd = (bundle / 'initramfs.cpio.gz').read_bytes()
archive = gzip.decompress(initrd)
if b'gravity-root-partuuid' not in archive or b'switch_root' not in archive:
    raise SystemExit('Use the SSD root initramfs.')
# v1.9.9 src/payload.c accepts a length-delimited compressed initramfs.
payload = (base + ('chosen.bootargs=' + args + '\n').encode() + dt + kernel +
           b'm1n1_initramfs' + struct.pack('<I', len(initrd)) + initrd + b'\0' * 4)
output.write_bytes(payload)
digest = hashlib.sha256(payload).hexdigest()
output.with_suffix(output.suffix + '.sha256').write_text(f'{digest}  {output.name}\n')
print(f'READY: {output}: {len(payload)} bytes; SHA256 {digest}')
