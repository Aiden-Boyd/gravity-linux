#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Guarded cleanup of an interrupted J614s stub APFS container.

This deliberately deletes only the tiny, separately-created partial
"Gravity Linux J614s Dev" APFS container. It never resizes the macOS
container and it does not convert the old physical-store partition to free
space; bootstrap asks the user to inspect diskutil output after deletion.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys


EXPECTED_NAMES = {
    "Gravity Linux J614s Dev - Data",
    "Gravity Linux J614s Dev",
    "Preboot",
    "Recovery",
}


def plist_cmd(*args: str) -> dict:
    proc = subprocess.run(
        list(args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return plistlib.loads(proc.stdout)


def find_candidate(apfs: dict, data_dev: str):
    containers = apfs.get("Containers", [])
    boot_container = None
    for container in containers:
        for volume in container.get("Volumes", []):
            if volume.get("DeviceIdentifier") == data_dev:
                boot_container = container.get("ContainerReference")
                break

    if not boot_container:
        raise RuntimeError("cannot identify the booted macOS APFS container")

    candidates = []
    for container in containers:
        cref = container.get("ContainerReference")
        if not cref or cref == boot_container:
            continue

        volumes = container.get("Volumes", [])
        names = {v.get("Name") for v in volumes}
        if names != EXPECTED_NAMES:
            continue

        capacity = int(container.get("CapacityCeiling") or 0)
        if not (2_400_000_000 <= capacity <= 2_600_000_000):
            continue

        stores = container.get("PhysicalStores", [])
        if len(stores) != 1:
            continue
        store = stores[0].get("DeviceIdentifier")
        if not store:
            continue

        roles = {
            v.get("Name"): tuple(v.get("Roles") or [])
            for v in volumes
        }
        if roles.get("Gravity Linux J614s Dev - Data") != ("Data",):
            continue
        if roles.get("Gravity Linux J614s Dev") != ("System",):
            continue
        if roles.get("Preboot") != ("Preboot",):
            continue
        if roles.get("Recovery") != ("Recovery",):
            continue

        candidates.append((cref, store, capacity, volumes))

    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one guarded partial J614s stub container, "
            f"found {len(candidates)}"
        )

    return boot_container, candidates[0]


def main() -> int:
    apfs = plist_cmd("diskutil", "apfs", "list", "-plist")
    data_info = plist_cmd("diskutil", "info", "-plist", "/System/Volumes/Data")
    data_dev = data_info.get("DeviceIdentifier")
    if not data_dev:
        print("ERROR: cannot identify the booted macOS Data volume", file=sys.stderr)
        return 1

    try:
        boot_container, candidate = find_candidate(apfs, data_dev)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("No disk changes were made.", file=sys.stderr)
        return 2

    cref, store, capacity, volumes = candidate

    print("Guarded partial-stub cleanup")
    print("============================")
    print(f"Booted macOS container: {boot_container}  (WILL NOT BE TOUCHED)")
    print(f"Partial stub container: {cref}")
    print(f"Physical store:         {store}")
    print(f"Capacity:               {capacity / 1_000_000_000:.2f} GB")
    print("Volumes:")
    for volume in volumes:
        print(
            f"  {volume.get('DeviceIdentifier')}: "
            f"{volume.get('Name')} ({', '.join(volume.get('Roles') or ['no role'])})"
        )

    print()
    print("This will permanently delete ONLY the partial stub container above.")
    print("It will not resize Macintosh HD.")
    token = input(f"Type exactly 'DELETE {cref}' to continue: ").strip()
    if token != f"DELETE {cref}":
        print("Cancelled. No disk changes were made.")
        return 3

    subprocess.run(["diskutil", "apfs", "deleteContainer", cref], check=True)

    print()
    print("Partial APFS container deletion completed.")
    print(f"Former physical-store partition: {store}")
    print("Do not erase or resize anything else yet.")
    print("Run 'diskutil list' and paste the result for the next guarded step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
