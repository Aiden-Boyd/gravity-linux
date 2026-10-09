#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Add locally extracted Mriya firmware to a copy of a tested RAM bundle.

Usage: python3 repack-local-radio.py keys fw-raw radio
Firmware stays on this computer. No kernel compilation or automatic boot.
"""
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

UPSTREAM = 'e93743d52178b3e26e428fa05174ef549abf30cb'
MODULES = {
    'wifi': 'd687bae98ad8aca35a607c04578ca1d64a3b35f9f9527abfe716cad186342b9f',
    'bluetooth': 'aa12e6cd684ed5b55d732db1f040d84570537bacc991d03ee6f854cbb232c369',
    'core': '1f1527b3a0178ea1fbf633f1aced57d78557ffb326d99f1001b5ad880a29393e',
    'cpio': 'cdf0058de83f2de8e9e65e5ecb6946f0ce5d57dd5e05839bf5375509964b634a',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    bundle, raw, output = map(lambda p: Path(p).resolve(), sys.argv[1:])
    if output.exists():
        raise SystemExit(f'{output} already exists; choose a new output directory.')
    if not shutil.which('cpio'):
        raise SystemExit('cpio is required on the Linux host.')
    wifi_source = raw / 'C-4388__s-C2'
    bt_source = raw / 'bluetooth'
    if not (wifi_source / 'mriya.trx').is_file() or not bt_source.is_dir():
        raise SystemExit('Expected fw-raw/C-4388__s-C2/mriya.trx and fw-raw/bluetooth.')
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=bundle, check=True)
    if (bundle / 'PROFILE.txt').read_text().strip() != 'diagnostic':
        raise SystemExit('This helper requires the tested diagnostic/input bundle.')
    kernel_hash = digest((bundle / 'Image.gz').read_bytes())
    dtb_hash = digest((bundle / 't6040-j614s.dtb').read_bytes())

    with tempfile.TemporaryDirectory(prefix='j614s-radio-') as temp:
        work = Path(temp)
        package = work / 'asahi_firmware'
        package.mkdir()
        (package / '__init__.py').write_text('')
        for name, expected in MODULES.items():
            url = f'https://raw.githubusercontent.com/AsahiLinux/asahi-installer/{UPSTREAM}/asahi_firmware/{name}.py'
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if digest(data) != expected:
                raise SystemExit(f'Upstream hash mismatch: {name}')
            if name == 'wifi':
                # Upstream excludes C2 from macOS 14.6.1 as broken. This is an
                # explicit experimental use of the user's newer C2 files only;
                # the original files and upstream checkout are never modified.
                skip = b'            if "C-4388__s-C2" in dirnames:\n                dirnames.remove("C-4388__s-C2")\n'
                if data.count(skip) != 1:
                    raise SystemExit('Upstream C2 exclusion changed.')
                data = data.replace(skip, b'')
            (package / (name + '.py')).write_bytes(data)
        sys.path.insert(0, str(work))
        wifi = importlib.import_module('asahi_firmware.wifi')
        bluetooth = importlib.import_module('asahi_firmware.bluetooth')
        # Limit conversion to this board/chip; preserve chip and stepping in
        # the directory name for the upstream dimensional filename parser.
        source = work / 'source'
        source.mkdir()
        shutil.copytree(wifi_source, source / wifi_source.name)
        converted = dict(wifi.WiFiFWCollection(source).files())
        converted.update({name: fw for name, fw in bluetooth.BluetoothFWCollection(bt_source).files()
                          if name.startswith('brcm/brcmbt4388c2-apple,mriya-')})
        for vendor in ('a', 'u'):
            for ext in ('bin', 'ptb'):
                if f'brcm/brcmbt4388c2-apple,mriya-{vendor}.{ext}' not in converted:
                    raise SystemExit(f'Missing Bluetooth {vendor}.{ext}')
        if not any(name.endswith('.bin') and 'brcmfmac4388c2' in name for name in converted):
            raise SystemExit('No Wi-Fi binaries converted.')

        root = work / 'root'
        root.mkdir()
        archive = gzip.decompress((bundle / 'initramfs.cpio.gz').read_bytes())
        subprocess.run(['cpio', '-id', '--no-absolute-filenames'], input=archive, cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        firmware = root / 'lib' / 'firmware'
        if not firmware.resolve().is_relative_to(root):
            raise SystemExit('Firmware path escapes unpacked initramfs.')
        firmware.mkdir(parents=True, exist_ok=True)
        manifest = []
        for name, fw in sorted(converted.items()):
            destination = firmware / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(fw.data)
            manifest.append({'destination': name, 'source': fw.name, 'sha256': digest(fw.data)})
        # Use the host's signed regulatory database when installed.
        for hostdir in (Path('/lib/firmware'), Path('/usr/lib/firmware')):
            if all((hostdir / name).is_file() for name in ('regulatory.db', 'regulatory.db.p7s')):
                for name in ('regulatory.db', 'regulatory.db.p7s'):
                    shutil.copyfile(hostdir / name, firmware / name)
                break

        names = ['.'] + sorted('./' + str(p.relative_to(root)) for p in root.rglob('*'))
        packed = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'],
                                input=('\0'.join(names) + '\0').encode(), cwd=root, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        staged = work / 'bundle'
        shutil.copytree(bundle, staged)
        (staged / 'initramfs.cpio.gz').write_bytes(gzip.compress(packed, compresslevel=9, mtime=0))
        (staged / 'LOCAL_FIRMWARE.json').write_text(json.dumps({
            'converter_commit': UPSTREAM,
            'note': 'Experimental newer macOS C2 source; upstream 14.6.1 exclusion bypassed locally. No generic firmware aliases.',
            'files': manifest,
        }, indent=2) + '\n')
        assert digest((staged / 'Image.gz').read_bytes()) == kernel_hash
        assert digest((staged / 't6040-j614s.dtb').read_bytes()) == dtb_hash
        (staged / 'SHA256SUMS').write_text(''.join(
            f'{digest(p.read_bytes())}  {p.name}\n' for p in sorted(staged.iterdir())
            if p.is_file() and p.name != 'SHA256SUMS'))
        subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=staged, check=True)
        shutil.copytree(staged, output)
    print(f'READY: {output.name}; kernel and DTB unchanged; {len(converted)} firmware files added.')
    print('Keep this bundle private: it includes your locally extracted firmware.')


if __name__ == '__main__':
    main()
