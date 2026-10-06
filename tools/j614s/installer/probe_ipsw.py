#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only compatibility probe for the J614s macOS restore IPSW."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import sys
import zipfile


def open_zip(source: str):
    if source.startswith(("http://", "https://")):
        # When this script is launched by bootstrap.sh, the current working
        # directory is the unpacked Asahi installer release. The script itself
        # lives in the Gravity source tree, so add CWD explicitly before
        # importing Asahi's packaged urlcache/util modules.
        sys.path.insert(0, os.getcwd())
        try:
            import urlcache  # provided by the packaged Asahi installer
        except ImportError as exc:
            raise SystemExit("remote probe requires Asahi's bundled urlcache module") from exc
        owner = urlcache.URLCache(source)
        return owner, zipfile.ZipFile(owner)

    owner = open(source, "rb")
    return owner, zipfile.ZipFile(owner)


def read_plist(zf: zipfile.ZipFile, path: str):
    try:
        with zf.open(path) as fd:
            return plistlib.load(fd)
    except KeyError as exc:
        raise RuntimeError(f"missing required IPSW member: {path}") from exc


def select_identity(
    manifest: dict, *, board_id: int, chip_id: int, device_class: str
):
    want_board = f"0x{board_id:02X}"
    want_chip = f"0x{chip_id:04X}"
    matches = []

    for identity in manifest.get("BuildIdentities", []):
        info = identity.get("Info", {})
        if (
            identity.get("ApBoardID") == want_board
            and identity.get("ApChipID") == want_chip
            and info.get("DeviceClass") == device_class
            and info.get("RestoreBehavior") == "Erase"
            and info.get("Variant") == "macOS Customer"
        ):
            matches.append(identity)

    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one J614s erase identity, got {len(matches)}"
        )

    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="IPSW path or HTTPS URL")
    parser.add_argument("--board-id", type=lambda value: int(value, 0), default=0x4)
    parser.add_argument("--chip-id", type=lambda value: int(value, 0), default=0x6040)
    parser.add_argument("--device-class", default="j614sap")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    owner = None
    zf = None
    try:
        owner, zf = open_zip(args.source)

        manifest = read_plist(zf, "BuildManifest.plist")
        bootcaches = read_plist(zf, "usr/standalone/bootcaches.plist")
        sysver = read_plist(zf, "SystemVersion.plist")

        identity = select_identity(
            manifest,
            board_id=args.board_id,
            chip_id=args.chip_id,
            device_class=args.device_class,
        )
        info = identity["Info"]

        bless2 = bootcaches.get("bless2")
        if not isinstance(bless2, dict):
            raise RuntimeError("bootcaches.plist has no bless2 dictionary")

        restore_path = bless2.get("RestoreBundlePath")
        base_system = (
            identity.get("Manifest", {})
            .get("BaseSystem", {})
            .get("Info", {})
            .get("Path")
        )
        if not base_system:
            raise RuntimeError("selected J614s identity has no BaseSystem path")

        names = set(zf.namelist())
        if base_system not in names:
            raise RuntimeError(f"BaseSystem member is absent from IPSW: {base_system}")

        result = {
            "product_version": sysver.get("ProductVersion"),
            "product_build": sysver.get("ProductBuildVersion"),
            "device_class": info.get("DeviceClass"),
            "board_id": identity.get("ApBoardID"),
            "chip_id": identity.get("ApChipID"),
            "variant": info.get("Variant"),
            "restore_behavior": info.get("RestoreBehavior"),
            "base_system": base_system,
            "base_system_aea": base_system.endswith(".aea"),
            "bless2_keys": sorted(bless2.keys()),
            "restore_bundle_path": restore_path,
        }

        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("J614s IPSW read-only compatibility probe")
            print("=======================================")
            print(
                f"Build:               {result['product_version']} "
                f"({result['product_build']})"
            )
            print(
                f"Identity:            {result['device_class']} / "
                f"{result['chip_id']} / board {result['board_id']}"
            )
            print(
                f"Restore behavior:    {result['restore_behavior']} / "
                f"{result['variant']}"
            )
            print(f"BaseSystem:           {result['base_system']}")
            print(
                f"BaseSystem AEA:       "
                f"{'yes' if result['base_system_aea'] else 'no'}"
            )
            print(f"bless2 keys:          {', '.join(result['bless2_keys'])}")
            print(f"RestoreBundlePath:    {restore_path!r}")

        if not restore_path:
            print(
                "PROBE FAIL: bootcaches bless2 has no RestoreBundlePath; "
                "stock Asahi stub construction is not compatible with this IPSW.",
                file=sys.stderr,
            )
            return 2

        print("PROBE PASS: required stock Asahi stub metadata is present.")
        return 0
    except Exception as exc:
        print(f"PROBE FAIL: {exc}", file=sys.stderr)
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
