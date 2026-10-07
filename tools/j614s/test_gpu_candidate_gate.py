#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import json
import pathlib
import tempfile
import unittest

import gpu_candidate_gate as gate


class CandidateGateTests(unittest.TestCase):
    def make_tree(self):
        td = tempfile.TemporaryDirectory()
        root = pathlib.Path(td.name)
        m1n1 = root / "m1n1"
        linux = root / "linux"
        mesa = root / "mesa"
        (m1n1 / "src").mkdir(parents=True)
        (m1n1 / "rust/src/gpu/hw").mkdir(parents=True)
        (linux / "drivers/gpu/drm/asahi").mkdir(parents=True)
        (linux / "arch/arm64/boot/dts/apple").mkdir(parents=True)
        (mesa / "src/asahi/lib").mkdir(parents=True)
        return td, m1n1, linux, mesa

    def test_current_style_stack_is_rejected(self):
        td, m1n1, linux, mesa = self.make_tree()
        self.addCleanup(td.cleanup)
        (m1n1 / "src/kboot_gpu.c").write_text(
            "int dt_set_gpu(void *dt) { switch (chip_id) { case T6022: break; default: return 0; } }"
        )
        (m1n1 / "rust/src/gpu/hw/mod.rs").write_text("enum GpuGen { G13 = 13, G14 = 14 }")
        (linux / "drivers/gpu/drm/asahi/driver.rs").write_text(
            'DeviceId::new(c_str!("apple,agx-t6022"))'
        )
        (mesa / "src/asahi/lib/agx_device.c").write_text("/* G14 only */")

        checks = gate.check_m1n1(m1n1) + gate.check_linux(linux) + gate.check_mesa(mesa)
        self.assertFalse(all(c.passed for c in checks))

    def test_explicit_g16_stack_can_reach_human_review(self):
        td, m1n1, linux, mesa = self.make_tree()
        self.addCleanup(td.cleanup)
        (m1n1 / "src/kboot_gpu.c").write_text(
            "int dt_set_gpu(void *dt) { switch (chip_id) { case T6040: break; default: return 0; } }"
        )
        (m1n1 / "rust/src/gpu/hw/mod.rs").write_text("enum GpuGen { G16 = 16 }")
        (linux / "drivers/gpu/drm/asahi/driver.rs").write_text(
            'DeviceId::new(c_str!("apple,agx-t6040")); GpuGen::G16; HWCONFIG_T6040;'
        )
        (mesa / "src/asahi/lib/agx_device.c").write_text("AGX_CHIP_G16")

        checks = gate.check_m1n1(m1n1) + gate.check_linux(linux) + gate.check_mesa(mesa)
        self.assertTrue(all(c.passed for c in checks), [c for c in checks if not c.passed])

    def test_g14_alias_is_rejected(self):
        td, _m1n1, linux, _mesa = self.make_tree()
        self.addCleanup(td.cleanup)
        (linux / "drivers/gpu/drm/asahi/driver.rs").write_text(
            'DeviceId::new(c_str!("apple,agx-t6040")), &hw::t602x::HWCONFIG_T6022; GpuGen::G16;'
        )
        checks = gate.check_linux(linux)
        alias = next(c for c in checks if "alias" in c.name)
        self.assertFalse(alias.passed)

    def test_contract_template_placeholders_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "contract.json"
            path.write_text(json.dumps({
                "dt_compatible": "apple,agx-t6040",
                "firmware_abi_or_build": "REPLACE_WITH_ABI",
                "first_test_scope": "G0",
                "crash_recovery": "REPLACE_WITH_RECOVERY",
                "m1n1_commit": "1" * 40,
                "linux_commit": "2" * 40,
                "mesa_commit": "3" * 40,
            }))
            result = gate.check_contract(path)
            self.assertFalse(result[0].passed)

    def test_short_nonimmutable_commit_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "contract.json"
            path.write_text(json.dumps({
                "dt_compatible": "apple,agx-t6040",
                "firmware_abi_or_build": "26.x-G16-maintainer-contract",
                "first_test_scope": "G0 probe-only",
                "crash_recovery": "serial watchdog then sanctioned reboot",
                "m1n1_commit": "abc",
                "linux_commit": "def",
                "mesa_commit": "ghi",
            }))
            result = gate.check_contract(path)
            self.assertFalse(result[0].passed)

    def test_completed_contract_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "contract.json"
            path.write_text(json.dumps({
                "dt_compatible": "apple,agx-t6040",
                "firmware_abi_or_build": "26.x-G16-maintainer-contract",
                "first_test_scope": "G0 probe-only",
                "crash_recovery": "serial watchdog then sanctioned reboot",
                "m1n1_commit": "1" * 40,
                "linux_commit": "2" * 40,
                "mesa_commit": "3" * 40,
            }))
            result = gate.check_contract(path)
            self.assertTrue(result[0].passed)


if __name__ == "__main__":
    unittest.main()
