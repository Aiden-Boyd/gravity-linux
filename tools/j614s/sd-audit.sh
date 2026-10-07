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

DTS=arch/arm64/boot/dts/apple/t6040-j614s-sd.dts
[ -f "$DTS" ] || fail "missing SD isolated DTS"
grep -q '#include "t6040-j614s-smc.dts"' "$DTS" ||
    fail "SD profile must build cumulatively on SMC-thin"
grep -q 'pwren-gpios = <&smc_gpio 0x19 GPIO_ACTIVE_HIGH>' "$DTS" ||
    fail "measured gP19 SD power GPIO missing"
! grep -q '0x13 GPIO_ACTIVE_HIGH' "$DTS" ||
    fail "SD profile must not drive Wi-Fi/BT gP13"
grep -q 'compatible = "pci17a0,9755"' "$DTS" ||
    fail "GL9755 endpoint missing"
! grep -q 'pci14e4' "$DTS" ||
    fail "SD profile must not expose BCM4388"

python3 - "$DTS" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
def state(node):
    m = re.search(r"&" + re.escape(node) + r"\s*\{(.*?)\n\};", text, re.S)
    assert m, f"missing {node}"
    s = re.search(r'status\s*=\s*"([^"]+)"', m.group(1))
    assert s, f"missing status for {node}"
    return s.group(1)
assert state("port01") == "okay"
for node in ("port00", "port02", "port03"):
    assert state(node) == "disabled"
assert state("smc_gpio") == "okay"
PY

CFG=tools/j614s/ramboot-config.sh
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^sd-thin\)\n(.*?)^\s*;;", text)
assert m, "missing sd-thin config case"
block = m.group(1)
for sym in ("CONFIG_GPIO_MACSMC", "CONFIG_MMC", "CONFIG_MMC_SDHCI"):
    assert f"enable {sym}" in block, f"{sym} is not enabled"
assert "module CONFIG_MMC_SDHCI_PCI" in block, "SD PCI driver must remain modular"
for sym in (
    "CONFIG_BRCMFMAC", "CONFIG_BT", "CONFIG_NVME_APPLE", "CONFIG_USB",
    "CONFIG_MACSMC_POWER", "CONFIG_SENSORS_MACSMC_HWMON",
    "CONFIG_INPUT_MACSMC_INPUT", "CONFIG_RTC_DRV_MACSMC",
):
    assert f"disable {sym}" in block, f"{sym} is not disabled"
PY

grep -q 't6040-j614s-sd.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "SD DTB not listed in Apple DT Makefile"

echo "J614s SD isolated source audit passed."
