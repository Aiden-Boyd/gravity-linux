#!/usr/bin/env python3
"""Read-only estimate of iBoot 11881 mode-1 cursor residues from Image4 PAYP.

This prints a CONDITIONAL intermediate calculation only. It cannot establish
that the actual failure used this path, or that the subsequent address
translation did not cancel the residue. It does not change boot files.
"""
import argparse
import re
from pathlib import Path

PROPERTY = re.compile(rb"\x16\x04(kc[a-z]{2})\x02")


def extract_properties(image: bytes) -> dict[str, int]:
    tail = image[max(0, len(image) - 65536):]
    found: dict[str, int] = {}
    for m in PROPERTY.finditer(tail):
        tag = m.group(1).decode("ascii")
        pos = m.end()
        if pos >= len(tail):
            raise ValueError(f"truncated DER property {tag}")
        length = tail[pos]
        pos += 1
        if length & 0x80:
            n = length & 0x7f
            if not 1 <= n <= 2 or pos + n > len(tail):
                raise ValueError(f"invalid DER length for {tag}")
            length = int.from_bytes(tail[pos:pos + n], "big")
            pos += n
        if not 1 <= length <= 9 or pos + length > len(tail):
            raise ValueError(f"bad DER integer for {tag}")
        value = int.from_bytes(tail[pos:pos + length], "big", signed=True)
        if value < 0 or value > (1 << 64) - 1:
            raise ValueError(f"out-of-range unsigned 64-bit integer {tag}")
        if tag in found and found[tag] != value:
            raise ValueError(f"conflicting property {tag}")
        found[tag] = value
    return found


def mode1_cursor_residue(props: dict[str, int]) -> int:
    required = ("kclo", "kclz", "kcwz")
    if any(k not in props for k in required):
        raise ValueError("missing kclo/kclz/kcwz; cannot model cursor")
    accumulated = sum(props.get(k, 0) for k in ("kcbz", "kcxz", "kcrz", "kcsz"))
    return (props["kclo"] + props["kclz"] + props["kcwz"] + accumulated) & 0xfff


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    args = ap.parse_args()
    data = args.image.read_bytes()
    if b"IMG4" not in data[:32] or b"IM4P" not in data[:48]:
        ap.error("input is not an apparent Image4")
    image_type = "fuos" if b"fuos" in data[:48] else ("krnl" if b"krnl" in data[:48] else "unknown")
    if image_type == "unknown":
        ap.error("input is neither fuOS nor krnl Image4")
    props = extract_properties(data)
    if not props:
        ap.error("no kcXX Image4 properties located")
    print(f"Image type: {image_type} — PAYP integers (not live register values):")
    for k, v in sorted(props.items()):
        print(f"  {k}: 0x{v:x} ({v:,})")
    print(f"\nConditional iBoot 11881 mode-1 cursor residue: "
          f"0x{mode1_cursor_residue(props):03x}")
    print("All contributions were extracted from the image, not runtime RAM.")
    print("The later mapping source/destination adjustment is UNKNOWN.")
    print("This output does NOT prove the cause of the iBoot panic.")
    print("Do NOT remove terminators, modify boot policy, or reboot on this basis.")


if __name__ == "__main__":
    main()
