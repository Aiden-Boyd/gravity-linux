#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 repack-nvme-probe.py radio-ssh nvme-dt nvme-probe

Copy an existing local SSH/firmware bundle, replacing only the DT and helpers.
The kernel/modules stay paired; local firmware and SSH keys never leave host.
"""
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    bundle, tools, output = map(lambda s: Path(s).resolve(), sys.argv[1:])
    if output.exists():
        raise SystemExit('Output exists; choose a new directory.')
    for directory in (bundle, tools):
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=directory, check=True)
    with tempfile.TemporaryDirectory(prefix='j614s-nvme-') as temp:
        work = Path(temp)
        root = work / 'root'
        root.mkdir()
        subprocess.run(['cpio', '-id', '--no-absolute-filenames'], cwd=root,
                       input=gzip.decompress((bundle / 'initramfs.cpio.gz').read_bytes()),
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        modules = root / 'lib/modules/7.1.13-g0542623a5c02'
        if not (modules / 'kernel/drivers/nvme/host/nvme-apple.ko').is_file():
            raise SystemExit('Expected tested kernel/module set is missing; refusing DT swap.')
        if not (root / 'root/.ssh/authorized_keys').is_file():
            raise SystemExit('Use the radio-ssh bundle with your public key.')
        for source, target in [('nvme-probe.sh', 'bin/nvme-probe'), ('net-start.sh', 'bin/net-start')]:
            path = root / target
            shutil.copyfile(tools / source, path)
            path.chmod(0o755)
            subprocess.run(['sh', '-n', str(path)], check=True)
        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        archive = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'],
                                 cwd=root, input=('\0'.join(names) + '\0').encode(),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        staged = work / 'bundle'
        shutil.copytree(bundle, staged)
        shutil.copyfile(tools / 't6040-j614s.dtb', staged / 't6040-j614s.dtb')
        shutil.copyfile(tools / 'nvme-handoff.py', staged / 'nvme-handoff.py')
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(archive.stdout, mtime=0))
        loader = staged / 'BOOT_FROM_HOST.sh'
        text = loader.read_text()
        old = 'exec python3 "$M1N1/proxyclient/tools/linux.py"'
        if text.count(old) != 1:
            raise SystemExit('Unexpected host loader; refusing to change handoff.')
        loader.write_text(text.replace(old, 'exec python3 "$BUNDLE/nvme-handoff.py" "$M1N1"'))
        (staged / 'NVME_PROBE.txt').write_text('Run net-start, then nvme-probe over SSH. Enumeration only. No mounts or formats.\n')
        for name in ('Image.gz', 'BOOTARGS.txt', 'kernel.config'):
            assert sha(staged / name) == sha(bundle / name), name
        (staged / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(staged.iterdir())
                                                if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output}; NVMe DT + clean handoff added; kernel unchanged.')

if __name__ == '__main__':
    main()
