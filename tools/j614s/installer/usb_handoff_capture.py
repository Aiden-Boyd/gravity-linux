#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Passive USB evidence collection for J614s first-boot debugging on a Linux host.

Never connects to devices, opens serial ports, writes boot policy or changes USB state.
- --history parses kernel events from a previously attempted boot.
- --live watches kernel events AND polls USB sysfs during the NEXT boot attempt.
Expected m1n1 USB CDC VID:PID is 1209:316d; 05ac:1905 is an Apple Mac interface.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

M1N1 = "1209:316d"
APPLE_MAC = "05ac:1905"
USB_PATTERN = re.compile(r"(usb|xhci|typec|thunderbolt|ttyACM|cdc_acm|usbmux|dart)", re.I)
ID_PATTERN = re.compile(r"idVendor=([0-9a-f]{4}),\s*idProduct=([0-9a-f]{4})", re.I)
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def usb_sysfs():
    result = {}
    for item in sorted(Path("/sys/bus/usb/devices").glob("*")):
        try:
            vendor = (item / "idVendor").read_text().strip().lower()
            product = (item / "idProduct").read_text().strip().lower()
            if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(r"[0-9a-f]{4}", product):
                continue
            def value(name):
                try:
                    return (item / name).read_text(errors="replace").strip()
                except OSError:
                    return ""
            result[item.name] = {
                "vidpid": vendor + ":" + product,
                "manufacturer": value("manufacturer"),
                "product": value("product"),
                "serial_present": bool(value("serial")),
                "busnum": value("busnum"),
                "devnum": value("devnum"),
            }
        except OSError:
            pass
    return result


def summary(lines, snapshots):
    ids = set()
    usb_lines = []
    tty_lines = []
    for line in lines:
        if not USB_PATTERN.search(line):
            continue
        usb_lines.append(line)
        for m in ID_PATTERN.finditer(line):
            ids.add((m.group(1) + ":" + m.group(2)).lower())
        if re.search(r"ttyACM|cdc_acm", line, re.I):
            tty_lines.append(line)
    for snap in snapshots:
        for dev in snap.get("devices", {}).values():
            ids.add(dev["vidpid"])
    return {
        "detected_ids": sorted(ids),
        "m1n1_vidpid_observed": M1N1 in ids,
        "apple_mac_vidpid_observed": APPLE_MAC in ids,
        "serial_kernel_lines": tty_lines,
        "relevant_kernel_line_count": len(usb_lines),
        "interpretation": (
            "m1n1 USB VID:PID observed. Verify proxy handshake on the matching tty; USB alone is not proof of a working proxy."
            if M1N1 in ids else
            "No m1n1 USB VID:PID observed. This cannot distinguish an iBoot-stage failure from m1n1 failing before USB enumeration."
        )
    }


def get_journal(since, until=None):
    cmd = ["journalctl", "-k", "--no-pager", "-o", "short-iso", "--since", since]
    if until:
        cmd.extend(["--until", until])
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode:
        raise RuntimeError(f"journalctl failed: {completed.stderr.strip()}")
    return completed.stdout.splitlines()


def history(args):
    lines = get_journal(args.since, args.until)
    verdict = summary(lines, [])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "mode": "historical-kernel-log", "since": args.since,
            "until": args.until, "analysis": verdict,
            "relevant_kernel_lines": [x for x in lines if USB_PATTERN.search(x)]
        }, indent=2) + "\n")
    print("Previous attempt kernel USB evidence")
    for line in lines:
        if USB_PATTERN.search(line):
            print(line)
    print("\nSummary:")
    print(json.dumps(verdict, indent=2))
    if args.output:
        print("Saved:", args.output)


def live(args):
    dest = args.output or Path.cwd() / ("j614s-usb-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    events = []
    snapshots = []
    lock = threading.Lock()
    baseline = now()
    cmd = ["journalctl", "-k", "--follow", "--no-pager", "-o", "short-iso", "--since", baseline]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1)

    def read_journal():
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if not USB_PATTERN.search(line):
                continue
            with lock:
                events.append(line)
            print("[kernel]", line, flush=True)

    thread = threading.Thread(target=read_journal, daemon=True)
    thread.start()
    print("Started at", baseline)
    print("PASSIVE monitoring only: start this BEFORE selecting Gravity on the target.")
    print("Will watch kernel USB events and USB sysfs for", args.seconds, "seconds.")
    print("Expected m1n1 ID", M1N1, "; macOS USB interface", APPLE_MAC)
    last = None
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            state = usb_sysfs()
            if state != last:
                snapshots.append({"timestamp": now(), "devices": state})
                added = set(state) - set(last or {})
                removed = set(last or {}) - set(state)
                changed = {x for x in set(state) & set(last or {})
                           if state[x] != last[x]}
                for key in sorted(added | changed):
                    print("[sysfs]", now(), key, "ADDED/CHANGED", state[key], flush=True)
                for key in sorted(removed):
                    print("[sysfs]", now(), key, "REMOVED", flush=True)
                last = state
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nInterrupted; saving observations.")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        thread.join(timeout=2)
        with lock:
            all_events = list(events)
        result = {
            "mode": "passive-live", "started": baseline, "ended": now(),
            "host_os": os.uname().sysname, "seconds_requested": args.seconds,
            "analysis": summary(all_events, snapshots),
            "relevant_kernel_lines": all_events,
            "usb_sysfs_changes": snapshots
        }
        dest.write_text(json.dumps(result, indent=2) + "\n")
        print("\nSummary:", json.dumps(result["analysis"], indent=2))
        print("Saved:", dest)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--history", action="store_true", help="Parse earlier kernel journal")
    mode.add_argument("--live", action="store_true", help="Capture a new boot attempt")
    p.add_argument("--since", help="Local time, e.g. '2026-10-08 16:08:45'")
    p.add_argument("--until", help="Local time, e.g. '2026-10-08 16:13:50'")
    p.add_argument("--seconds", type=int, default=300, help="Live watch duration")
    p.add_argument("--output", type=Path, help="JSON evidence file")
    args = p.parse_args()
    if args.history:
        if not args.since or not args.until:
            p.error("--history requires --since and --until")
        history(args)
    else:
        if args.seconds <= 0:
            p.error("--seconds must be positive")
        if sys.platform != "linux":
            p.error("--live requires Linux host")
        live(args)


if __name__ == "__main__":
    main()
