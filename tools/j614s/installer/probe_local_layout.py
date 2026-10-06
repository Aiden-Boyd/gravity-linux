#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only probe of the currently booted macOS Preboot/paired-Recovery layout."""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
from pathlib import Path

UUID_RE = re.compile(r"^[0-9A-Fa-f-]{36}$")


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def plist(path: Path):
    with path.open("rb") as fd:
        return plistlib.load(fd)


def rel_entries(root: Path, max_depth: int = 3):
    out = []
    if not root.exists():
        return out
    root_depth = len(root.parts)
    for base, dirs, files in os.walk(root):
        basep = Path(base)
        depth = len(basep.parts) - root_depth
        if depth >= max_depth:
            dirs[:] = []
        for name in sorted(dirs):
            out.append(str((basep / name).relative_to(root)) + "/")
        for name in sorted(files):
            out.append(str((basep / name).relative_to(root)))
    return out


def main() -> int:
    print("J614s local macOS layout probe")
    print("=============================")
    print("Mode: read-only")
    print()

    info = run("diskutil", "info", "/")
    print("Boot volume info:")
    for line in info.splitlines():
        if any(key in line for key in (
            "Device Identifier",
            "Volume Name",
            "APFS Volume Group",
            "APFS Snapshot",
            "FileVault",
        )):
            print(" ", line.strip())

    preboot = Path("/System/Volumes/Preboot")
    if not preboot.is_dir():
        raise SystemExit("Preboot is not mounted at /System/Volumes/Preboot")

    candidates = [p for p in preboot.iterdir() if p.is_dir() and UUID_RE.match(p.name)]
    print()
    print(f"Preboot VGID directories: {len(candidates)}")

    bootcaches = Path("/usr/standalone/bootcaches.plist")
    if bootcaches.exists():
        bc = plist(bootcaches)
        bless2 = bc.get("bless2", {})
        print("Current /usr/standalone/bootcaches.plist bless2:")
        print(json.dumps(bless2, indent=2, sort_keys=True, default=str))
    else:
        print("Current bootcaches.plist not found")

    print()
    for vg in sorted(candidates, key=lambda p: p.name):
        print(f"VGID {vg.name}")
        interesting = {
            "restore": vg / "restore",
            "Restore": vg / "Restore",
            "boot": vg / "boot",
            "System": vg / "System",
            "var_db": vg / "var/db",
        }
        for label, path in interesting.items():
            print(f"  {label:8}: {'yes' if path.exists() else 'no'}")

        # Print a shallow tree only; no file contents except plist metadata.
        entries = rel_entries(vg, max_depth=3)
        selected = [
            e for e in entries
            if (
                e.startswith(("restore", "Restore", "boot/", "System/", "var/db/"))
                or "Recovery" in e
                or "Restore" in e
                or "bootcaches.plist" in e
                or "SystemVersion.plist" in e
            )
        ]
        for e in selected[:200]:
            print(f"    {e}")

        for p in (
            vg / "restore/SystemVersion.plist",
            vg / "Restore/SystemVersion.plist",
            vg / "System/Library/CoreServices/SystemVersion.plist",
            vg / "restore/RestoreVersion.plist",
            vg / "Restore/RestoreVersion.plist",
            vg / "restore/bootcaches.plist",
            vg / "Restore/bootcaches.plist",
        ):
            if p.is_file():
                try:
                    data = plist(p)
                    print(f"  plist {p.relative_to(vg)}:")
                    # Keep output bounded and focused on version/bless information.
                    if isinstance(data, dict):
                        keep = {}
                        for k in (
                            "ProductVersion", "ProductBuildVersion", "BuildVersion",
                            "RestoreVersion", "bless2"
                        ):
                            if k in data:
                                keep[k] = data[k]
                        print(json.dumps(keep or {"keys": sorted(data.keys())}, indent=2, default=str))
                except Exception as exc:
                    print(f"  plist {p.relative_to(vg)}: unreadable ({exc})")

        print()

    # Recovery volumes may be mounted elsewhere; list them without mounting anything.
    print("APFS Recovery volumes (not mounted by this probe):")
    apfs = run("diskutil", "apfs", "list")
    capture = False
    for line in apfs.splitlines():
        if "APFS Volume Disk" in line and "Recovery" in line:
            capture = True
            print(" ", line.strip())
            continue
        if capture:
            if line.strip().startswith("+->") or line.strip().startswith("| +->"):
                capture = False
            elif any(k in line for k in ("Name:", "Role:", "Mount Point:", "Capacity Consumed:")):
                print(" ", line.strip())

    print()
    print("Probe complete. No disk, APFS, boot-policy, or Recovery changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
