#!/usr/bin/env python3
import base64
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("diag", Path(__file__).with_name("one_shot_diagnostics.py"))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)

class DiagnosticsTests(unittest.TestCase):
    def test_synthetic_fuos_payload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = b"FAKE_M1N1" + bytes(7)
            payload = source + bytes(4)
            # Format used by the known image: DER OCTET STRING after IM4P metadata.
            prefix = b"\x30\x83\x00\x00\x40\x16\x04IMG4\x16\x04IM4P\x16\x04fuos"
            blob = prefix + b"\x04\x83" + len(payload).to_bytes(3, "big") + payload + b"trailer"
            fuos = root / "test.img4"
            src = root / "m1n1.bin"
            fuos.write_bytes(blob)
            src.write_bytes(source)
            info = diag.fuos_info(fuos, src)
            self.assertTrue(info["payload"]["matches_m1n1_plus_four_nuls"])
            self.assertEqual(info["payload"]["bytes"], len(payload))
            self.assertEqual(info["payload"]["offset"], len(prefix) + 5)

    def test_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payload = b"DIFFERENT"
            prefix = b"\x30\x83\x00\x00\x40IMG4IM4Pfuos"
            a, b = root / "a.img4", root / "b.bin"
            a.write_bytes(prefix + b"\x04\x83" + len(payload).to_bytes(3, "big") + payload)
            b.write_bytes(b"source")
            self.assertFalse(diag.fuos_info(a,b)["payload"]["matches_m1n1_plus_four_nuls"])

    def test_synthetic_panic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample.panic"
            raw = b"SOCDxxxxiBoot Panic: : 3bdace14b1a9a68:981\nBuild: RELEASE:iBoot-11881.41.5\n"
            header = {"timestamp": "synthetic"}
            report = {"product":"Mac16,8", "SOCDContainers":[{"SOCDContainer":base64.b64encode(raw).decode()}]}
            p.write_text(json.dumps(header)+"\n"+json.dumps(report))
            info = diag.panic_info(p)
            self.assertEqual(info["containers"][0]["panic_signatures"], ["3bdace14b1a9a68:981"])
            self.assertEqual(info["containers"][0]["iboot_builds"], ["RELEASE:iBoot-11881.41.5"])

    def test_report_without_inputs(self):
        report=diag.build_report()
        self.assertEqual(report["mode"], "read_only")
        self.assertIn("Next action",diag.markdown(report))

if __name__ == "__main__":
    unittest.main()
