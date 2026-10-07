# J614s / T6040 GPU bring-up

Status: preparation only. Native GPU acceleration is intentionally **not enabled** on J614s yet.

## Why

The J614s MacBook Pro uses an M4 Pro (T6040-family) GPU. As of October 2026,
Asahi's public M4 support matrix lists GPU support for M4 / M4 Pro / M4 Max as
TBA. The downstream Asahi GPU kernel driver is also still in the process of
being upstreamed and is not present in this Linux 7.1.13 tree.

References:

- https://asahilinux.org/docs/platform/feature-support/m4/
- https://asahilinux.org/2026/02/progress-report-6-19/

M1/M2 AGX support must not be assumed to be register-, firmware-, command
stream-, or power-management-compatible with T6040.

## What is safe today

The J614s RAM-boot profiles may use the boot framebuffer / simpledrm path for
early display output. That does not initialize the native GPU.

The `tools/j614s/gpu-audit.sh` guard checks that we have not accidentally:

- enabled `CONFIG_DRM_ASAHI` for J614s;
- added a T6040 GPU DT node before the hardware description is reviewed; or
- mistaken the presence of an Asahi DRM source tree for actual T6040 support.

## Bring-up order once T6040 GPU work exists

1. Import or rebase the reviewed Asahi DRM driver and its required Rust/DRM
   abstractions onto the exact Gravity kernel base.
2. Confirm the driver explicitly recognizes the T6040 GPU generation. Do not
   add a compatible string merely to make probe run.
3. Derive the J614s GPU DT description from hardware evidence / upstream Asahi
   work: MMIO ranges, IRQs, DART/IOMMU links, power domains, clocks, firmware
   channels and reserved memory.
4. Keep the driver disabled in `safe`.
5. Build it as a module in `diagnostic`, load it manually, and capture the
   complete serial log before enabling automatic probing.
6. Only after clean firmware/RTKit initialization and memory-management tests,
   allow built-in probing in `yolo`.
7. Then pair the kernel UAPI with matching Mesa Asahi/Honeykrisp userspace and
   validate OpenGL/Vulkan, suspend/resume, thermal behavior and fault recovery.

## Experimental override

For a deliberate developer experiment only, the audit guard can be bypassed
with:

```
J614S_ALLOW_EXPERIMENTAL_GPU=1 sh tools/j614s/gpu-audit.sh
```

That override only disables the repository safety check. It does not make
T6040 GPU support functional or safe.
