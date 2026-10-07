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
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^pcie-dart-thin\)\n(.*?)^\s*;;", text)
assert m, "missing pcie-dart-thin config case"
block = m.group(1)
for sym in ("CONFIG_PINCTRL_APPLE_GPIO", "CONFIG_APPLE_DART", "CONFIG_PCIE_APPLE"):
    assert f"enable {sym}" in block, f"{sym} is not enabled in pcie-dart-thin"
for sym in ("CONFIG_MFD_MACSMC", "CONFIG_BRCMFMAC", "CONFIG_BT",
            "CONFIG_MMC", "CONFIG_NVME_APPLE", "CONFIG_USB"):
    assert f"disable {sym}" in block, f"{sym} is not disabled in pcie-dart-thin"
PY

grep -q 't6040_pcie_requested' tools/j614s/m1n1/patch-v1.9.9-j614s.py ||
    fail "stage1 target-DT PCIe gate missing"
grep -q 't6040-j614s-pcie-dart.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "PCIe/DART thin DTB not listed in Apple DT Makefile"

echo "J614s PCIe/DART-thin source audit passed."
