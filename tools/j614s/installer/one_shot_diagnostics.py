#!/usr/bin/env python3
"""J614s read-only one-shot boot evidence report (no firmware or APFS writes)."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

KNOWN_BASE = 0x10081AA4000
KNOWN_IBOOT_PANIC_OFF = 0x3B83C
KNOWN_TRANSLATION_OFF = 0x3B61C
KNOWN_CHECK_OFF = 0x3B7A8
PANIC_RE = re.compile(rb"iBoot Panic:\s*:\s*([0-9a-f]+:\d+)")
BUILD_RE = re.compile(rb"Build:\s*(RELEASE:iBoot-[0-9.]+)")
ADDRESS_RE = re.compile(rb"@0x([0-9a-fA-F]{10,16})")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def file_info(path):
    data = path.read_bytes()
    return {"file": str(path), "bytes": len(data), "sha256": sha(data),
            "mod_4096": len(data) % 4096, "mod_16384": len(data) % 16384}

def fuos_info(path, m1n1=None):
    data = path.read_bytes()
    result = file_info(path)
    result["markers"] = {x.decode(): data.find(x) for x in (b"IMG4", b"IM4P", b"fuos")}
    # Require the exact known header prefix and DER 0x83 long-form OCTET length.
    # Do not pretend this is a general ASN.1 parser.
    prefix = bytes.fromhex("30 83")
    marker = b"\x04\x83"
    pos = data.find(marker, 0, 128)
    if not data.startswith(prefix) or pos < 0 or pos + 5 > len(data):
        result["payload_error"] = "Known FUOS DER layout not recognized"
        return result
    size = int.from_bytes(data[pos+2:pos+5], "big")
    start = pos + 5
    if not (data.find(b"fuos", 0, start) >= 0 and 0 < size <= len(data) - start):
        result["payload_error"] = "Unexpected FUOS payload size/header"
        return result
    payload = data[start:start+size]
    result["payload"] = {"offset": start, "bytes": size, "sha256": sha(payload),
                         "mod_4096": size % 4096, "mod_16384": size % 16384,
                         "trailing_4_hex": payload[-4:].hex()}
    if m1n1 is not None:
        source = m1n1.read_bytes()
        result["payload"]["matches_m1n1_plus_four_nuls"] = payload == source + bytes(4)
        result["m1n1"] = file_info(m1n1)
    return result

def panic_info(path):
    with path.open("r", encoding="utf-8", errors="replace") as f:
        header = json.loads(f.readline())
        report = json.load(f)
    result = {"file": str(path), "timestamp": header.get("timestamp"),
              "product": report.get("product"), "socId": report.get("socId"),
              "build": report.get("build"), "panicString": report.get("panicString"),
              "notes": report.get("notes"), "containers": []}
    for c in report.get("SOCDContainers", []):
        raw = base64.b64decode(c["SOCDContainer"], validate=True)
        # Strings can appear repeatedly. Report distinct signatures.
        sigs = sorted(set(s.decode("ascii") for s in PANIC_RE.findall(raw)))
        builds = sorted(set(s.decode("ascii") for s in BUILD_RE.findall(raw)))
        addrs = sorted(set(int(s,16) for s in ADDRESS_RE.findall(raw)))
        result["containers"].append({"bytes": len(raw), "socd_magic": raw[:4] == b"SOCD",
                                     "panic_signatures": sigs, "iboot_builds": builds,
                                     "printed_addresses": [hex(a) for a in addrs]})
    return result

def iboot_info(path):
    data = path.read_bytes()
    out = file_info(path)
    out["first_instruction_hex"] = data[:4].hex()
    out["linked_base_literal"] = hex(int.from_bytes(data[0x300:0x308], "little")) if len(data) >= 0x308 else None
    out["static_evidence"] = {"panic_line_candidate_offset": hex(KNOWN_IBOOT_PANIC_OFF),
                              "translation_helper_offset": hex(KNOWN_TRANSLATION_OFF),
                              "alignment_test_offset": hex(KNOWN_CHECK_OFF)}
    out["warning"] = "Static offsets from 15.1 reverse engineering; not proof of runtime state."
    return out

def build_report(fuos=None, m1n1=None, iboot=None, panics=()):
    report = {"device": "Mac16,8 / J614s / T6040", "mode": "read_only",
              "fuos": None, "iboot": None, "panics": [], "findings": [], "next_action": ""}
    if fuos:
        report["fuos"] = fuos_info(fuos, m1n1)
        p = report["fuos"].get("payload", {})
        if p.get("matches_m1n1_plus_four_nuls") is True:
            report["findings"].append("Installed FUOS payload matches selected m1n1 plus four zero bytes.")
        elif "matches_m1n1_plus_four_nuls" in p:
            report["findings"].append("WARNING: installed FUOS payload differs from selected m1n1+4.")
    if iboot:
        report["iboot"] = iboot_info(iboot)
        if report["iboot"]["linked_base_literal"] == hex(KNOWN_BASE):
            report["findings"].append("iBoot relocation literal matches analyzed 15.1 image base.")
        else:
            report["findings"].append("WARNING: iBoot linked-base literal differs from analyzed binary.")
    for p in panics:
        report["panics"].append(panic_info(p))
    signatures = sorted({s for p in report["panics"] for c in p["containers"] for s in c["panic_signatures"]})
    report["findings"].append("Distinct iBoot panic signatures: " + (", ".join(signatures) or "none decoded"))
    if "3bdace14b1a9a68:981" in signatures:
        report["findings"].append("Line 981 matches the observed 4 KiB alignment-check failure path; runtime mapping values remain unknown.")
    report["findings"].append("Image file-length alignment alone does not establish an iBoot mapping fault.")
    report["next_action"] = ("Compare boot artifact creation/boot policy and capture mapping inputs from a controlled test; "
                             "do not modify signed IMG4 or bypass the alignment check based only on this static report.")
    return report

def markdown(report):
    lines = ["# Gravity Linux J614s one-shot diagnostics", "",
             "**Mode:** read-only", "", "## Findings", ""]
    lines += ["- " + s for s in report["findings"]]
    lines += ["", "## Inputs", ""]
    for k in ("fuos", "iboot"):
        if report[k]:
            lines += [f"- **{k}:** `{report[k]['file']}` ({report[k]['bytes']} bytes)"]
    for p in report["panics"]:
        sig = sorted({s for c in p["containers"] for s in c["panic_signatures"]})
        lines += [f"- **Panic:** `{p['file']}` — {', '.join(sig) or 'no signature'}"]
    lines += ["", "## Next action", "", report["next_action"], "",
              "See JSON for hashes, offsets, and complete metadata.", ""]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fuos", type=Path)
    ap.add_argument("--m1n1", type=Path)
    ap.add_argument("--iboot", type=Path)
    ap.add_argument("--panic", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, default=Path("j614s-diagnostics"))
    a = ap.parse_args()
    if a.m1n1 and not a.fuos:
        ap.error("--m1n1 requires --fuos")
    report = build_report(a.fuos, a.m1n1, a.iboot, a.panic)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (a.out / "report.md").write_text(markdown(report))
    print(markdown(report))
    print(f"Saved {a.out}/report.json and {a.out}/report.md")

if __name__ == "__main__":
    main()
