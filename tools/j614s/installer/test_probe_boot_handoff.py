#!/usr/bin/env python3
"""Synthetic, offline tests for the read-only J614s boot handoff audit."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

import probe_boot_handoff as p


VGID = "1B517D62-C96F-4CC6-BD52-6320F1AC845D"
ACTIVE = "9F745CB68D205FD01A1D4C57A1F4378AB16321ABF714B045207FD8A46D87CFD7F8511DC5144F95BCC538D082ADD8AE8A"
CUSTOM = "50AD5E77B497CE00881635BE3B95371E166183F5CD4C5D0624BD30B52CBEE2A575B69C2188FD136936B265CC593C1BD8"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.preboot = base / "Preboot"
        self.system = base / "System"
        self.source = base / "m1n1.bin"
        root = self.preboot / VGID
        bootroot = root / "boot"
        bootroot.mkdir(parents=True)
        (bootroot / "active").write_text(ACTIVE + "\n")
        customdir = bootroot / ACTIVE / "System/Library/Caches/com.apple.kernelcaches"
        customdir.mkdir(parents=True)

        raw = b"MOCK_m1n1\n"
        self.source.write_bytes(raw)
        self.original_sha = p.EXPECTED_M1N1_SHA256
        p.EXPECTED_M1N1_SHA256 = hashlib.sha256(raw).hexdigest()
        self.addCleanup(setattr, p, "EXPECTED_M1N1_SHA256", self.original_sha)
        boot = raw + b"\x00" * 4
        bootpath = self.system / "Finish Installation.app/Contents/Resources/boot.bin"
        bootpath.parent.mkdir(parents=True)
        bootpath.write_bytes(boot)
        (customdir / ("kernelcache.custom." + CUSTOM)).write_bytes(
            b"\x30\x01IMG4\x00IM4P\x00fuos\x00" + b"0" * (72 - 19) + boot
        )
        systemplist = self.system / "System/Library/CoreServices/SystemVersion.plist"
        systemplist.parent.mkdir(parents=True)
        systemplist.write_bytes(plistlib.dumps({"ProductVersion": "15.1", "ProductBuildVersion": "24B2083"}))
        recoverplist = root / "restore/SystemVersion.plist"
        recoverplist.parent.mkdir(parents=True)
        recoverplist.write_bytes(plistlib.dumps({"ProductVersion": "15.1", "ProductBuildVersion": "24B2083"}))

        self.policy = base / "policy.txt"
        self.policy.write_text(
            "Next Stage Image4 Hash                  (nsih): " + ACTIVE + "\n"
            "CustomKC or fuOS Image4 Hash            (coih): " + CUSTOM + "\n"
            "Pairing Integrity                             : Valid\n"
            "Security Mode:               Permissive (smb0 && smb1): 1\n"
        )
        self.args = ["--vgid", VGID, "--preboot", str(self.preboot),
                     "--system", str(self.system), "--source", str(self.source),
                     "--policy-file", str(self.policy)]

    def invoke(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = p.main(self.args)
        return status, output.getvalue()

    def test_expected_complete_stub(self):
        status, out = self.invoke()
        self.assertEqual(status, 0, out)
        self.assertIn("Checks: 10 passed, 0 failed", out)
        self.assertIn("Local policy nsih matches", out)

    def test_policy_hash_mismatch(self):
        data = self.policy.read_text().replace(ACTIVE, "A" * 96)
        self.policy.write_text(data)
        status, out = self.invoke()
        self.assertEqual(status, 1)
        self.assertIn("FAIL  Local policy nsih", out)

    def test_missing_preboot(self):
        self.args[3] = str(Path(self.tmp.name) / "not-a-volume")
        status, out = self.invoke()
        self.assertEqual(status, 2)
        self.assertIn("FAIL  Gravity Preboot directory accessible", out)

    def test_wrong_payload(self):
        bootpath = self.system / "Finish Installation.app/Contents/Resources/boot.bin"
        bootpath.write_bytes(b"BROKEN")
        status, out = self.invoke()
        self.assertEqual(status, 1)
        self.assertIn("FAIL  Installed boot.bin", out)

    def test_panic_summary(self):
        path = Path(self.tmp.name) / "panic.panic"
        path.write_text(json.dumps({"os_version": "macOS 15.1"}) + "\n" +
                        json.dumps({"panicString": "SOCD report detected: (iBoot panic)",
                                    "build": "macOS 15.1", "SOCDContainers": []}))
        msg, version, codes = p.panic_summary(path)
        self.assertIn("iBoot panic", msg)
        self.assertEqual(version, "macOS 15.1")
        self.assertEqual(codes, [])


if __name__ == "__main__":
    unittest.main()
