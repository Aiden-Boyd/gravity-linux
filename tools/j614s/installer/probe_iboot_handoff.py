#!/usr/bin/env python3
"""Read-only J614s Gravity iBoot/m1n1 handoff audit.

Does not mount volumes, invoke bputil, or modify boot policy. Example:
 python3 tools/j614s/installer/probe_iboot_handoff.py \
   --preboot /Volumes/Preboot --system '/Volumes/Gravity Linux J614s Dev' \
   --vgid <GRAVITY_VOLUME_GROUP_UUID> \
   --m1n1 tools/j614s/m1n1/m1n1-v1.9.9-j614s.4-chainloading.bin \
   --panic /Volumes/Preboot/DiagnosticReports/panic-base+socd-....panic
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import plistlib
import re
import sys


HASH96 = re.compile(r"[0-9a-fA-F]{96}\Z")
CUSTOM = re.compile(r"kernelcache\.custom\.([0-9a-fA-F]{96})\Z")
PANIC_CODE = re.compile(r"iBoot Panic:\s*:\s*([0-9a-f]+:\d+)")
TAG = re.compile(r"\b(?:3000[cd f]|f000[57]|f010[06])\(([0-9a-fA-F]{8})\)".replace(" ", ""))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plist_version(path: Path) -> str:
    with path.open("rb") as fd:
        obj = plistlib.load(fd)
    return f"{obj.get('ProductVersion', '?')} ({obj.get('ProductBuildVersion', '?')})"


def parse_panic(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fd:
        first = json.loads(fd.readline())
        second = json.load(fd)
    report = {
        "timestamp": first.get("timestamp", "unknown"),
        "os_version": first.get("os_version", "unknown"),
        "panic_type": second.get("panicString", "unknown"),
        "iboot_builds": set(),
        "panic_locations": set(),
        "firmware_tags": set(),
    }
    for container in second.get("SOCDContainers", []):
        payload = base64.b64decode(container["SOCDContainer"], validate=True)
        for match in re.finditer(rb"[\x20-\x7e\n]{12,}", payload):
            text = match.group().decode("ascii", errors="replace")
            report["iboot_builds"].update(re.findall(r"Build:\s*(RELEASE:iBoot-[\d.]+)", text))
            report["panic_locations"].update(PANIC_CODE.findall(text))
            for hex_tag in TAG.findall(text):
                label = bytes.fromhex(hex_tag).decode("ascii", errors="replace")
                if label.isprintable():
                    report["firmware_tags"].add(label)
    return report


def audit(preboot: Path, vgid: str, system: Path, m1n1: Path | None, panic: Path | None) -> list[str]:
    rows: list[str] = []
    root = preboot / vgid
    active = (root / "boot/active").read_text(encoding="ascii").strip()
    if not HASH96.fullmatch(active):
        raise ValueError("unexpected active boot pointer format (expected 96 hex digits)")
    active_dir = root / "boot" / active
    if not active_dir.is_dir():
        raise ValueError("active boot directory is missing")
    rows.append("ACTIVE_PREBOOT_POINTER: " + active)

    kc_dir = active_dir / "System/Library/Caches/com.apple.kernelcaches"
    customs = [p for p in kc_dir.glob("kernelcache.custom.*") if CUSTOM.fullmatch(p.name)]
    if len(customs) != 1:
        raise ValueError(f"expected exactly one custom image, found {len(customs)}")
    custom_path = customs[0]
    custom = custom_path.read_bytes()
    custom_hash = CUSTOM.fullmatch(custom_path.name).group(1)
    rows.append("CUSTOM_IMAGE_FILE: " + custom_path.name)
    rows.append("CUSTOM_IMAGE_BYTES: " + str(len(custom)))
    rows.append("CUSTOM_IMAGE_SHA256: " + digest(custom))
    rows.append("IMG4_WRAPPER: " + str(custom[:12].find(b"IMG4") >= 0 and b"IM4P" in custom[:40]))
    rows.append("CUSTOM_IMAGE_FUOS: " + str(b"fuos" in custom[:48]))
    rows.append("CUSTOM_POLICY_HASH_FROM_FILENAME: " + custom_hash)

    boot_path = system / "Finish Installation.app/Contents/Resources/boot.bin"
    boot = boot_path.read_bytes()
    rows.append("PACKAGED_M1N1_BYTES: " + str(len(boot)))
    rows.append("PACKAGED_M1N1_SHA256: " + digest(boot))
    offset = custom.find(boot)
    rows.append("M1N1_EXACTLY_EMBEDDED: " + str(offset >= 0))
    rows.append("M1N1_OFFSET_IN_IMG4: " + str(offset))
    if m1n1 is not None:
        original = m1n1.read_bytes()
        rows.append("LOCAL_M1N1_SHA256: " + digest(original))
        rows.append("PACKAGING_IS_ORIGINAL_PLUS_4_ZERO_BYTES: " + str(boot == original + b"\0" * 4))

    stub_version = system / "System/Library/CoreServices/SystemVersion.plist"
    restore_version = root / "restore/SystemVersion.plist"
    rows.append("STUB_OS_VERSION: " + plist_version(stub_version))
    rows.append("RESTORE_OS_VERSION: " + plist_version(restore_version))
    iboot = active_dir / "usr/standalone/firmware/iBoot.img4"
    rows.append("ACTIVE_IBOOT_FILE: " + str(iboot))
    if iboot.is_file():
        rows.append("ACTIVE_IBOOT_SHA256: " + digest(iboot.read_bytes()))
        rows.append("ACTIVE_IBOOT_BYTES: " + str(iboot.stat().st_size))
    else:
        rows.append("ACTIVE_IBOOT_MISSING: True")

    if panic is not None:
        info = parse_panic(panic)
        for key in ("timestamp", "os_version", "panic_type"):
            rows.append("PANIC_" + key.upper() + ": " + str(info[key]))
        for key in ("iboot_builds", "panic_locations", "firmware_tags"):
            rows.append("PANIC_" + key.upper() + ": " + ", ".join(sorted(info[key])))
    rows.append("NOTE: Evidence of proper packaging is not evidence that iBoot executed m1n1.")
    rows.append("NOTE: iBoot panic source-location identifiers are not root-cause classifications.")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preboot", type=Path, required=True, help="mounted Gravity Preboot volume")
    parser.add_argument("--vgid", required=True, help="Gravity APFS volume group UUID")
    parser.add_argument("--system", type=Path, required=True, help="mounted Gravity stub System volume")
    parser.add_argument("--m1n1", type=Path, help="pinned original m1n1 binary, optional")
    parser.add_argument("--panic", type=Path, help="SOCD iBoot panic report, optional")
    args = parser.parse_args()
    try:
        print("\n".join(audit(args.preboot, args.vgid, args.system, args.m1n1, args.panic)))
    except (ValueError, OSError, KeyError, json.JSONDecodeError, plistlib.InvalidFileException) as exc:
        print(f"AUDIT ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
