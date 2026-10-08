#!/usr/bin/env python3
"""Offline synthetic tests for a nonbootable J614s fuOS padding model."""

import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_fuos_padding_model import make_model, PAGE_ALIGNMENT, TERMINATOR


class PaddingModelTests(unittest.TestCase):
    def setUp(self):
        self.source = b"TEST" * (PAGE_ALIGNMENT // 4)
        self.source_hash = hashlib.sha256(self.source).hexdigest()

    def model(self, value=None, **kwargs):
        source = self.source if value is None else value
        return make_model(source, expected_hash=self.source_hash,
                          expected_length=len(self.source), **kwargs)

    def test_preserves_original_and_terminator(self):
        candidate, report = self.model()
        self.assertEqual(candidate[:len(self.source)], self.source)
        self.assertEqual(candidate[len(self.source):len(self.source) + 4], TERMINATOR)
        self.assertEqual(report["extra_post_terminator_padding"], 0x3FFC)
        self.assertEqual(candidate[len(self.source) + 4:], b"\x00" * 0x3FFC)
        self.assertEqual(len(candidate), PAGE_ALIGNMENT * 2)
        self.assertEqual(report["current_conditional_mode1_low12"], 4)
        self.assertEqual(report["model_conditional_mode1_low12"], 0)

    def test_deterministic(self):
        a, report_a = self.model()
        b, report_b = self.model()
        self.assertEqual(a, b)
        self.assertEqual(report_a, report_b)
        self.assertEqual(report_a["model_sha256"], hashlib.sha256(a).hexdigest())

    def test_wrong_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.model(value=self.source[:-1] + b"X")

    def test_wrong_length_rejected(self):
        with self.assertRaisesRegex(ValueError, "length"):
            self.model(value=self.source[:-4])

    def test_non_aligned_source_rejected(self):
        misaligned = b"X" * (PAGE_ALIGNMENT + 4)
        with self.assertRaisesRegex(ValueError, "aligned"):
            make_model(misaligned, expected_hash=hashlib.sha256(misaligned).hexdigest(),
                       expected_length=len(misaligned))


if __name__ == "__main__":
    unittest.main()
