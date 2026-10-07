#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parent / "m1n1" / "collect-gpu-adt.py"
SPEC = importlib.util.spec_from_file_location("collect_gpu_adt", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class _Reg:
    def __init__(self, addr, size):
        self.addr = addr
        self.size = size


class _Node:
    def __init__(self):
        self.reg = [_Reg(0x88000000, 0x3758000)]

    def get_reg(self, idx):
        raw = self.reg[idx]
        return raw.addr + 0x200000000, raw.size


class CollectorTests(unittest.TestCase):
    def test_raw_and_cpu_physical_ranges_are_both_reported(self):
        regs = collector.translated_regs(_Node())
        self.assertEqual(regs, [{
            "index": 0,
            "adt_bus_base": "0x88000000",
            "adt_size": "0x3758000",
            "cpu_physical_base": "0x288000000",
            "size": "0x3758000",
        }])

    def test_plain_bytes_remain_nonlossy(self):
        self.assertEqual(
            collector.plain(b"\x01\x02"),
            {"hex": "0102", "length": 2},
        )


if __name__ == "__main__":
    unittest.main()
