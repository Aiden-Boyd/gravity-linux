#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static source qualification gate for J614s bring-up images.

This gate runs before artifact compilation. It validates immutable source
identity, syntax/provenance markers, profile isolation, and fail-closed
hardware assumptions. It does not claim runtime hardware correctness.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys


def die(msg: str) -> None:
    raise SystemExit(f"source qualification FAILED: {msg}")


def text(path: pathlib.Path) -> str:
    if not path.is_file():
        die(f"missing required source file: {path}")
    return path.read_text(errors="replace")


def run(*cmd: str, cwd: pathlib.Path) -> str:
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if p.returncode:
        sys.stderr.write(p.stdout)
        sys.stderr.write(p.stderr)
        die("command failed: " + " ".join(cmd))
    return p.stdout.strip()


def assert_contains(blob: str, needle: str, why: str) -> None:
    if needle not in blob:
        die(why)


def assert_not_contains(blob: str, needle: str, why: str) -> None:
    if needle in blob:
        die(why)


def load_profile(manifest: pathlib.Path, profile_id: str) -> dict:
    data = json.loads(manifest.read_text())
    for profile in data["profiles"]:
        if profile["id"] == profile_id:
            return profile
    die(f"profile {profile_id!r} not found in manifest")


def global_checks(root: pathlib.Path, profile: dict) -> None:
    expected = profile.get("source_commit")
    if not expected or not re.fullmatch(r"[0-9a-f]{40}", expected):
        die("buildable profile is missing a full immutable 40-hex source_commit")

    actual = run("git", "rev-parse", "HEAD", cwd=root)
    if actual != expected:
        die(f"source SHA mismatch: manifest={expected} checkout={actual}")

    status = run("git", "status", "--porcelain", cwd=root)
    if status:
        die("candidate checkout is not clean")

    # Reject unresolved merge/conflict debris in source files.
    for rel in (
        "tools/j614s/ramboot-config.sh",
        "tools/j614s/ramboot-diag.sh",
        "tools/j614s/m1n1/patch-v1.9.9-j614s.py",
        "arch/arm64/boot/dts/apple/t6040.dtsi",
        "arch/arm64/boot/dts/apple/t6040-j614s.dts",
        "arch/arm64/boot/dts/apple/t6040-j614s-all.dts",
    ):
        blob = text(root / rel)
        if re.search(r"^(<<<<<<<|=======|>>>>>>>)", blob, re.M):
            die(f"merge conflict marker found in {rel}")

    # Syntax-only checks: no kernel/image compilation happens in this gate.
    for rel in (
        "tools/j614s/ramboot-config.sh",
        "tools/j614s/ramboot-diag.sh",
        "tools/j614s/tethered-boot.sh",
        "tools/j614s/installer/bootstrap.sh",
    ):
        run("sh", "-n", rel, cwd=root)

    run("python3", "-m", "py_compile",
        "tools/j614s/m1n1/patch-v1.9.9-j614s.py",
        cwd=root)

    mk = text(root / "Makefile")
    for key in ("VERSION = 7", "PATCHLEVEL = 1"):
        assert_contains(mk, key, f"unexpected kernel base; missing {key}")

    dts = text(root / "arch/arm64/boot/dts/apple/t6040.dtsi")
    assert_contains(dts, 'compatible = "apple,t6040-aic3"', "T6040 AICv3 source marker missing")
    assert_contains(dts, "cpu_p05_disabled: cpu@10105", "fused/positional CPU slot missing")

    patch = text(root / "tools/j614s/m1n1/patch-v1.9.9-j614s.py")
    for marker in ("broken_wfi = true", "wfe_mode = true", "refusing to disable WFE mode"):
        assert_contains(patch, marker, f"required M4 stage1 safety marker missing: {marker}")

    # The RAM boot userspace may mount only virtual/pseudo filesystems
    # automatically. Persistent block devices stay untouched until a human
    # explicitly chooses a subsystem test.
    shell_init = text(root / "tools/j614s/ramboot-shell-init.sh")
    shell_mounts = re.findall(r"(?m)^mount\\s+-t\\s+([A-Za-z0-9_-]+)", shell_init)
    allowed_mounts = {"proc", "sysfs", "devtmpfs", "tmpfs"}
    if set(shell_mounts) - allowed_mounts:
        die(f"shell init auto-mounts unexpected filesystem types: {shell_mounts}")
    for marker in ("/dev/nvme", "/dev/mmcblk", "/dev/sd"):
        assert_not_contains(shell_init, marker,
                            f"shell init references persistent block path {marker}")

    safe_init = text(root / "tools/j614s/ramboot-init.c")
    c_mount_lines = [
        line.strip() for line in safe_init.splitlines()
        if line.lstrip().startswith("mount(")
    ]
    allowed_c_mounts = (
        'mount("proc", "/proc", "proc",',
        'mount("sysfs", "/sys", "sysfs",',
        'mount("devtmpfs", "/dev", "devtmpfs",',
    )
    for line in c_mount_lines:
        if not line.startswith(allowed_c_mounts):
            die(f"safe init contains unexpected automatic mount: {line}")
    for marker in ("/dev/nvme", "/dev/mmcblk", "/dev/sd"):
        assert_not_contains(safe_init, marker,
                            f"safe init references persistent block path {marker}")


