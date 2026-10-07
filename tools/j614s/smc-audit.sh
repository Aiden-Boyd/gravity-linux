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

DTS=arch/arm64/boot/dts/apple/t6040-j614s-smc.dts
[ -f "$DTS" ] || fail "missing SMC-thin DTS"

grep -q '#include "t6040-j614s-pcie-dart.dts"' "$DTS" ||
    fail "SMC-thin must build cumulatively on PCIe/DART-thin"

python3 - "$DTS" <<'PY'
import re, sys
text = open(sys.argv[1]).read()

def state(node):
    m = re.search(r"&" + re.escape(node) + r"\s*\{(.*?)\n\};", text, re.S)
    assert m, f"missing explicit {node} override"
    s = re.search(r'status\s*=\s*"([^"]+)"', m.group(1))
    assert s, f"missing status for {node}"
    return s.group(1)

assert state("smc_mbox") == "okay"
assert state("smc") == "okay"
assert state("smc_gpio") == "disabled"
assert state("smc_hwmon") == "disabled"
PY

! grep -q 'pwren-gpios' "$DTS" || fail "SMC-thin must not drive endpoint power"
! grep -q 'pci14e4' "$DTS" || fail "SMC-thin must not add BCM4388 endpoint"
! grep -q 'pci17a0' "$DTS" || fail "SMC-thin must not add SD endpoint"

CFG=tools/j614s/ramboot-config.sh
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^smc-thin\)\n(.*?)^\s*;;", text)
assert m, "missing smc-thin config case"
block = m.group(1)

for sym in (
    "CONFIG_APPLE_MAILBOX", "CONFIG_APPLE_RTKIT", "CONFIG_MFD_MACSMC",
    "CONFIG_PINCTRL_APPLE_GPIO", "CONFIG_APPLE_DART", "CONFIG_PCIE_APPLE",
):
    assert f"enable {sym}" in block, f"{sym} is not enabled in smc-thin"

for sym in (
    "CONFIG_GPIO_MACSMC", "CONFIG_SENSORS_MACSMC_HWMON",
    "CONFIG_MACSMC_POWER", "CONFIG_INPUT_MACSMC_INPUT",
    "CONFIG_RTC_DRV_MACSMC", "CONFIG_POWER_RESET_MACSMC",
    "CONFIG_BRCMFMAC", "CONFIG_BT", "CONFIG_MMC", "CONFIG_NVME_APPLE",
    "CONFIG_USB",
):
    assert f"disable {sym}" in block, f"{sym} is not disabled in smc-thin"
PY

grep -q 't6040-j614s-smc.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "SMC-thin DTB not listed in Apple DT Makefile"

echo "J614s SMC-thin source audit passed."
