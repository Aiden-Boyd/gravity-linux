#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only host firmware/Recovery preflight for J614s installer bring-up."""

from __future__ import annotations

import argparse
import json


def evaluate_alignment(info: dict) -> tuple[bool, list[str]]:
    """Return hard blockers for boot-policy work.

    SystemRecovery commonly lags the booted macOS/SFR version on otherwise
    normal Apple Silicon installations, so version skew alone is not a blocker.
    Likewise, current macOS can produce bputil output that older Asahi parsers
    do not recognize; an "Unknown" boot mode is therefore handled as a warning
    when the booted and default volume-group IDs still match.
    """
    reasons = []

    macos = info.get("macos_version")
    sfr = info.get("sfr_version")
    sros = info.get("system_recovery_version")

    if not macos or not sfr:
        missing = []
        if not macos:
            missing.append("macOS")
        if not sfr:
            missing.append("main firmware")
        reasons.append("missing version data: " + ", ".join(missing))
    elif macos != sfr:
        reasons.append(
            f"macOS/main firmware mismatch: macOS={macos}, main firmware={sfr}"
        )

    if not sros or sros == "0":
        reasons.append("SystemRecovery version is unavailable")

    boot_mode = info.get("boot_mode")
    if boot_mode not in ("macOS", "Unknown", None):
        reasons.append(f"boot mode is {boot_mode!r}, not normal macOS")

    boot_vgid = info.get("boot_vgid")
    default_vgid = info.get("default_boot_vgid")
    if not boot_vgid or not default_vgid:
        reasons.append("boot/default volume-group ID is unavailable")
    elif boot_vgid != default_vgid:
        reasons.append(
            f"default boot VGID {default_vgid} differs from booted macOS VGID {boot_vgid}"
        )

    return not reasons, reasons


def evaluate_warnings(info: dict) -> list[str]:
    warnings = []

    macos = info.get("macos_version")
    sfr = info.get("sfr_version")
    sros = info.get("system_recovery_version")
    if macos and sfr and sros and len({macos, sfr, sros}) != 1:
        warnings.append(
            "SystemRecovery version differs from the booted macOS/main firmware: "
            f"macOS={macos}, main firmware={sfr}, SystemRecovery={sros}"
        )

    if info.get("boot_mode") in ("Unknown", None):
        warnings.append(
            "bputil boot mode could not be classified by the packaged Asahi parser; "
            "matching boot/default VGIDs are used as the safety gate instead"
        )

    return warnings


def collect() -> dict:
    # system.py is supplied by the unpacked Asahi installer release.
    from system import SystemInfo

    sysinfo = SystemInfo()
    return {
        "product_name": sysinfo.product_name,
        "soc_name": sysinfo.soc_name,
        "device_class": sysinfo.device_class,
        "product_type": sysinfo.product_type,
        "board_id": f"0x{sysinfo.board_id:x}",
        "chip_id": f"0x{sysinfo.chip_id:x}",
        "system_firmware": sysinfo.sys_firmware,
        "boot_mode": sysinfo.boot_mode,
        "boot_vgid": sysinfo.boot_vgid,
        "default_boot_vgid": sysinfo.default_boot,
        "macos_version": sysinfo.macos_ver,
        "macos_build": sysinfo.macos_build,
        "macos_restore_version": sysinfo.macos_restore_ver,
        "sfr_version": sysinfo.sfr_ver,
        "sfr_build": sysinfo.sfr_build,
        "sfr_restore_version": sysinfo.sfr_full_ver,
        "system_recovery_version": sysinfo.sros_ver,
        "system_recovery_build": sysinfo.sros_build,
        "system_recovery_restore_version": sysinfo.sros_full_ver,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = collect()
        ready, reasons = evaluate_alignment(result)
        warnings = evaluate_warnings(result)
        result["ready_for_boot_policy"] = ready
        result["blocking_reasons"] = reasons
        result["warnings"] = warnings

        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("J614s host boot/recovery preflight")
            print("=================================")
            print(
                f"Machine:              {result['product_type']} / "
                f"{result['device_class']} / {result['chip_id']}"
            )
            print(
                f"macOS:                {result['macos_version']} "
                f"({result['macos_build']})"
            )
            print(
                f"Main firmware (SFR):  {result['sfr_version']} "
                f"({result['sfr_build']})"
            )
            print(
                f"SystemRecovery:       {result['system_recovery_version']} "
                f"({result['system_recovery_build']})"
            )
            print(
                "RestoreLongVersion:   "
                f"OS={result['macos_restore_version']}, "
                f"SFR={result['sfr_restore_version']}, "
                f"Recovery={result['system_recovery_restore_version']}"
            )
            print(f"Boot mode:            {result['boot_mode']}")
            print(f"Boot VGID:            {result['boot_vgid']}")
            print(f"Default boot VGID:    {result['default_boot_vgid']}")
            print(
                "Boot-policy preflight: "
                + ("PASS" if ready else "BLOCKED")
            )
            for reason in reasons:
                print(f"  BLOCKER: {reason}")
            for warning in warnings:
                print(f"  WARNING: {warning}")

        return 0 if ready else 2
    except Exception as exc:
        print(f"HOST PROBE FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
