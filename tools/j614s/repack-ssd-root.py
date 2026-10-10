#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 repack-ssd-root.py nvme-probe ssd-root

Prepare a tethered kernel boot that switches into the verified SSD root.
Download ssd-root-loader.sh beside this script before running it.
"""
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source, output = (Path(p).resolve() for p in sys.argv[1:])
    if output.exists():
        raise SystemExit('Output already exists; choose a new directory.')
    loader = Path(__file__).resolve().with_name('ssd-root-loader.sh')
    subprocess.run(['sh', '-n', str(loader)], check=True)
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=source, check=True)
    if not (source / 'nvme-handoff.py').is_file():
        raise SystemExit('Use the tested nvme-probe bundle with its NVMe handoff.')
    with tempfile.TemporaryDirectory(prefix='gravity-ssd-') as temp:
        root = Path(temp) / 'root'
        root.mkdir()
        subprocess.run(['cpio', '-id', '--no-absolute-filenames'], cwd=root,
                       input=gzip.decompress((source / 'initramfs.cpio.gz').read_bytes()),
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        init = root / 'init'
        init.unlink()
        shutil.copyfile(loader, init)
        init.chmod(0o755)
        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        archive = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'],
                                 cwd=root, input=('\0'.join(names) + '\0').encode(),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        staged = Path(temp) / 'bundle'
        shutil.copytree(source, staged)
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(archive.stdout, mtime=0))
        (staged / 'SSD_ROOT.txt').write_text(
            'Tethered kernel; initramfs switches to ext4 PARTUUID '
            'abdb3fe1-f31a-4829-b829-0f95b0023418. No formatting.\n')
        for name in ('Image.gz', 't6040-j614s.dtb', 'BOOTARGS.txt', 'nvme-handoff.py'):
            assert (staged / name).read_bytes() == (source / name).read_bytes(), name
        (staged / 'SHA256SUMS').write_text(''.join(
            f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
            for p in sorted(staged.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output}; SSD switch_root loader added; kernel and DT unchanged.')

if __name__ == '__main__':
    main()
