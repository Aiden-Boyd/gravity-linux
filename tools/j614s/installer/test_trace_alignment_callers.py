#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic ARM64 and modular-address tests, no proprietary firmware."""
import unittest
from trace_alignment_callers import branch_target, evaluate_alignment, analyze

class TestPanic981MemoryTranslation(unittest.TestCase):
    def test_arm64_bl(self):
        self.assertEqual(branch_target(0x3B794, 0x97FFFFB3), 0x3B660)

    def test_arm64_b(self):
        self.assertEqual(branch_target(0x3D564, 0x17FFF872), 0x3B72C)

    def test_unknown_opcode(self):
        self.assertIsNone(branch_target(0x3B794, 0))

    def test_aligned_bases(self):
        val=evaluate_alignment(0x10004000, 0x20000000, 0x40000000)
        self.assertEqual(val["remainder"], 0)
        self.assertFalse(val["would_panic_in_candidate_path"])

    def test_mismatch_bases(self):
        val=evaluate_alignment(0x10004000, 0x20000000, 0x40000800)
        self.assertEqual(val["remainder"], 0x800)
        self.assertTrue(val["would_panic_in_candidate_path"])

    def test_compensating_residues(self):
        self.assertFalse(evaluate_alignment(0x10000800, 0x20000800, 0x40000000)["would_panic_in_candidate_path"])

    def test_address_validation(self):
        with self.assertRaises(ValueError):
            evaluate_alignment(-1, 0, 0)

    def test_unknown_iboot_rejected(self):
        with self.assertRaises(ValueError):
            analyze(bytes(32))

if __name__=="__main__":
    unittest.main()
