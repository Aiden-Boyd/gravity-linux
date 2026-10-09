#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 repack-radio-tools.py radio radio-tools radio-test

Merge an ARM64 userspace add-on into a COPY of a local RAM bundle.
Preserves locally extracted firmware, kernel, DTB, and boot arguments.
"""
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    bundle, tools, output = [Path(p).resolve() for p in sys.argv[1:]]
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
        for name in ('iw', 'wpa_supplicant', 'wpa_cli', 'wpa_passphrase', 'btmgmt'):
            matches = [p for p in root.rglob(name) if p.is_file()]
            if len(matches) != 1:
                raise SystemExit(f'Missing or ambiguous tool: {name}')
            binary = matches[0].read_bytes()
            if binary[:4] != b'\x7fELF' or int.from_bytes(binary[18:20], 'little') != 183:
                raise SystemExit(f'Tool is not an ARM64 ELF: {name}')
        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        result = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
                                input=('\0'.join(names) + '\0').encode(), check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        staged = work / 'bundle'
        shutil.copytree(bundle, staged)
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(result.stdout, compresslevel=9, mtime=0))
        shutil.copyfile(tools / 'PACKAGE_VERSIONS.txt', staged / 'USERSPACE_PACKAGES.txt')
        for name, expected in original.items():
            assert sha(staged / name) == expected
        (staged / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(staged.iterdir())
                                                if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output.name}; radio tools added; kernel, DTB and boot arguments unchanged.')


if __name__ == '__main__':
    main()
