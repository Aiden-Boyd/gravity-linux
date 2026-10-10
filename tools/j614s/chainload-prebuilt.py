#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Usage: python3 chainload-prebuilt.py m1n1 gravity-standalone.bin
Use the upstream raw loader with a verified, position-independent copy stub.
"""
import hashlib
from pathlib import Path
import re
import runpy
import struct
import sys

if len(sys.argv) != 3:
    raise SystemExit(__doc__)
checkout, payload = (Path(s).resolve() for s in sys.argv[1:])
here = Path(__file__).resolve().parent
for line in (here / 'SHA256SUMS').read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    name = name.lstrip('*')
    if Path(name).name != name:
        raise SystemExit('Unexpected checksum path.')
    if hashlib.sha256((here / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Checksum mismatch: {name}')
stub = (here / 'chainload-stub.bin').read_bytes()
if len(stub) != 48 or stub[-8:] != bytes(8):
    raise SystemExit('Unexpected stub layout.')
sys.path.insert(0, str(checkout / 'proxyclient'))
from m1n1 import asm

class PrebuiltStub:
    def __init__(self, source, addr=0):
        expected = r'1:ldpx4,x5,\[x1\],#16stpx4,x5,\[x2\]dccvau,x2icivau,x2addx2,x2,#16subx3,x3,#16cbnzx3,1bldrx1,=(0x[0-9a-fA-F]+|[0-9]+)brx1'
        match = re.fullmatch(expected, re.sub(r'\s+', '', source))
        if not match:
            raise RuntimeError('Upstream stub changed; refusing substitution.')
        self.addr = self.start = addr
        self.data = stub[:-8] + struct.pack('<Q', int(match.group(1), 0))
        self.len = len(self.data)
        self.end = addr + self.len

asm.ARMAsm = PrebuiltStub
sys.argv = [str(checkout / 'proxyclient/tools/chainload.py'), '-r', str(payload)]
runpy.run_path(sys.argv[0], run_name='__main__')
