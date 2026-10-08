#!/usr/bin/env python3
"""Read-only J614s iBoot alignment-panic call-path report.

Requires Capstone 5; uses raw iBoot 15.1 decompressed binary.
Does not patch binaries, boot policy, or APFS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

BASE = 0x10081AA4000
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
    if len(data) <= max(EXPECTED_CALLERS) + 4:
        raise ValueError("Input too short for known iBoot 15.1 offsets")
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
    dis = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    sections = {}
    for name, start, end in [
        ("higher_level_callers_A", 0x37290, 0x37334),
        ("higher_level_callers_B", 0x39360, 0x39400),
        ("helper_A", 0x3D548, 0x3D56C),
        ("helper_B", 0x3D57C, 0x3D59C),
        ("translator", 0x3B61C, 0x3B660),
        ("allocation_and_alignment",0x3B780,0x3B7B4),
        ("panic_site",0x3B838,0x3B848)
    ]:
        sections[name] = [f"{i.address-BASE:06x}: {i.mnemonic} {i.op_str}" for i in dis.disasm(data[start:end], BASE+start)]
    return {"sha256":hashlib.sha256(data).hexdigest(),
            "bytes":len(data),"linked_base":hex(BASE),
            "expected_callers":matches,"references":calls,"disassembly":sections,
            "equation":"translated = allocated_address - descriptor[+8] + descriptor[+16]",
            "alignment_condition":"translated & 0xFFF == 0",
            "interpretation":"The 981 panic checks translation alignment. No concrete mapping values or root-cause fix are derivable from static code alone.",
            "safe_next_test":"Correlate runtime mapping values or known-good FUOS install behaviour; do not bypass assertion or pad signed IMG4 based only on sizes."}

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
