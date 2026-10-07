#!/bin/sh
# SPDX-License-Identifier: MIT
# Audit J614s/T6040 GPU bring-up state without pretending unsupported hardware works.
set -eu

ROOT=${1:-.}
ALLOW=${J614S_ALLOW_EXPERIMENTAL_GPU:-0}

cd "$ROOT"

version="$(awk '
  /^VERSION =/ {v=$3}
  /^PATCHLEVEL =/ {p=$3}
  /^SUBLEVEL =/ {s=$3}
  END {printf "%s.%s.%s", v, p, s}
' Makefile)"

echo "J614s GPU audit (kernel $version)"

driver_dir=drivers/gpu/drm/asahi
has_driver=0
has_symbol=0
has_t6040_node=0

if [ -d "$driver_dir" ]; then
  has_driver=1
fi

if grep -RqsE 'config[[:space:]]+DRM_ASAHI|CONFIG_DRM_ASAHI' drivers/gpu/drm 2>/dev/null; then
  has_symbol=1
fi

if grep -RqsE '(^|[[:space:]])gpu@|apple,(agx|gpu)'     arch/arm64/boot/dts/apple/t6040*.dts     arch/arm64/boot/dts/apple/t6040*.dtsi 2>/dev/null; then
  has_t6040_node=1
fi

printf '  drm/asahi source: %s\n' "$has_driver"
printf '  DRM_ASAHI symbol: %s\n' "$has_symbol"
printf '  T6040 GPU DT node: %s\n' "$has_t6040_node"

if [ -f .config ] && grep -q '^CONFIG_DRM_ASAHI=[ym]$' .config 2>/dev/null; then
  echo "  CONFIG_DRM_ASAHI: enabled"
  if [ "$ALLOW" != 1 ]; then
    echo "ERROR: DRM_ASAHI is enabled for J614s without an explicit experimental override." >&2
    echo "T6040/M4 Pro GPU support is not yet a reviewed bring-up target in this tree." >&2
    exit 1
  fi
fi

if [ "$has_t6040_node" = 1 ] && [ "$ALLOW" != 1 ]; then
  echo "ERROR: a T6040 GPU device-tree node appeared without explicit experimental opt-in." >&2
  echo "Review MMIO, IRQs, DART, firmware/RTKit interfaces, power domains and GPU generation support first." >&2
  exit 1
fi

if [ "$has_driver" = 1 ] || [ "$has_symbol" = 1 ]; then
  echo "NOTE: an Asahi DRM implementation exists in this tree, but that alone does not imply T6040 support."
else
  echo "NOTE: no Asahi DRM kernel driver is present in this tree yet."
fi

echo "GPU audit passed: boot framebuffer/simpledrm may be used; native T6040 acceleration remains gated."
