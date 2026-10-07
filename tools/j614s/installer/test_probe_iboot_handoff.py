#!/usr/bin/env python3
"""Synthetic tests for the read-only iBoot handoff audit."""
import base64
import importlib.util
import json
import plistlib
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).with_name("probe_iboot_handoff.py")
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class TestAudit(unittest.TestCase):
    def test_synthetic_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            gid = "A" * 8 + "-" + "B" * 4 + "-" + "C" * 4 + "-" + "D" * 4 + "-" + "E" * 12
            active = "1" * 96
            coih = "2" * 96
            pb = root / "Preboot" / gid
            (pb / "boot" / active / "System/Library/Caches/com.apple.kernelcaches").mkdir(parents=True)
            (pb / "boot" / active / "usr/standalone/firmware").mkdir(parents=True)
            (pb / "restore").mkdir(parents=True)
            (pb / "boot/active").write_text(active)
            stub = root / "Stub"
            (stub / "Finish Installation.app/Contents/Resources").mkdir(parents=True)
            (stub / "System/Library/CoreServices").mkdir(parents=True)
            original = b"PINNED_BINARY"
            (root / "m1n1.bin").write_bytes(original)
            boot = original + b"\0" * 4
            (stub / "Finish Installation.app/Contents/Resources/boot.bin").write_bytes(boot)
            (
                pb / "boot" / active / "System/Library/Caches/com.apple.kernelcaches"
                / ("kernelcache.custom." + coih)
            ).write_bytes(b"30\x00IMG4xxIM4Pyyfuos" + boot)
            (pb / "boot" / active / "usr/standalone/firmware/iBoot.img4").write_bytes(b"iboot")
            version = {"ProductVersion": "15.1", "ProductBuildVersion": "24B2083"}
            (stub / "System/Library/CoreServices/SystemVersion.plist").write_bytes(
                plistlib.dumps(version)
            )
            (pb / "restore/SystemVersion.plist").write_bytes(plistlib.dumps(version))
            panic = root / "panic.panic"
            soc = (
                b"iBoot Panic: : 3bdace14b1a9a68:981\n"
                b"Build: RELEASE:iBoot-11881.41.5\n3000d(67667866)\n"
            )
            panic.write_text(
                json.dumps({"timestamp": "test", "os_version": "macOS 15.1"}) + "\n" +
                json.dumps({
                    "panicString": "SOCD report detected: (iBoot panic)",
                    "SOCDContainers": [{
                        "SOCDContainer": base64.b64encode(soc).decode()
                    }],
                })
            )
            lines = audit.audit(root / "Preboot", gid, stub, root / "m1n1.bin", panic)
            self.assertIn("M1N1_EXACTLY_EMBEDDED: True", lines)
            self.assertIn("PACKAGING_IS_ORIGINAL_PLUS_4_ZERO_BYTES: True", lines)
            self.assertIn("PANIC_PANIC_LOCATIONS: 3bdace14b1a9a68:981", lines)
            self.assertIn("PANIC_FIRMWARE_TAGS: gfxf", lines)
            self.assertIn("PANIC_IBOOT_BUILDS: RELEASE:iBoot-11881.41.5", lines)
            self.assertIn("IMG4_WRAPPER: True", lines)

    def test_bad_pointer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            p = r / "PB" / "VG" / "boot"
            p.mkdir(parents=True)
            (p / "active").write_text("BAD")
            with self.assertRaisesRegex(ValueError, "active boot pointer"):
                audit.audit(r / "PB", "VG", r / "System", None, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
