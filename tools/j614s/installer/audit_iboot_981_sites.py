#!/usr/bin/env python3
"""Read-only source-hash disambiguation of J614s iBoot 15.1 :981 panic sites.

Runs only on the exact previously analyzed decompressed iBoot SHA-256.
Does not modify firmware, boot policy, or hardware. Python standard library only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

EXPECTED_SHA256 = "bd452a87420a03db8373c514a93014fdaa32019a43f1e830279ce2ea0c855e3b"
EXPECTED_BYTES = 3750816
EXPECTED_SITES = {0x3B83C, 0x10C7B4, 0x15596C}
MOV_W1_981 = 0x52807AA1
EXPECTED_PANIC_ID = 0x03BDACE14B1A9A68


def word(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def branch_target(offset: int, opcode: int) -> int | None:
    if opcode & 0xFC000000 not in (0x14000000, 0x94000000):
        return None
    imm = opcode & 0x03FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return offset + (imm << 2)


def constant_x0(data: bytes, offset: int) -> int:
    """Decode a MOVZ/MOVK x0 constant helper with direct RET."""
    value = 0
    for i in range(4):
        opcode = word(data, offset + 4 * i)
        kind = opcode & 0xFF800000
        if opcode & 0x1F:
            raise ValueError("source helper writes a register other than x0")
        imm = (opcode >> 5) & 0xFFFF
        shift = ((opcode >> 21) & 3) * 16
        if (i == 0 and kind != 0xD2800000) or (i > 0 and kind != 0xF2800000):
            raise ValueError("unrecognized source hash helper")
        if i == 0:
            value = imm << shift
        else:
            value = (value & ~(0xFFFF << shift)) | (imm << shift)
    if word(data, offset + 16) != 0xD65F03C0:
        raise ValueError("source hash helper does not end with RET")
    return value


def inspect(data: bytes) -> dict:
    if len(data) != EXPECTED_BYTES or hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise ValueError("iBoot hash/size mismatch: refusing source inference")
    sites = []
    for offset in range(4, len(data) - 7, 4):
        if word(data, offset) != MOV_W1_981:
            continue
        source = branch_target(offset - 4, word(data, offset - 4))
        reporter = branch_target(offset + 4, word(data, offset + 4))
        if source is None or reporter is None:
            raise ValueError("unrecognized line-981 call sequence")
        identifier = constant_x0(data, source)
        sites.append({
            "offset": hex(offset),
            "source_helper": hex(source),
            "source_identifier": f"{identifier:016x}",
            "reporter": hex(reporter),
            "matches_recorded_panic": identifier == EXPECTED_PANIC_ID,
        })
    if {int(s["offset"], 16) for s in sites} != EXPECTED_SITES:
        raise ValueError("unexpected line-981 sites")
    if len({s["reporter"] for s in sites}) != 1:
        raise ValueError("expected shared panic reporter")
    matches = [s for s in sites if s["matches_recorded_panic"]]
    if len(matches) != 1 or matches[0]["offset"] != "0x3b83c":
        raise ValueError("unexpected panic source match")
    return {
        "source_sha256": EXPECTED_SHA256,
        "panic": "3bdace14b1a9a68:981",
        "sites": sites,
        "selected_path": "translated-address alignment branch at 0x3b7a8",
        "proven": "The panic identifier and line select 0x3b83c among three sites",
        "not_proven": [
            "reason the mapped address was misaligned",
            "allocator return or descriptor runtime values",
            "whether a different OS-paired firmware version would work",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iboot", type=Path)
    parser.add_argument("--output", type=Path, default=Path("j614s-iboot-981-sources.json"))
    args = parser.parse_args()
    result = inspect(args.iboot.read_bytes())
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for site in result["sites"]:
        print(site["offset"], site["source_identifier"], "MATCH" if site["matches_recorded_panic"] else "other")
    print("Wrote", args.output)


if __name__ == "__main__":
    main()
