#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Initialize and cleanly stop ANS before the unmodified m1n1 Linux loader."""
import pathlib
import runpy
import sys

checkout = pathlib.Path(sys.argv[1]).resolve()
loader_args = sys.argv[2:]
sys.path.insert(0, str(checkout / 'proxyclient'))
from m1n1.setup import p

print('NVMe: initializing m1n1 controller for clean Linux handoff; no disk writes.')
if not p.nvme_init():
    raise SystemExit('STOP: m1n1 NVMe initialization failed; Linux was not booted.')
p.nvme_shutdown()
print('NVMe: clean shutdown complete; loading Linux.')
loader = checkout / 'proxyclient/tools/linux.py'
sys.argv = [str(loader), *loader_args]
runpy.run_path(str(loader), run_name='__main__')
