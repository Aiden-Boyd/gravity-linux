#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deep, non-APFS probe of the real J614s BaseSystem AEA.

Downloads only the selected BaseSystem member from the IPSW into a temporary
folder, decrypts it with the pinned blacktop/ipsw helper, validates that the
result is a readable disk image, then deletes the temporary files.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

from probe_ipsw import open_zip, read_plist, select_identity


CHUNK = 16 * 1024 * 1024


def human(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{n} B"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="IPSW path or HTTPS URL")
    parser.add_argument("--tool", required=True, help="Path to pinned ipsw helper")
    parser.add_argument("--board-id", type=lambda value: int(value, 0), default=0x4)
    parser.add_argument("--chip-id", type=lambda value: int(value, 0), default=0x6040)
    parser.add_argument("--device-class", default="j614sap")
    args = parser.parse_args()

    tool = os.path.abspath(args.tool)
    if not os.path.isfile(tool) or not os.access(tool, os.X_OK):
        print(f"DEEP PROBE FAIL: helper is not executable: {tool}", file=sys.stderr)
        return 1

    owner = None
    zf = None
    try:
        owner, zf = open_zip(args.source)
        manifest = read_plist(zf, "BuildManifest.plist")
        identity = select_identity(
            manifest,
            board_id=args.board_id,
            chip_id=args.chip_id,
            device_class=args.device_class,
        )
        base_system = identity["Manifest"]["BaseSystem"]["Info"]["Path"]
        info = zf.getinfo(base_system)

        if not base_system.endswith(".aea"):
            print(f"DEEP PROBE FAIL: expected AEA BaseSystem, got {base_system}", file=sys.stderr)
            return 1

        # The decrypted image can be substantially larger than the AEA member.
        # Refuse to start unless /tmp has a generous safety margin.
        free = shutil.disk_usage("/tmp").free
        required = max(8 * 1024**3, info.file_size * 4)
        print("J614s BaseSystem AEA deep probe")
        print("==============================")
        print(f"BaseSystem:         {base_system}")
        print(f"AEA member size:    {human(info.file_size)}")
        print(f"Temporary free:     {human(free)}")
        print(f"Required free:      {human(required)}")
        print("Disk/boot changes:  none")
        print()

        if free < required:
            print(
                "DEEP PROBE FAIL: insufficient temporary free space for safe "
                "download/decryption",
                file=sys.stderr,
            )
            return 2

        with tempfile.TemporaryDirectory(prefix="j614s-base-system-") as tmp:
            aea_path = os.path.join(tmp, os.path.basename(base_system))
            outdir = os.path.join(tmp, "decrypted")
            os.makedirs(outdir)

            print("Downloading only the BaseSystem AEA member...")
            done = 0
            with zf.open(info) as src, open(aea_path, "wb") as dst:
                while True:
                    block = src.read(CHUNK)
                    if not block:
                        break
                    dst.write(block)
                    done += len(block)
                    pct = done * 100 / info.file_size
                    print(f"  {pct:5.1f}%  {human(done)}", end="\r", flush=True)
            print()

            if os.path.getsize(aea_path) != info.file_size:
                raise RuntimeError(
                    "BaseSystem download size mismatch: "
                    f"{os.path.getsize(aea_path)} != {info.file_size}"
                )

            print("Decrypting BaseSystem AEA with pinned blacktop/ipsw...")
            subprocess.run(
                [tool, "fw", "aea", aea_path, "-o", outdir],
                check=True,
            )

            expected = os.path.join(
                outdir, os.path.basename(base_system[:-4])
            )
            if not os.path.isfile(expected):
                candidates = [
                    os.path.join(outdir, name)
                    for name in os.listdir(outdir)
                    if name.endswith(".dmg")
                ]
                if len(candidates) != 1:
                    raise RuntimeError(
                        f"expected one decrypted DMG, found {candidates!r}"
                    )
                expected = candidates[0]

            size = os.path.getsize(expected)
            if size <= 0:
                raise RuntimeError("decrypted BaseSystem DMG is empty")

            print(f"Decrypted DMG:      {os.path.basename(expected)}")
            print(f"Decrypted size:     {human(size)}")
            print("Validating disk-image structure with hdiutil imageinfo...")
            subprocess.run(
                ["/usr/bin/hdiutil", "imageinfo", expected],
                check=True,
                stdout=subprocess.DEVNULL,
            )

        print()
        print(
            "DEEP PROBE PASS: the real J614s BaseSystem AEA downloaded, "
            "decrypted, and parsed as a disk image."
        )
        print("Temporary probe files were removed.")
        return 0
    except Exception as exc:
        print(f"DEEP PROBE FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if zf is not None:
            zf.close()
        if owner is not None:
            if hasattr(owner, "close_connection"):
                owner.close_connection()
            elif hasattr(owner, "close"):
                owner.close()


if __name__ == "__main__":
    raise SystemExit(main())
