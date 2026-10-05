#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("adt_pcie_report.py")
SPEC = importlib.util.spec_from_file_location("adt_pcie_report", MODULE_PATH)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class AdtPcieReportTests(unittest.TestCase):
    def sample_archive(self):
        return [{
            "IORegistryEntryName": "root",
            "IORegistryEntryChildren": [{
                "IORegistryEntryName": "arm-io",
                "compatible": b"arm-io,t6040\\0",
                "IORegistryEntryChildren": [{
                    "IORegistryEntryName": "apcie@1cb0000000",
                    "compatible": b"apcie,t6040\\0",
                    "reg": bytes.fromhex(
                        "0000001c b0000000 00000000 10000000"
                    ),
                    "interrupts": (
                        (1723).to_bytes(4, "big") +
                        (1732).to_bytes(4, "big")
                    ),
                    "serial-number": "do-not-export",
                    "IORegistryEntryChildren": [{
                        "IORegistryEntryName": "port01",
                        "reg": (0x800).to_bytes(4, "big"),
                    }],
                }, {
                    "IORegistryEntryName": "dart-apcie1",
                    "compatible": b"dart,t8110\\0",
                    "reg": (
                        (0x4).to_bytes(4, "big") +
                        (0x11000000).to_bytes(4, "big")
                    ),
                }],
            }],
        }]

    def test_extracts_relevant_nodes_and_cells(self):
        nodes = REPORT.extract_nodes(self.sample_archive())
        by_name = {node["name"]: node for node in nodes}
        self.assertIn("apcie@1cb0000000", by_name)
        self.assertIn("dart-apcie1", by_name)
        reg = by_name["apcie@1cb0000000"]["properties"]["reg"]
        self.assertEqual(reg["cells"][0], "0x0000001c")
        self.assertEqual(reg["cells"][1], "0xb0000000")

    def test_sensitive_identifiers_are_not_exported(self):
        nodes = REPORT.extract_nodes(self.sample_archive())
        apcie = next(node for node in nodes if node["name"].startswith("apcie@"))
        self.assertNotIn("serial-number", apcie["properties"])

    def test_archive_mode_never_claims_boot_readiness(self):
        report = REPORT.collect(archive=self.sample_archive(), system="Linux")
        self.assertEqual(report["status"], "evidence_collected")
        self.assertFalse(report["ready_to_boot"])
        self.assertTrue(report["read_only"])

    def test_live_mode_rejects_non_macos_hosts(self):
        report = REPORT.collect(system="Linux")
        self.assertEqual(report["status"], "unsupported_host")
        self.assertFalse(report["ready_to_boot"])


if __name__ == "__main__":
    unittest.main()
