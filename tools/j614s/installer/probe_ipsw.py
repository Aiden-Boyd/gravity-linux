#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only compatibility probe for the J614s macOS restore IPSW."""

from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stdout
import json
import os
import plistlib
import sys
import zipfile


SKIP_MANIFEST_KEYS = {
    "BaseSystem",
    "OS",
    "Ap,SystemVolumeCanonicalMetadata",
    "RestoreRamDisk",
    "RestoreTrustCache",
}


def open_zip(source: str):
    if source.startswith(("http://", "https://")):
        # bootstrap.sh runs us with CWD set to the unpacked Asahi installer.
        # Add it explicitly so the probe can reuse Asahi's range-backed
        # urlcache implementation without downloading the whole IPSW.
        sys.path.insert(0, os.getcwd())
        try:
            import urlcache  # provided by the packaged Asahi installer
        except ImportError as exc:
            raise SystemExit(
                "remote probe requires Asahi's bundled urlcache module"
            ) from exc
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


def restore_strategy(bless2: dict) -> tuple[str, str]:
    explicit = bless2.get("RestoreBundlePath")
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit:
            raise RuntimeError(f"invalid RestoreBundlePath: {explicit!r}")
        path = os.path.normpath(explicit)
        if (
            os.path.isabs(path)
            or path in (".", "..")
            or path.startswith("../")
            or "\x00" in path
        ):
            raise RuntimeError(f"unsafe RestoreBundlePath: {explicit!r}")
        return "legacy-explicit", path

    if bless2.get("SupportsPairedRecovery") is True:
        return "paired-implicit", "restore"

    raise RuntimeError(
        "bless2 has neither RestoreBundlePath nor SupportsPairedRecovery"
    )


def check_stub_inputs(zf: zipfile.ZipFile, identity: dict) -> dict:
    """Verify every public IPSW input that current Asahi stub.py consumes."""
    names = set(zf.namelist())
    missing = []

    required_files = {
        "BuildManifest.plist",
        "SystemVersion.plist",
        "RestoreVersion.plist",
        "PlatformSupport.plist",
        "usr/standalone/bootcaches.plist",
        "BootabilityBundle/Restore/Firmware/Bootability.dmg.trustcache",
    }

    for path in sorted(required_files):
        if path not in names:
            missing.append(path)

    required_prefixes = {
        "BootabilityBundle/Restore/Bootability/",
        "Firmware/Manifests/restore/macOS Customer/",
    }
    for prefix in sorted(required_prefixes):
        if not any(name.startswith(prefix) for name in names):
            missing.append(prefix + "*")

    manifest_paths = []
    selected_manifest = identity.get("Manifest", {})
    for key, value in selected_manifest.items():
        if key in SKIP_MANIFEST_KEYS or key.startswith("Cryptex"):
            continue
        try:
            path = value["Info"]["Path"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"identity Manifest entry {key!r} has no Info/Path"
            ) from exc
        manifest_paths.append(path)
        if path not in names:
            missing.append(path)

    try:
        base_system = selected_manifest["BaseSystem"]["Info"]["Path"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("selected J614s identity has no BaseSystem path") from exc

    if base_system not in names:
        missing.append(base_system)

    if missing:
        sample = ", ".join(missing[:12])
        if len(missing) > 12:
            sample += f", ... (+{len(missing) - 12} more)"
        raise RuntimeError(f"required stub inputs are missing: {sample}")

    return {
        "base_system": base_system,
        "base_system_aea": base_system.endswith(".aea"),
        "manifest_paths_checked": len(set(manifest_paths)),
        "required_files_checked": len(required_files),
        "required_prefixes_checked": len(required_prefixes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="IPSW path or HTTPS URL")
    parser.add_argument("--board-id", type=lambda value: int(value, 0), default=0x4)
    parser.add_argument("--chip-id", type=lambda value: int(value, 0), default=0x6040)
    parser.add_argument("--device-class", default="j614sap")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dump-bless2",
        action="store_true",
        help="print the public IPSW bless2 dictionary as XML for bring-up analysis",
    )
    args = parser.parse_args()

    owner = None
    zf = None
    try:
        # Asahi's URLCache prints its range-download spinner to stdout. Keep
        # --json stdout strictly machine-readable by sending that progress to
        # stderr while the remote ZIP metadata/plists are being read.
        progress_context = (
            redirect_stdout(sys.stderr) if args.json else nullcontext()
        )
        with progress_context:
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

            strategy, restore_path = restore_strategy(bless2)
            inputs = check_stub_inputs(zf, identity)

        result = {
            "product_version": sysver.get("ProductVersion"),
            "product_build": sysver.get("ProductBuildVersion"),
            "device_class": info.get("DeviceClass"),
            "board_id": identity.get("ApBoardID"),
            "chip_id": identity.get("ApChipID"),
            "variant": info.get("Variant"),
            "restore_behavior": info.get("RestoreBehavior"),
            "base_system": inputs["base_system"],
            "base_system_aea": inputs["base_system_aea"],
            "bless2_keys": sorted(bless2.keys()),
            "restore_strategy": strategy,
            "restore_bundle_path": restore_path,
            "supports_paired_recovery": bless2.get("SupportsPairedRecovery") is True,
            "supports_external_preboot_objects": (
                bless2.get("SupportsExternalPrebootObjects") is True
            ),
            "manifest_paths_checked": inputs["manifest_paths_checked"],
            "required_files_checked": inputs["required_files_checked"],
            "required_prefixes_checked": inputs["required_prefixes_checked"],
        }

        if args.dump_bless2:
            print("bless2 plist:")
            print(
                plistlib.dumps(
                    {"bless2": bless2}, fmt=plistlib.FMT_XML
                ).decode()
            )

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
                "BaseSystem AEA:       "
                + ("yes" if result["base_system_aea"] else "no")
            )
            print(f"bless2 keys:          {', '.join(result['bless2_keys'])}")
            print(f"Restore strategy:     {result['restore_strategy']}")
            print(f"Restore bundle path:  {result['restore_bundle_path']}")
            print(
                "Stub inputs checked:  "
                f"{result['required_files_checked']} fixed files, "
                f"{result['required_prefixes_checked']} trees, "
                f"{result['manifest_paths_checked']} manifest paths"
            )

        if not result["supports_external_preboot_objects"]:
            raise RuntimeError(
                "J614s bless2 does not advertise SupportsExternalPrebootObjects"
            )

        if not args.json:
            print(
                "PROBE PASS: J614s identity, paired-Recovery strategy, and "
                "stub input plan are compatible."
            )
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
