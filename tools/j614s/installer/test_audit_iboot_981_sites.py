#!/usr/bin/env python3
"""Synthetic J614s panic-source tests; no Apple firmware distributed."""
import struct
import unittest
from audit_iboot_981_sites import branch_target, constant_x0, inspect


def movz(reg=0, imm=0x9a68, hw=0):
    return 0xD2800000 | (hw << 21) | (imm << 5) | reg


def movk(reg=0, imm=0x4b1a, hw=1):
    return 0xF2800000 | (hw << 21) | (imm << 5) | reg


class TestSourceHash(unittest.TestCase):
    def test_branch(self):
        self.assertEqual(branch_target(0x3b840, 0x94011a84), 0x82250)

    def test_non_branch(self):
        self.assertIsNone(branch_target(0, 0x52807aa1))

    def test_hash_constant(self):
        b = struct.pack("<5I", movz(), movk(), movk(imm=0xace1,hw=2),
                        movk(imm=0x3bd,hw=3), 0xD65F03C0)
        self.assertEqual(constant_x0(b, 0), 0x03BDACE14B1A9A68)

    def test_wrong_register(self):
        b = struct.pack("<5I", movz(reg=1), movk(), movk(imm=0xace1,hw=2),
                        movk(imm=0x3bd,hw=3), 0xD65F03C0)
        with self.assertRaises(ValueError):
            constant_x0(b, 0)

    def test_wrong_return(self):
        b = struct.pack("<5I", movz(), movk(), movk(imm=0xace1,hw=2),
                        movk(imm=0x3bd,hw=3), 0)
        with self.assertRaises(ValueError):
            constant_x0(b, 0)

    def test_unknown_binary(self):
        with self.assertRaises(ValueError):
            inspect(bytes(64))


if __name__ == "__main__":
    unittest.main()
