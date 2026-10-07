#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Structural admission gate for a future J614s/T6040 NVMe candidate."""

import argparse
import json
import pathlib
import re
from dataclasses import dataclass, asdict

@dataclass
class Check:
    surface: str
    name: str
    passed: bool
    detail: str

def read(path):
    try:
        return pathlib.Path(path).read_text(errors="ignore")
    except OSError:
        return ""

def check_linux(root):
    root = pathlib.Path(root)
    apple = read(root / "drivers/nvme/host/apple.c")
    sart = read(root / "drivers/soc/apple/sart.c")
    t6040 = "apple,t6040-nvme-ans2" in apple
    m4_ioq = all(x in apple for x in ("APPLE_ANS_T8132_IOQ_CMDS","APPLE_ANS_T8132_IOQ_CQES","needs_ioq_register"))
    split = bool(re.search(r'\bmmio_nvmmu\b|\bnvmmu_base\b|resource_byname[^\n]*"nvmmu"', apple))
    coastguard = all(x in sart for x in ("apple,t8140-sart","APPLE_SART_POWER_ACTIVE","APPLE_SART_POWER_INACTIVE","sart_scan_entries"))
    return [
        Check("linux","explicit T6040 ANS2 compatible",t6040,"found" if t6040 else "missing"),
        Check("linux","M4 IOQ setup",m4_ioq,"present" if m4_ioq else "incomplete"),
        Check("linux","explicit T6040 NVMMU aperture",split,"present" if split else "missing"),
        Check("linux","CoastGuard SART lifecycle",coastguard,"present" if coastguard else "incomplete"),
    ]

def check_m1n1(root):
    nvme = read(pathlib.Path(root) / "src/nvme.c")
    checks = {
        "M4 secure-bar detection": "nvme-secure-bar" in nvme,
        "M4 reg[9] controller selection": bool(re.search(r'adt_get_reg\([^\n]*9\s*,\s*&nvme_base', nvme)),
        "M4 IOQ setup": all(x in nvme for x in ("NVME_T8132","NVME_IOQ_CMDS","NVME_IOQ_CQES")),
        "NVMMU DMA direction": all(x in nvme for x in ("NVMMU_TCB_DMA_FROM_DEVICE","NVMMU_TCB_DMA_TO_DEVICE")),
    }
    return [Check("m1n1",k,v,"present" if v else "missing") for k,v in checks.items()]

def check_contract(path):
    if path is None:
        return [Check("contract","candidate metadata",False,"not supplied")]
    try:
        d=json.loads(pathlib.Path(path).read_text())
    except Exception as exc:
        return [Check("contract","candidate metadata",False,f"invalid JSON: {exc}")]
    required=("linux_commit","m1n1_commit","dt_artifact_sha256","first_test_stage","recovery_plan")
    problems=[]
    for key in required:
        v=d.get(key)
        if not v or (isinstance(v,str) and v.startswith("REPLACE_")):
            problems.append(key)
    for key in ("linux_commit","m1n1_commit"):
        v=d.get(key,"")
        if v and not v.startswith("REPLACE_") and not re.fullmatch(r"[0-9a-fA-F]{40,64}",v):
            problems.append(key)
    sha=d.get("dt_artifact_sha256","")
    if sha and not sha.startswith("REPLACE_") and not re.fullmatch(r"[0-9a-fA-F]{64}",sha):
        problems.append("dt_artifact_sha256")
    if d.get("first_test_stage") not in (None,"N0","N1","N2","N3","N4"):
        problems.append("first_test_stage")
    return [Check("contract","candidate metadata",not problems,"complete" if not problems else "invalid: "+", ".join(sorted(set(problems))))]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--linux",type=pathlib.Path,required=True)
    p.add_argument("--m1n1",type=pathlib.Path,required=True)
    p.add_argument("--contract",type=pathlib.Path)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    checks=check_linux(a.linux)+check_m1n1(a.m1n1)+check_contract(a.contract)
    ok=all(c.passed for c in checks)
    if a.json:
        print(json.dumps({"ready_for_review":ok,"checks":[asdict(c) for c in checks]},indent=2))
    else:
        for c in checks:
            print(f"[{'PASS' if c.passed else 'FAIL'}] {c.surface}: {c.name} — {c.detail}")
        print("ADMISSION RESULT: "+("READY FOR REVIEW" if ok else "BLOCKED"))
    return 0 if ok else 2

if __name__=="__main__":
    raise SystemExit(main())
