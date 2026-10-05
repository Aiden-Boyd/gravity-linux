#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Boot the development Image/initramfs on QEMU virt, not Apple hardware."""
import argparse
import os
from pathlib import Path
import selectors
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("initramfs")
    parser.add_argument("log")
    args = parser.parse_args()
    # The development kernel uses 16 KiB pages; cortex-a72 only supports 4/64 KiB.
    command = [
        "qemu-system-aarch64", "-machine", "virt", "-accel", "tcg", "-cpu", "max",
        "-m", "1024", "-smp", "2", "-nographic", "-no-reboot",
        "-nic", "none",
        "-object", "rng-random,id=rng0,filename=/dev/urandom",
        "-device", "virtio-rng-device,rng=rng0",
        "-kernel", args.image, "-initrd", args.initramfs,
        "-append", "console=ttyAMA0 ignore_loglevel nokaslr initcall_debug sysrq_always_enabled=1 rdinit=/init panic=-1 j614s.selftest=1",
    ]
    output = bytearray()
    sent = False
    dumped = False
    broke = False
    passed = False
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            for key, _ in selector.select(timeout=1):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("QEMU exited before the shell test passed:\n" +
                                       output[-8192:].decode(errors="replace"))
                output.extend(chunk)
            if not broke and time.monotonic() > deadline - 35:
                process.stdin.write(b"\x01b")
                process.stdin.flush()
                broke = True
            if not dumped and time.monotonic() > deadline - 33:
                # QEMU stdio multiplexor: serial BREAK then SysRq task dump.
                process.stdin.write(b"t\x01cinfo registers\nx/32gx $sp\ncpu 1\ninfo registers\nx/32gx $sp\n")
                process.stdin.flush()
                dumped = True
            if not sent and b"j614s> " in output:
                process.stdin.write(b"printf '%s%s\\n' J614S_INTERACTIVE_ PASS\n")
                process.stdin.flush()
                sent = True
            if all(marker in output for marker in (
                b"J614S_INITRAMFS_READY", b"J614S_SHELL_PASS",
                b"J614S_INTERACTIVE_PASS",
            )):
                passed = True
                break
        if not passed:
            raise RuntimeError("Timed out waiting for an interactive initramfs shell")
    finally:
        selector.close()
        process.terminate()
        try:
            tail, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            tail, _ = process.communicate()
        output.extend(tail)
        Path(args.log).write_bytes(output)
    print("PASS: QEMU virt reached the RAM-only interactive shell; Apple hardware remains untested")


if __name__ == "__main__":
    main()
