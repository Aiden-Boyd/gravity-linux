#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

ROOT=${1:-.}
cd "$ROOT"

fail()
{
    echo "ERROR: $*" >&2
    exit 1
}

DTS=arch/arm64/boot/dts/apple/t6040-j614s-pcie-dart.dts
[ -f "$DTS" ] || fail "missing PCIe/DART thin DTS"

grep -q '^&pinctrl_ap {' "$DTS" || fail "pinctrl_ap not explicitly controlled"
grep -q '^&pcie0_dart_0 {' "$DTS" || fail "DART0 not explicitly controlled"
grep -q '^&pcie0_dart_1 {' "$DTS" || fail "DART1 not explicitly controlled"
grep -q '^&pcie0 {' "$DTS" || fail "PCIe root not explicitly controlled"

for node in port00 port01 port02 port03; do
    python3 - "$DTS" "$node" <<'PY'
import re, sys
path, node = sys.argv[1:]
text = open(path).read()
m = re.search(r"&" + re.escape(node) + r"\s*\{(.*?)\n\};", text, re.S)
assert m, f"missing explicit {node} override"
assert re.search(r'status\s*=\s*"disabled"', m.group(1)), f"{node} is not disabled"
PY
done

! grep -q 'pwren-gpios' "$DTS" || fail "thin PCIe DTS must not drive endpoint power GPIOs"
! grep -q '&smc' "$DTS" || fail "thin PCIe DTS must not enable SMC"
! grep -q 'pci14e4' "$DTS" || fail "thin PCIe DTS must not describe BCM4388 endpoints"
! grep -q 'pci17a0' "$DTS" || fail "thin PCIe DTS must not describe SD endpoint"

CFG=tools/j614s/ramboot-config.sh
grep -q 'pcie-dart-thin)' "$CFG" || fail "missing pcie-dart-thin config case"
for sym in CONFIG_PINCTRL_APPLE_GPIO CONFIG_APPLE_DART CONFIG_PCIE_APPLE; do
    grep -q "enable $sym" "$CFG" || fail "$sym is not enabled"
done
for sym in CONFIG_MFD_MACSMC CONFIG_BRCMFMAC CONFIG_BT CONFIG_MMC CONFIG_NVME_APPLE CONFIG_USB; do
    grep -q "disable $sym" "$CFG" || fail "$sym is not disabled"
done

echo "J614s PCIe/DART-thin source audit passed."
