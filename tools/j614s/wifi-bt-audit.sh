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

DTS=arch/arm64/boot/dts/apple/t6040-j614s-wifi-bt.dts
[ -f "$DTS" ] || fail "missing Wi-Fi/BT isolated DTS"

grep -q '#include "t6040-j614s-smc.dts"' "$DTS" ||
    fail "Wi-Fi/BT profile must build cumulatively on SMC-thin"

grep -q 'pwren-gpios = <&smc_gpio 0x13 GPIO_ACTIVE_HIGH>' "$DTS" ||
    fail "measured gP13 Wi-Fi/BT power GPIO missing"
! grep -q '0x19 GPIO_ACTIVE_HIGH' "$DTS" ||
    fail "Wi-Fi/BT profile must not drive SD gP19"
grep -q 'compatible = "pci14e4,4434"' "$DTS" ||
    fail "BCM4388 Wi-Fi function missing"
grep -q 'compatible = "pci14e4,5f72"' "$DTS" ||
    fail "BCM4388 Bluetooth function missing"
! grep -q 'pci17a0,9755' "$DTS" ||
    fail "Wi-Fi/BT profile must not expose the SD endpoint"

python3 - "$DTS" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
def state(node):
    m = re.search(r"&" + re.escape(node) + r"\s*\{(.*?)\n\};", text, re.S)
    assert m, f"missing {node}"
    s = re.search(r'status\s*=\s*"([^"]+)"', m.group(1))
    assert s, f"missing status for {node}"
    return s.group(1)
assert state("port00") == "okay"
for node in ("port01", "port02", "port03"):
    assert state(node) == "disabled", f"{node} must remain disabled"
assert state("smc_gpio") == "okay"
PY

CFG=tools/j614s/ramboot-config.sh
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^wifi-bt\)\n(.*?)^\s*;;", text)
assert m, "missing wifi-bt config case"
block = m.group(1)
for sym in (
    "CONFIG_GPIO_MACSMC", "CONFIG_RFKILL", "CONFIG_CFG80211",
    "CONFIG_BT", "CONFIG_BRCMFMAC_PCIE",
):
    assert f"enable {sym}" in block, f"{sym} is not enabled"
for sym in ("CONFIG_BRCMFMAC", "CONFIG_BT_HCIBCM4377"):
    assert f"module {sym}" in block, f"{sym} must remain modular"
for sym in (
    "CONFIG_MMC", "CONFIG_NVME_APPLE", "CONFIG_USB",
    "CONFIG_MACSMC_POWER", "CONFIG_SENSORS_MACSMC_HWMON",
    "CONFIG_INPUT_MACSMC_INPUT", "CONFIG_RTC_DRV_MACSMC",
):
    assert f"disable {sym}" in block, f"{sym} is not disabled"
PY

grep -q 't6040-j614s-wifi-bt.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "Wi-Fi/BT DTB not listed in Apple DT Makefile"

echo "J614s Wi-Fi/BT isolated source audit passed."
