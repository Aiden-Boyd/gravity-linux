#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only macOS identification for J614s bring-up; never installs or boots."""
import json
import platform
import subprocess
import sys


def query(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def collect(run=query, system=None):
    system = platform.system() if system is None else system
    if system != "Darwin":
        return {"status": "unsupported_host", "host": system,
                "ready_to_boot": False,
                "reason": "Run this report on the target Mac in macOS."}
    fields = {
        "model": "hw.model", "cpu_brand": "machdep.cpu.brand_string",
        "physical_cpus": "hw.physicalcpu", "logical_cpus": "hw.logicalcpu",
        "memory_bytes": "hw.memsize",
        "perflevel0_physical_cpus": "hw.perflevel0.physicalcpu",
        "perflevel1_physical_cpus": "hw.perflevel1.physicalcpu",
    }
    hardware = {}
    for name, key in fields.items():
        value = run(["/usr/sbin/sysctl", "-n", key])
        hardware[name] = int(value) if value and value.isdecimal() else value
    matched = hardware["model"] == "Mac16,8" and hardware["cpu_brand"] == "Apple M4 Pro"
    return {
        "report_version": 1,
        "status": "model_matches" if matched else "model_unconfirmed",
        "hardware": hardware,
        "macos": {
            "version": run(["/usr/bin/sw_vers", "-productVersion"]),
            "build": run(["/usr/bin/sw_vers", "-buildVersion"]),
        },
        "target": {"board": "J614s", "soc": "T6040", "model": "Mac16,8"},
        "ready_to_boot": False,
        "unverified": ["loader_and_firmware_compatibility", "recovery_path",
                       "hardware_boot", "console_input", "thermal_behaviour"],
        "notice": "Model identification is not boot approval. No disk, boot-policy or firmware changes were made.",
    }


if __name__ == "__main__":
    report = collect()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "model_matches" else 2)
