#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small no-hardware unit tests for J614s USB capture classification."""
import unittest
from usb_handoff_capture import summary

class TestUSBForensics(unittest.TestCase):
    def test_apple_mac_not_proxy(self):
        report=summary(['Oct 08 16:11:02 kernel: usb 1-4: New USB device found, idVendor=05ac, idProduct=1905'],[])
        self.assertTrue(report["apple_mac_vidpid_observed"])
        self.assertFalse(report["m1n1_vidpid_observed"])

    def test_m1n1_in_kernel_logs(self):
        report=summary(['kernel: usb 1-4: New USB device found, idVendor=1209, idProduct=316d'],[])
        self.assertTrue(report["m1n1_vidpid_observed"])

    def test_m1n1_in_sysfs_snapshot(self):
        report=summary([], [{"devices":{"1-4":{"vidpid":"1209:316d"}}}])
        self.assertTrue(report["m1n1_vidpid_observed"])

    def test_absence_inconclusive(self):
        report=summary([],[])
        self.assertFalse(report["m1n1_vidpid_observed"])
        self.assertIn("cannot distinguish",report["interpretation"])

if __name__=="__main__":
    unittest.main()