def check_minimal_config_source(root: pathlib.Path) -> str:
    cfg = text(root / "tools/j614s/ramboot-config.sh")
    for sym in (
        "CONFIG_NVME_APPLE", "CONFIG_BLK_DEV_NVME", "CONFIG_PCIE_APPLE",
        "CONFIG_APPLE_DART", "CONFIG_MFD_MACSMC", "CONFIG_APPLE_DOCKCHANNEL",
        "CONFIG_HID_DOCKCHANNEL", "CONFIG_BRCMFMAC", "CONFIG_WLAN",
        "CONFIG_BT", "CONFIG_MMC", "CONFIG_USB",
    ):
        assert_contains(cfg, f"disable {sym}", f"minimal profile does not disable {sym}")
    return cfg


def profile_checks(root: pathlib.Path, profile: dict) -> None:
    gate = profile["source_gate"]
    cfg = text(root / "tools/j614s/ramboot-config.sh")
    all_dts = text(root / "arch/arm64/boot/dts/apple/t6040-j614s-all.dts")
    thin_dts = text(root / "arch/arm64/boot/dts/apple/t6040-j614s.dts")

    if gate == "safe":
        check_minimal_config_source(root)
        assert_contains(cfg, "safe)", "SAFE case missing from ramboot config")
        assert_contains(thin_dts, "status = \"disabled\"", "thin DT no longer contains disabled-device guards")

    elif gate == "diagnostic":
        for marker in (
            "module CONFIG_APPLE_DART",
            "module CONFIG_PCIE_APPLE",
            "module CONFIG_MFD_MACSMC",
            "module CONFIG_BRCMFMAC",
            "module CONFIG_BT_HCIBCM4377",
            "module CONFIG_MMC_SDHCI_PCI",
        ):
            assert_contains(cfg, marker, f"diagnostic source missing {marker}")
        for marker in (
            'pwren-gpios = <&smc_gpio 0x13 GPIO_ACTIVE_HIGH>',
            'pwren-gpios = <&smc_gpio 0x19 GPIO_ACTIVE_HIGH>',
            'compatible = "pci14e4,4434"',
            'compatible = "pci17a0,9755"',
        ):
            assert_contains(all_dts, marker, f"diagnostic DT missing reviewed marker: {marker}")

    elif gate == "yolo":
        for marker in (
            "enable CONFIG_APPLE_DART",
            "enable CONFIG_PCIE_APPLE",
            "enable CONFIG_MFD_MACSMC",
            "enable CONFIG_BRCMFMAC",
            "enable CONFIG_BT_HCIBCM4377",
            "enable CONFIG_MMC_SDHCI_PCI",
        ):
            assert_contains(cfg, marker, f"YOLO source missing {marker}")

    elif gate == "smp-thin":
        check_minimal_config_source(root)
        assert_contains(cfg, "safe|smp-thin)", "SMP-thin is not tied to the minimal profile")
        assert_contains(cfg, "enable CONFIG_SMP", "SMP-thin source does not explicitly enable SMP")
        audit = text(root / "tools/j614s/smp-audit.sh")
        assert_contains(audit, "maxcpus=14", "SMP audit no longer enforces 14-CPU candidate")
        run("sh", "tools/j614s/smp-audit.sh", cwd=root)
        wf = text(root / ".github/workflows/j614s-smp-thin.yml")
        for marker in ("maxcpus=14", "idle=nop", "arm64.nowfxt"):
            assert_contains(wf, marker, f"SMP workflow lost required boot argument {marker}")
        assert_not_contains(wf,
            'cp arch/arm64/boot/dts/apple/t6040-j614s-all.dtb "$OUT/t6040-j614s.dtb"',
            "SMP-thin packages the all-hardware DT")

    else:
        die(f"source gate {gate!r} is not admitted for building")

    # No admitted image may silently grow native T6040 GPU or internal NVMe
    # nodes while those contracts remain gated.
    joined = text(root / "arch/arm64/boot/dts/apple/t6040.dtsi") + "\n" + all_dts
    if "apple,agx-t6040" in joined or "gpu,t6040" in joined:
        die("unadmitted native T6040 GPU node found in build source")
    if "apple,t6040-nvme-ans2" in joined:
        die("unadmitted native T6040 NVMe node found in build source")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=pathlib.Path, required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--source", type=pathlib.Path, required=True)
    args = ap.parse_args()

    profile = load_profile(args.manifest, args.profile)
    if not profile.get("build_enabled"):
        die(f"profile {args.profile} is blocked and must not build")

    root = args.source.resolve()
    global_checks(root, profile)
    profile_checks(root, profile)

    print(f"SOURCE_QUALIFIED {args.profile} {profile['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
