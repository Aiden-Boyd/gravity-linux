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

DTS=arch/arm64/boot/dts/apple/t6040-j614s-input.dts
[ -f "$DTS" ] || fail "missing input-thin DTS"
grep -q '#include "t6040-j614s.dts"' "$DTS" ||
    fail "input-thin must start from the minimal J614s DT"

python3 - "$DTS" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
for node in ("mtp_mbox", "mtp_dart", "mtp", "mtp_dockchannel", "mtp_hid"):
    m = re.search(r"&" + re.escape(node) + r"\s*\{(.*?)\n\};", text, re.S)
    assert m, f"missing explicit {node} override"
    assert re.search(r'status\s*=\s*"okay"', m.group(1)), f"{node} not enabled"
PY

! grep -q '&pcie0' "$DTS" || fail "input-thin must not enable PCIe"
! grep -q '&smc' "$DTS" || fail "input-thin must not enable SMC"
! grep -q 'pwren-gpios' "$DTS" || fail "input-thin must not drive endpoint power"

CFG=tools/j614s/ramboot-config.sh
python3 - "$CFG" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"(?ms)^input-thin\)\n(.*?)^\s*;;", text)
assert m, "missing input-thin config case"
block = m.group(1)
for sym in (
    "CONFIG_MODULES", "CONFIG_INPUT", "CONFIG_HID_SUPPORT", "CONFIG_HID",
):
    assert f"enable {sym}" in block, f"{sym} is not enabled"
for sym in (
    "CONFIG_APPLE_MAILBOX", "CONFIG_APPLE_RTKIT", "CONFIG_APPLE_RTKIT_HELPER",
    "CONFIG_APPLE_DART", "CONFIG_APPLE_DOCKCHANNEL", "CONFIG_HID_DOCKCHANNEL",
    "CONFIG_HID_APPLE", "CONFIG_HID_MAGICMOUSE",
):
    assert f"module {sym}" in block, f"{sym} must remain modular"
for sym in (
    "CONFIG_PCIE_APPLE", "CONFIG_MFD_MACSMC", "CONFIG_BRCMFMAC",
    "CONFIG_BT", "CONFIG_MMC", "CONFIG_NVME_APPLE", "CONFIG_USB",
):
    assert f"disable {sym}" in block, f"{sym} is not disabled"
PY

grep -q 't6040-j614s-input.dtb' arch/arm64/boot/dts/apple/Makefile ||
    fail "input-thin DTB not listed in Apple DT Makefile"

echo "J614s input-thin source audit passed."
