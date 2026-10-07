# J614s PCIe/DART-thin bring-up

Purpose: test the T6040 PCIe host bridge and its two measured DART IOMMUs
without powering or enumerating any downstream J614s endpoint.

This image is intentionally a step after SMP-THIN. It keeps the 14-CPU M4
safety arguments (`idle=nop`, `arm64.nowfxt`) and adds only:

- AP pinctrl required by the PCIe controller;
- `pcie0_dart_0`;
- `pcie0_dart_1`;
- the `pcie0` root complex.

The four PCIe port nodes remain disabled. In particular there are no
`pwren-gpios`, so this image does not drive J614s gP13 or gP19 and therefore
does not power the BCM4388 Wi-Fi/BT module or GL9755 SD reader.

## Why this split matters

Asahi reported in August 2026 that M4 PCIe had reached Linux bus enumeration,
but T604x PCIe/DART remain development territory in the public feature matrix.
Earlier J614s experiments also showed that endpoint power-up can materially
change high-core-count behavior. Root-complex/DART qualification therefore
must be separate from endpoint qualification.

## Source admission requirements

Before this image may compile:

- the dedicated DTS must explicitly keep port00-port03 disabled;
- it must contain no endpoint power GPIOs or PCI endpoint compatible strings;
- the kernel profile must enable PCIe/DART/pinctrl but disable SMC, Wi-Fi,
  Bluetooth, MMC, NVMe and USB;
- the patched m1n1 source must retain the target-DT gate that leaves T6040 PCIe
  untouched when the target DT disables it;
- the dedicated DTB target must be listed in the Apple DT Makefile.

`tools/j614s/pcie-dart-audit.sh` enforces these invariants.

## Hardware success criteria

After the RAM-only shell appears:

1. all expected CPUs remain online with no kernel Oops/Internal error;
2. the Apple DART instances bind without translation faults;
3. the Apple PCIe host controller binds and creates the root bus;
4. no downstream endpoint appears because all port nodes are disabled;
5. no SMC, BCM4388, Bluetooth or SD driver is present;
6. repeated `j614s-diag pcie` and `dmesg` inspection show no new fault.

A pass admits the PCIe/DART foundation only. It does not admit Wi-Fi, Bluetooth,
SD, NVMe or any other endpoint.
