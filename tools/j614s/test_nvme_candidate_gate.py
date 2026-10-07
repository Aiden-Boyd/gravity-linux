#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import json
import pathlib
import tempfile
import unittest

import nvme_candidate_gate as gate


class NVMeCandidateGateTests(unittest.TestCase):
    def make_tree(self):
        td = tempfile.TemporaryDirectory()
        root = pathlib.Path(td.name)
        linux = root / "linux"
        m1n1 = root / "m1n1"
        (linux / "drivers/nvme/host").mkdir(parents=True)
        (linux / "drivers/soc/apple").mkdir(parents=True)
        (m1n1 / "src").mkdir(parents=True)
        return td, linux, m1n1

    def test_current_style_single_aperture_linux_is_blocked(self):
        td, linux, _ = self.make_tree()
        self.addCleanup(td.cleanup)
        (linux / "drivers/nvme/host/apple.c").write_text(
            'APPLE_ANS_T8132_IOQ_CMDS APPLE_ANS_T8132_IOQ_CQES needs_ioq_register '
            '"apple,t8132-nvme-ans2"'
        )
        (linux / "drivers/soc/apple/sart.c").write_text(
            'apple,t8140-sart APPLE_SART_POWER_ACTIVE APPLE_SART_POWER_INACTIVE sart_scan_entries'
        )
        self.assertFalse(all(c.passed for c in gate.check_linux(linux)))

    def test_explicit_t6040_split_resource_linux_can_pass_structure(self):
        td, linux, _ = self.make_tree()
        self.addCleanup(td.cleanup)
        (linux / "drivers/nvme/host/apple.c").write_text(
            'APPLE_ANS_T8132_IOQ_CMDS APPLE_ANS_T8132_IOQ_CQES needs_ioq_register '
            '"apple,t6040-nvme-ans2" mmio_nvmmu'
        )
        (linux / "drivers/soc/apple/sart.c").write_text(
            'apple,t8140-sart APPLE_SART_POWER_ACTIVE APPLE_SART_POWER_INACTIVE sart_scan_entries'
        )
        self.assertTrue(all(c.passed for c in gate.check_linux(linux)))

    def test_m1n1_m4_shape(self):
        td, _, m1n1 = self.make_tree()
        self.addCleanup(td.cleanup)
        (m1n1 / "src/nvme.c").write_text(
            'nvme-secure-bar NVME_T8132 NVME_IOQ_CMDS NVME_IOQ_CQES '
            'NVMMU_TCB_DMA_FROM_DEVICE NVMMU_TCB_DMA_TO_DEVICE '
            'adt_get_reg(adt, adt_path, "reg", 9, &nvme_base, NULL)'
        )
        self.assertTrue(all(c.passed for c in gate.check_m1n1(m1n1)))

    def test_contract_rejects_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "c.json"
            path.write_text(json.dumps({
                "linux_commit": "REPLACE_WITH_IMMUTABLE_COMMIT",
                "m1n1_commit": "1" * 40,
                "dt_artifact_sha256": "2" * 64,
                "first_test_stage": "N0",
                "recovery_plan": "serial recovery",
                "storage_policy": {
                    "auto_probe": False,
                    "filesystem_use": False,
                    "modification_allowed": False,
                },
            }))
            self.assertFalse(gate.check_contract(path)[0].passed)

    def test_contract_accepts_gated_immutable_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "c.json"
            path.write_text(json.dumps({
                "linux_commit": "1" * 40,
                "m1n1_commit": "2" * 40,
                "dt_artifact_sha256": "3" * 64,
                "first_test_stage": "N2",
                "recovery_plan": "serial recovery and known-good tethered boot",
                "storage_policy": {
                    "auto_probe": False,
                    "filesystem_use": False,
                    "modification_allowed": False,
                },
            }))
            self.assertTrue(gate.check_contract(path)[0].passed)


if __name__ == "__main__":
    unittest.main()
