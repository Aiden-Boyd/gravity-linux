#!/usr/bin/env python3
"""Offline synthetic tests, no Apple firmware or active boot environment needed."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_j614s_fuos_layout import extract_properties, mode1_cursor_residue


def prop(tag, integer):
    payload = integer.to_bytes(max(1, (integer.bit_length() + 8) // 8), "big")
    return b"\x16\x04" + tag.encode("ascii") + b"\x02" + bytes([len(payload)]) + payload


class TestFuOS(unittest.TestCase):
    def test_four_byte_residue(self):
        raw = b"IMG4\x00IM4P\x00fuos\x00" + b"".join(prop(*p) for p in (
            ("kclo", 0), ("kclz", 0), ("kcwz", 0x3b0004), ("kcrz", 0), ("kclf", 0x3b0004)))
        props = extract_properties(raw)
        self.assertEqual(props["kclf"], 0x3b0004)
        self.assertEqual(mode1_cursor_residue(props), 4)
        self.assertEqual(mode1_cursor_residue({**props, "kcwz": 0x3b0000}), 0)

    def test_accumulated_sizes(self):
        props = {"kclo": 0, "kclz": 0, "kcwz": 0x4000,
                 "kcbz": 0x110, "kcxz": 0x20, "kcrz": 0x4, "kcsz": 0x2}
        self.assertEqual(mode1_cursor_residue(props), 0x136)

    def test_stock_kernelcache_nine_byte_positive_integer(self):
        # Apple kernel VAs have the high bit set, so DER adds a sign guard 0x00.
        attrs = (
            ("kclo", 0xFFFFFE0007004000),
            ("kclz", 0x15B8000),
            ("kcwz", 0x788000),
            ("kcbz", 0x8000),
            ("kcxz", 0x349C000),
            ("kcrz", 0x1670000),
            ("kcsz", 0x54000),
        )
        raw = b"".join(prop(*item) for item in attrs)
        props = extract_properties(raw)
        self.assertEqual(props["kclo"], 0xFFFFFE0007004000)
        self.assertEqual(mode1_cursor_residue(props), 0)

    def test_conflicting_property_rejected(self):
        with self.assertRaises(ValueError):
            extract_properties(prop("kcwz", 4) + prop("kcwz", 8))

    def test_missing_essential_property_rejected(self):
        with self.assertRaises(ValueError):
            mode1_cursor_residue({"kcwz": 0x4000})


if __name__ == "__main__":
    unittest.main()
