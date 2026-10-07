# J614s driver readiness matrix

This matrix separates **compiled**, **exact-hardware proven elsewhere**, and
**proven in this Gravity build**. A green CI build is not a hardware proof.

| Subsystem | Gravity driver/path | Current policy | Exact J614s evidence | Gravity live proof |
|---|---|---|---|---|
| UART / early console | Samsung serial | SAFE built-in | yes | pending first boot |
| AICv3 | irq-apple-aic T6040 quirk | SAFE built-in | yes | pending |
| PMGR | apple T6041 power domains | SAFE built-in | yes | pending |
| CPU frequency | apple-soc-cpufreq | diagnostic module / YOLO built-in | yes, including >4.294 GHz fix | pending |
| Keyboard | DockChannel + hid-apple | diagnostic module / YOLO built-in | yes | pending |
| Trackpad / haptics | DockChannel + hid-magicmouse | diagnostic module / YOLO built-in | yes, touch+haptics | pending; paired firmware required |
| SMC core/GPIO | macsmc + gpio-macsmc | diagnostic module / YOLO built-in | yes | pending |
| Battery / AC | macsmc-power | diagnostic module / YOLO built-in | yes | pending |
| Thermals / fans | macsmc-hwmon | diagnostic module / YOLO built-in | yes | pending |
| Lid / power button | macsmc-input | diagnostic module / YOLO built-in | yes | pending |
| PCIe | pcie-apple + Apple DART | staged diagnostic only | yes | pending; stage1 handoff gating still under review |
| Wi-Fi | brcmfmac BCM4388 | staged diagnostic / YOLO built-in | yes | pending; paired firmware required |
| Bluetooth | hci_bcm4377 BCM4388 | staged diagnostic / YOLO built-in | yes | pending; paired firmware required |
| SD reader | sdhci-pci GL9755 | staged diagnostic / YOLO built-in | yes, persistent read/write | pending |
| Simple display | simpledrm | available | yes, native panel desktop | pending |
| Internal NVMe | apple-nvme | **do not use** | known CQ-wrap/assert blocker | blocked |
| SMP | arm64 | **1 CPU only** | known CoW/MM corruption | blocked |
| USB-C host | xHCI/Type-C/SPMI | **do not auto-enable** | partial | blocked on safe VBUS/PD path |
| GPU acceleration | G16/AGX | no production path yet | not ready | blocked |
| Audio / camera | Apple audio / ISP | compile-only where applicable | incomplete | blocked |

The promotion rule is intentionally strict: a driver moves to “Gravity live
proof” only after a boot log plus a subsystem-specific smoke test on Mac16,8.
