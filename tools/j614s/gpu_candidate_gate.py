#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail-closed admission gate for a future J614s/T6040 G16 GPU stack.

This does not prove a candidate is safe. It rejects candidates that do not
contain the minimum explicit T6040/G16 identifiers needed before a reviewed
live test can even be considered.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, asdict


TEXT_SUFFIXES = {
    ".c", ".h", ".rs", ".dts", ".dtsi", ".yaml", ".yml", ".toml",
    ".json", ".md", ".txt", ".py",
}


@dataclass
class Check:
    surface: str
    name: str
    passed: bool
    detail: str


def read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def tree_text(root: pathlib.Path, subdir: str | None = None) -> str:
    base = root / subdir if subdir else root
    if not base.exists():
        return ""
    chunks: list[str] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        # Source checks only need text/configuration. Avoid accidentally
        # ingesting giant generated files in a candidate checkout.
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
        except OSError:
            continue
        chunks.append(read_text(path))
    return "\n".join(chunks)


def function_body(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        return ""
    brace = text.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def check_m1n1(root: pathlib.Path) -> list[Check]:
    kboot = read_text(root / "src/kboot_gpu.c")
    body = function_body(kboot, "int dt_set_gpu")
    gpu_text = tree_text(root, "rust/src/gpu") + "\n" + kboot

    explicit_soc = bool(re.search(r"\bcase\s+T6040\s*:", body))
    explicit_gen = bool(
        re.search(r"\bG16\b", gpu_text)
        or re.search(r"GpuGen\s*::\s*G16", gpu_text)
        or re.search(r"\bG16\s*=\s*16\b", gpu_text)
    )

    return [
        Check(
            "m1n1",
            "dt_set_gpu explicitly handles T6040",
            explicit_soc,
            "T6040 case found in dt_set_gpu()" if explicit_soc
            else "No T6040 case in dt_set_gpu(); current loader handoff cannot be admitted.",
        ),
        Check(
            "m1n1",
            "GPU hardware model explicitly names G16",
            explicit_gen,
            "Explicit G16 generation marker found." if explicit_gen
            else "No explicit G16 generation/configuration marker found.",
        ),
    ]


def check_linux(root: pathlib.Path) -> list[Check]:
    drm = tree_text(root, "drivers/gpu/drm/asahi")
    dt = tree_text(root, "arch/arm64/boot/dts/apple")
    all_text = drm + "\n" + dt

    compat = "apple,agx-t6040" in drm
    gen = bool(
        re.search(r"\bG16\b", drm)
        or re.search(r"GpuGen\s*::\s*G16", drm)
        or re.search(r"\bAGX2\b", drm)
    )

    alias_bad = False
    if compat:
        for match in re.finditer(re.escape("apple,agx-t6040"), drm):
            nearby = drm[match.start() : match.start() + 600]
            if re.search(r"(?:t602x::HWCONFIG|HWCONFIG_T602[012]|GpuGen\s*::\s*G14)", nearby):
                alias_bad = True
                break

    return [
        Check(
            "linux",
            "explicit apple,agx-t6040 compatible",
            compat,
            "Explicit T6040 OF compatible found." if compat
            else "No apple,agx-t6040 compatible found in DRM/Apple DT sources.",
        ),
        Check(
            "linux",
            "explicit G16/AGX2 hardware path",
            gen,
            "Explicit G16/AGX2 marker found." if gen
            else "No explicit G16/AGX2 hardware path found.",
        ),
        Check(
            "linux",
            "T6040 is not a nearby T602x/G14 alias",
            compat and not alias_bad,
            "No nearby G14/T602x alias detected." if compat and not alias_bad
            else (
                "T6040 compatible appears to reuse a T602x/G14 configuration."
                if alias_bad else "Cannot evaluate aliasing without a T6040 compatible."
            ),
        ),
    ]


def check_mesa(root: pathlib.Path) -> list[Check]:
    asahi = tree_text(root, "src/asahi")
    explicit = bool(
        re.search(r"\bG16\b", asahi)
        or re.search(r"AGX_CHIP_G16", asahi)
        or re.search(r"\bAGX2\b", asahi)
    )
    return [
        Check(
            "mesa",
            "explicit G16/AGX2 userspace path",
            explicit,
            "Explicit G16/AGX2 marker found in src/asahi." if explicit
            else "No explicit G16/AGX2 userspace marker found in src/asahi.",
        )
    ]


def check_contract(path: pathlib.Path | None) -> list[Check]:
    if path is None:
        return [
            Check(
                "contract",
                "candidate test contract supplied",
                False,
                "No --contract JSON supplied.",
            )
        ]

    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return [Check("contract", "candidate test contract supplied", False, f"Invalid JSON: {exc}")]

    required = (
        "dt_compatible",
        "firmware_abi_or_build",
        "first_test_scope",
        "crash_recovery",
        "m1n1_commit",
        "linux_commit",
        "mesa_commit",
    )
    missing = [
        key for key in required
        if not data.get(key)
        or (isinstance(data.get(key), str) and data.get(key).startswith("REPLACE_"))
    ]
    return [
        Check(
            "contract",
            "candidate test contract supplied",
            not missing,
            "Required contract fields are present."
            if not missing else "Missing fields: " + ", ".join(missing),
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m1n1", type=pathlib.Path, required=True)
    parser.add_argument("--linux", type=pathlib.Path, required=True)
    parser.add_argument("--mesa", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()

    checks = (
        check_m1n1(args.m1n1)
        + check_linux(args.linux)
        + check_mesa(args.mesa)
        + check_contract(args.contract)
    )
    passed = all(check.passed for check in checks)

    if args.json:
        print(json.dumps({"ready_for_review": passed, "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        for check in checks:
            mark = "PASS" if check.passed else "FAIL"
            print(f"[{mark}] {check.surface}: {check.name}")
            print(f"       {check.detail}")
        print()
        print(
            "ADMISSION RESULT: READY FOR HUMAN REVIEW"
            if passed else
            "ADMISSION RESULT: REJECTED (no live GPU test)"
        )

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
