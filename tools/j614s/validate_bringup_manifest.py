#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import argparse
import json
import pathlib
import re
import sys


def fail(msg):
    raise SystemExit(f"bring-up manifest INVALID: {msg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path)
    args = ap.parse_args()

    data = json.loads(args.manifest.read_text())
    if data.get("schema_version") != 1:
        fail("unsupported schema_version")
    if data.get("machine") != {"model":"Mac16,8","board":"J614s","soc":"T6040"}:
        fail("machine identity is not the J614s/T6040 target")

    profiles = data.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        fail("profiles list missing")

    ids = [p.get("id") for p in profiles]
    if len(ids) != len(set(ids)):
        fail("duplicate profile id")

    orders = [p.get("order") for p in profiles]
    if any(not isinstance(x, int) for x in orders) or len(orders) != len(set(orders)):
        fail("orders must be unique integers")

    by_id = {p["id"]: p for p in profiles}
    allowed_gates = {
        "safe", "smp-thin", "pcie-dart-thin", "smc-thin", "wifi-bt",
        "sd", "nvme-readonly", "input", "power", "diagnostic", "yolo",
        "gpu-native",
    }

    for p in profiles:
        pid = p["id"]
        if p.get("source_gate") not in allowed_gates:
            fail(f"{pid}: unknown source_gate")
        deps = p.get("boot_after", [])
        if not isinstance(deps, list):
            fail(f"{pid}: boot_after must be a list")
        for dep in deps:
            if dep not in by_id:
                fail(f"{pid}: unknown boot dependency {dep}")
            if by_id[dep]["order"] >= p["order"]:
                fail(f"{pid}: dependency {dep} does not precede it in boot order")

        if p.get("build_enabled"):
            sha = p.get("source_commit")
            branch = p.get("source_branch")
            if not branch:
                fail(f"{pid}: build-enabled profile has no source_branch")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                fail(f"{pid}: build-enabled profile lacks immutable 40-hex source_commit")
            if p.get("blocked_reason"):
                fail(f"{pid}: profile cannot be both build-enabled and blocked")
        else:
            if not p.get("blocked_reason"):
                fail(f"{pid}: blocked profile is missing blocked_reason")

    # Simple DFS cycle check independent of order validation.
    visiting = set()
    visited = set()
    def visit(pid):
        if pid in visited:
            return
        if pid in visiting:
            fail(f"dependency cycle at {pid}")
        visiting.add(pid)
        for dep in by_id[pid].get("boot_after", []):
            visit(dep)
        visiting.remove(pid)
        visited.add(pid)
    for pid in ids:
        visit(pid)

    buildable = [p["id"] for p in sorted(profiles, key=lambda x:x["order"]) if p.get("build_enabled")]
    print("manifest valid")
    print("buildable profiles:", " ".join(buildable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
