#!/usr/bin/env python3
"""Read-only J614s Gravity boot handoff audit (macOS, Python 3 stdlib).

Does not mount, bless, change boot policy, alter security, or write files.
Run from macOS after manually mounting Gravity's Preboot read-only.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import plistlib
import re
import sys
import uuid

EXPECTED_M1N1_SHA256 = "29c9ac4542577e88e58734075d069835afac1a6b4db8b16b7aa7000942196411"
HEX_HASH = re.compile(r"[A-Fa-f0-9]{96}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return path.read_bytes()


def check(label, success, detail=""):
    print(f"{'PASS' if success else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    return success


def policy_values(policy_text):
    def capture(pattern):
        match = re.search(pattern, policy_text, re.MULTILINE)
        return match.group(1).strip() if match else None

    return {
        "nsih": capture(r"^Next Stage Image4 Hash\s+\(nsih\):\s*(\S+)"),
        "coih": capture(r"^CustomKC or fuOS Image4 Hash\s+\(coih\):\s*(\S+)"),
        "integrity": capture(r"^Pairing Integrity\s*:\s*(\S+)"),
        "security": capture(r"^Security Mode:\s*(.*)$"),
    }


def panic_summary(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            header = json.loads(handle.readline())
            report = json.loads(handle.read())
        panic = report.get("panicString", "unknown")
        version = report.get("build", header.get("os_version", "unknown"))
        codes = set()
        for entry in report.get("SOCDContainers", []):
            raw = base64.b64decode(entry.get("SOCDContainer", ""), validate=True)
            for match in re.findall(rb"iBoot Panic:[^\n\r\x00]{1,120}", raw):
                codes.add(match.decode("ascii", "replace"))
        return panic, version, sorted(codes)
    except (OSError, ValueError, UnicodeError, KeyError) as error:
        return f"unreadable: {error}", "unknown", []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vgid", required=True, help="Gravity APFS volume-group UUID")
    parser.add_argument("--preboot", type=Path, default=Path("/Volumes/Preboot"),
                        help="already mounted, read-only Gravity Preboot (default: /Volumes/Preboot)")
    parser.add_argument("--system", type=Path, default=Path("/Volumes/Gravity Linux J614s Dev"),
                        help="already mounted Gravity stub System volume")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent /
                        "m1n1/m1n1-v1.9.9-j614s.4-chainloading.bin",
                        help="pinned original m1n1 binary from this repo")
    parser.add_argument("--policy-file", type=Path, help="optional saved output of sudo bputil -d -v VGID")
    parser.add_argument("--panic", type=Path, help="optional panic report path (auto-find when omitted)")
    args = parser.parse_args(argv)
    try:
        vgid = str(uuid.UUID(args.vgid)).upper()
    except ValueError:
        parser.error("--vgid must be an APFS volume-group UUID")

    passed = []
    root = args.preboot / vgid
    boot_dir = root / "boot"
    print("Gravity J614s boot handoff audit — READ ONLY")
    print("No mount, disk, boot-policy, or security changes will be made.\n")

    if not check("Gravity Preboot directory accessible", root.is_dir(), str(root)):
        print("Mount the correct Gravity Preboot volume read-only and retry.")
        return 2

    active_file = boot_dir / "active"
    try:
        active = active_file.read_text(encoding="ascii").strip().upper()
    except (OSError, UnicodeError):
        check("Active boot pointer readable", False)
        return 2
    valid_active = bool(HEX_HASH.fullmatch(active))
    passed.append(check("Active boot pointer is a 96-digit image hash", valid_active))
    if not valid_active:
        return 2
    active_dir = boot_dir / active
    passed.append(check("Active boot-generation directory exists", active_dir.is_dir()))
    if not active_dir.is_dir():
        return 2

    custom_dir = active_dir / "System/Library/Caches/com.apple.kernelcaches"
    customs = sorted(custom_dir.glob("kernelcache.custom.*"))
    passed.append(check("Exactly one active custom kernelcache", len(customs) == 1,
                        f"found {len(customs)}"))
    custom = customs[0] if len(customs) == 1 else None

    boot_path = args.system / "Finish Installation.app/Contents/Resources/boot.bin"
    stage1 = None
    boot = None
    if args.source.is_file():
        stage1 = read(args.source)
        passed.append(check("Original m1n1 SHA-256 matches reviewed pin",
                            digest(stage1) == EXPECTED_M1N1_SHA256))
    else:
        print(f"SKIP  Local m1n1 source unavailable: {args.source}")
    if boot_path.is_file():
        boot = read(boot_path)
        passed.append(check("Installed boot.bin has expected original m1n1 + four NULs",
                            stage1 is not None and boot == stage1 + b"\x00" * 4))
    else:
        passed.append(check("Installed boot.bin exists", False))

    if custom:
        data = read(custom)
        has_img4 = all(token in data[:80] for token in (b"IMG4", b"IM4P", b"fuos"))
        passed.append(check("Custom image has IMG4/IM4P/fuOS markers", has_img4))
        offset = data.find(boot) if boot is not None else -1
        passed.append(check("Installed boot.bin embedded verbatim in active custom image",
                            offset >= 0, f"offset {offset}" if offset >= 0 else "not found"))
        suffix = custom.name.removeprefix("kernelcache.custom.").upper()
        passed.append(check("CustomKC filename suffix looks like an Image4 hash",
                            bool(HEX_HASH.fullmatch(suffix))))
    else:
        suffix = None

    for label, path in (
        ("Gravity stub", args.system / "System/Library/CoreServices/SystemVersion.plist"),
        ("Gravity Recovery", root / "restore/SystemVersion.plist"),
    ):
        try:
            item = plistlib.loads(read(path))
            print(f"INFO  {label}: {item.get('ProductVersion')} ({item.get('ProductBuildVersion')})")
        except (OSError, ValueError, TypeError) as error:
            passed.append(check(f"{label} metadata readable", False, str(error)))

    if args.policy_file:
        try:
            policy = policy_values(args.policy_file.read_text(encoding="utf-8"))
            passed.append(check("Local policy nsih matches active boot generation",
                                policy["nsih"] is not None and policy["nsih"].upper() == active))
            passed.append(check("Local policy coih matches custom kernelcache filename",
                                suffix is not None and policy["coih"] is not None and
                                policy["coih"].upper() == suffix))
            print(f"INFO  Pairing integrity: {policy['integrity'] or 'not reported'}")
            print(f"INFO  Security mode: {policy['security'] or 'not reported'}")
            print("NOTE  'Not Paired' when queried from a different macOS is not by itself a failure.")
        except OSError as error:
            passed.append(check("Read saved local policy", False, str(error)))
    else:
        print("SKIP  Policy comparison; provide --policy-file with saved bputil -d output")

    panic = args.panic
    if panic is None:
        reports = list((args.preboot / "DiagnosticReports").glob("panic-base+socd*.panic"))
        panic = max(reports, key=lambda p: p.stat().st_mtime) if reports else None
    if panic:
        msg, version, codes = panic_summary(panic)
        print(f"INFO  Panic: {msg}; OS: {version}")
        for code in codes[:3]:
            print(f"INFO  Encoded panic record: {code}")
        if "iBoot panic" in msg:
            print("NOTE  iBoot panic is confirmed, but its precise failing instruction is not decoded.")
    else:
        print("SKIP  No panic report found on the supplied Preboot mount")

    print(f"\nChecks: {sum(passed)} passed, {len(passed) - sum(passed)} failed")
    print("NOTE  Passing static checks do not prove iBoot executed m1n1.")
    return 1 if not all(passed) else 0


if __name__ == "__main__":
    sys.exit(main())
