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

DTS=arch/arm64/boot/dts/apple/t6040-j614s-power.dts
[ -f "$DTS" ] || fail "missing power-thin DTS"
grep -q '#include "t6040-j614s-smc.dts"' "$DTS" ||
    fail "power-thin must build cumulatively on SMC-thin"
grep -q '^&smc_hwmon {' "$DTS" || fail "SMC hwmon child not explicitly controlled"
grep -q '4512000000' "$DTS" || fail "reviewed J614s P-core OPP ceiling missing"
grep -q 'cpufreq@210e20000' "$DTS" || fail "E-cluster cpufreq node missing"
grep -q 'cpufreq@211e20000' "$DTS" || fail "P0 cpufreq node missing"
grep -q 'cpufreq@212e20000' "$DTS" || fail "P1 cpufreq node missing"
! grep -q 'pwren-gpios' "$DTS" || fail "power-thin must not drive endpoint power"
! grep -q '&smc_gpio' "$DTS" || fail "power-thin must not enable SMC GPIO"

CFG=tools/j614s/ramboot-config.sh
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^power-thin\)\n(.*?)^\s*;;", text)
assert m, "missing power-thin config case"
block = m.group(1)
for sym in (
    "CONFIG_MODULES", "CONFIG_POWER_SUPPLY", "CONFIG_HWMON",
):
    assert f"enable {sym}" in block, f"{sym} is not enabled"
for sym in (
    "CONFIG_MACSMC_POWER", "CONFIG_SENSORS_MACSMC_HWMON",
    "CONFIG_INPUT_MACSMC_INPUT", "CONFIG_RTC_DRV_MACSMC",
    "CONFIG_ARM_APPLE_SOC_CPUFREQ",
):
    assert f"module {sym}" in block, f"{sym} must remain modular"
for sym in (
    "CONFIG_GPIO_MACSMC", "CONFIG_POWER_RESET_MACSMC", "CONFIG_BRCMFMAC",
    "CONFIG_BT", "CONFIG_MMC", "CONFIG_NVME_APPLE", "CONFIG_USB",
):
    assert f"disable {sym}" in block, f"{sym} is not disabled"
PY

grep -q 't6040-j614s-power.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "power-thin DTB not listed in Apple DT Makefile"

echo "J614s power-thin source audit passed."
