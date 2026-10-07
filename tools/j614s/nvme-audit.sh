#!/bin/sh
# SPDX-License-Identifier: MIT
# Fail-closed J614s/T6040 internal-NVMe preparation audit.
set -eu

ROOT=${1:-.}
ALLOW=${J614S_ALLOW_EXPERIMENTAL_NVME:-0}
cd "$ROOT"

fail()
{
    echo "ERROR: $*" >&2
    exit 1
}

test -f tools/j614s/t6040-nvme-evidence.json ||
    fail "missing T6040 NVMe evidence packet"

grep -q 'APPLE_ANS_T8132_IOQ_CMDS' drivers/nvme/host/apple.c ||
    fail "missing T8132 IOQ register support"
grep -q 'needs_ioq_register' drivers/nvme/host/apple.c ||
    fail "missing M4 IOQ setup gate"
grep -q 'apple,t8132-nvme-ans2' drivers/nvme/host/apple.c ||
    fail "missing T8132 ANS2 compatible"

grep -q 'apple,t8140-sart' drivers/soc/apple/sart.c ||
    fail "missing T8140 CoastGuard SART support"
grep -q 'sart_scan_entries' drivers/soc/apple/sart.c ||
    fail "missing deferred SART protected-entry scan"

if grep -RqsE 'apple,t6040-nvme-ans2|nvme@44dcc0000|ans_nvme:'     arch/arm64/boot/dts/apple/t6040*.dts     arch/arm64/boot/dts/apple/t6040*.dtsi 2>/dev/null; then
    [ "$ALLOW" = 1 ] ||
        fail "T6040 NVMe DT node appeared without explicit experimental override"
fi

if [ -f .config ] && grep -q '^CONFIG_NVME_APPLE=[ym]$' .config; then
    profile=${PROFILE:-unknown}
    [ "$profile" != safe ] ||
        fail "SAFE profile enabled CONFIG_NVME_APPLE"
fi

echo "J614s NVMe audit passed: M4/CoastGuard prep present; internal SSD probing remains gated."
