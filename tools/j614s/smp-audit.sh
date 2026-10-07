#!/bin/sh
# SPDX-License-Identifier: MIT
# Static fail-closed audit for the J614s SMP-thin candidate.
set -eu

ROOT=${1:-.}
cd "$ROOT"

fail()
{
    echo "ERROR: $*" >&2
    exit 1
}

grep -q 'safe|smp-thin)' tools/j614s/ramboot-config.sh ||
    fail "smp-thin is no longer tied to the minimal hardware profile"
grep -q 'enable CONFIG_SMP' tools/j614s/ramboot-config.sh ||
    fail "CONFIG_SMP is not explicitly enabled"

for sym in     CONFIG_NVME_APPLE CONFIG_BLK_DEV_NVME CONFIG_PCIE_APPLE CONFIG_APPLE_DART     CONFIG_MFD_MACSMC CONFIG_APPLE_DOCKCHANNEL CONFIG_HID_DOCKCHANNEL     CONFIG_BRCMFMAC CONFIG_WLAN CONFIG_BT CONFIG_MMC CONFIG_USB
do
    grep -q "disable $sym" tools/j614s/ramboot-config.sh ||
        fail "$sym is not disabled by the minimal profile"
done

grep -q 'broken_wfi = true' tools/j614s/m1n1/patch-v1.9.9-j614s.py ||
    fail "m1n1 broken-WFI feature is missing"
grep -q 'wfe_mode = true' tools/j614s/m1n1/patch-v1.9.9-j614s.py ||
    fail "m1n1 no longer forces WFE parking on broken-WFI SoCs"
grep -q 'refusing to disable WFE mode' tools/j614s/m1n1/patch-v1.9.9-j614s.py ||
    fail "m1n1 WFE fail-closed guard is missing"

grep -q 'maxcpus=14' .github/workflows/j614s-smp-thin.yml ||
    fail "SMP workflow no longer exposes 14 CPUs"
grep -q 'idle=nop' .github/workflows/j614s-smp-thin.yml ||
    fail "SMP workflow lost idle=nop"
grep -q 'arm64.nowfxt' .github/workflows/j614s-smp-thin.yml ||
    fail "SMP workflow lost arm64.nowfxt"

# The workflow must package the thin DT, not the all-hardware DT.
if grep -q 'cp arch/arm64/boot/dts/apple/t6040-j614s-all.dtb.*j614s-ramboot-smp-thin'     .github/workflows/j614s-smp-thin.yml; then
    fail "SMP-thin workflow packages the all-hardware DT"
fi

# Ensure the 14 active J614s CPUs plus the fused-off positional slot remain described.
python3 - <<'PY'
import re
text = open("arch/arm64/boot/dts/apple/t6040.dtsi").read()
active = re.findall(r"\bcpu_(?:e[0-3]|p(?:0[0-4]|1[0-4])):\s*cpu@", text)
assert len(active) == 14, f"expected 14 active CPU descriptions, got {len(active)}"
assert "cpu_p05_disabled: cpu@10105" in text
PY

echo "J614s SMP-thin audit passed."
