#!/usr/bin/env python3
"""Read-only J614s iBoot alignment-panic call-path report.

Python standard library only; requires exact known-hash iBoot 15.1 decompressed binary.
Does not patch binaries, boot policy, or APFS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path


BASE = 0x10081AA4000
KNOWN_SIZE = 3750816
KNOWN_SHA256 = "bd452a87420a03db8373c514a93014fdaa32019a43f1e830279ce2ea0c855e3b"
# Exact opcode fingerprints at the source/translator/check/panic path.
# These are never patched. Values were independently verified from uploaded iBoot 15.1.
OPCODES = {
    0x39AC4: (0x5287FFE9, "mov w9, #0x3fff"),
    0x39ACC: (0x9272C520, "and x0, x9, #...c000"),
    0x3B634: (0xF9400428, "ldr x8, [x1, #8] (source base)"),
    0x3B63C: (0xF9400829, "ldr x9, [x1, #16] (target base)"),
    0x3B640: (0xCB080008, "sub x8, x0, x8"),
    0x3B644: (0x8B090100, "add x0, x8, x9"),
    0x3B780: (0xF9401018, "ldr x24, [x0, #32] (requested size)"),
    0x3B784: (0x5287FFE8, "mov w8, #0x3fff"),
    0x3B788: (0x8B080308, "add x8, x24, x8"),
    0x3B78C: (0x9272C517, "and x23, x8, #...c000"),
    0x3B790: (0xAA1703E0, "mov x0, x23"),
    0x3B798: (0xAA1C03E1, "mov x1, x28"),
    0x3B79C: (0xAA1B03E2, "mov x2, x27"),
    0x3B7A0: (0xAA1903E3, "mov x3, x25"),
    0x3B7A8: (0xF2402C1F, "tst x0, #0xfff"),
    0x3B7AC: (0x54000461, "b.ne 0x3b838"),
    0x3B83C: (0x52807AA1, "mov w1, #981"),
}
LABELS = {0x2841F4: "SEPPatches", 0x2841FF: "uStuff"}

ENTRY = 0x3B72C
ALIGN_CHECK = 0x3B7A8
PANIC_LINE = 0x3B83C
HELPERS = {0x3D548: "mapping-from-x21", 0x3D57C: "mapping-from-x19"}
EXPECTED_CALLERS = {0x39390:0x3D548, 0x393EC:0x3D548,
                    0x372BC:0x3D57C, 0x37314:0x3D57C}

def branch_target(offset, word):
    opcode = word & 0xFC000000
    if opcode not in (0x14000000, 0x94000000):
        return None
    imm = word & 0x03FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return offset + (imm << 2)

def analyze(data):
    if len(data) != KNOWN_SIZE or hashlib.sha256(data).hexdigest() != KNOWN_SHA256:
        raise ValueError("Unknown iBoot build; refusing version-specific panic inference")
    if int.from_bytes(data[0x300:0x308], "little") != BASE:
        raise ValueError("Image base mismatch; refusing to apply known-version offsets")
    calls = []
    for off in range(0, len(data) - 3, 4):
        word = struct.unpack_from("<I", data, off)[0]
        dst = branch_target(off, word)
        if dst in (*HELPERS, ENTRY):
            calls.append({"from":hex(off),"to":hex(dst),
                          "kind":"BL" if (word & 0xFC000000)==0x94000000 else "B"})
    matches = []
    for source, destination in EXPECTED_CALLERS.items():
        actual = branch_target(source, struct.unpack_from("<I",data,source)[0])
        matches.append({"offset":hex(source),"target":hex(destination),"matches":actual==destination})
    # Validate every opcode before interpreting the path; no Capstone requirement.
    validated = []
    for off, (expected, meaning) in OPCODES.items():
        got = struct.unpack_from("<I", data, off)[0]
        if got != expected:
            raise ValueError(f"Unexpected instruction at {off:#x}: {got:#x}")
        validated.append({"offset": hex(off), "opcode": hex(got), "meaning": meaning})
    labels = {}
    for off, name in LABELS.items():
        if data[off:off+len(name)+1] != name.encode() + b"\\0":
            raise ValueError(f"Caller label {name!r} not present at {off:#x}")
        labels[hex(off)] = name
    if (struct.unpack_from("<I",data,0x3B7AC)[0] >> 5 & 0x7ffff) * 4 + 0x3B7AC != 0x3B838:
        raise ValueError("Misalignment branch does not lead to known panic block")
    sections = {"instruction_checks":validated, "caller_labels":labels}
    return {"sha256":hashlib.sha256(data).hexdigest(),
            "bytes":len(data),"linked_base":hex(BASE),
            "expected_callers":matches,"references":calls,"disassembly":sections,"opcode_checks":validated,"caller_labels":labels,
            "equation":"translated = allocator_return - descriptor[+8] + descriptor[+16]",
            "allocation_size":"align_up(descriptor[+0x20], 0x4000)",
            "static_callers_warning":"SEPPatches and uStuff are caller labels, not proof which branch executed",
            "needed_runtime_values":["allocator return address","descriptor[+8]","descriptor[+16]"],
            "alignment_condition":"translated & 0xFFF == 0",
            "interpretation":"Candidate :981 path checks whether an allocated address translated between descriptor bases is 4096-aligned. We do not know which caller ran or its runtime operands.",
            "safe_next_test":"Correlate runtime bases/allocator return with an authorized firmware trace; do not change signed IMG4/iBoot or bypass assertion based on static code."}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iboot",type=Path)
    ap.add_argument("--output",type=Path,default=Path("j614s-alignment-trace.json"))
    a=ap.parse_args()
    result=analyze(a.iboot.read_bytes())
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print("Verified callers:",sum(x["matches"] for x in result["expected_callers"]),
          "/",len(result["expected_callers"]))
    for call in result["expected_callers"]:
        print(call["offset"],"->",call["target"],"OK" if call["matches"] else "MISMATCH")
    print(result["equation"])
    print(result["alignment_condition"])
    print("Report:",a.output)

if __name__=="__main__":
    main()
