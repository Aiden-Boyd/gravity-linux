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


## Verified J614s / T6040 hardware inventory

We now have a pinned, machine-readable evidence packet at
`tools/j614s/t6040-gpu-evidence.json`. Its primary source is the public
Wallace J614s ADT capture/reduction at commit
`55f116dd0e0f28d1412c6be728a101f7d861c473`; the captured ADT SHA-256 is
`7a92e6e4d16cb1b5a5858beb22b22acc8e5ed4b36ed5d5ccde9b251f1da55c84`.

Proven facts, kept as raw inventory rather than a speculative Linux node:

- `/arm-io/sgx` is `gpu,t6040`.
- SGX exposes two raw ADT bus ranges:
  `0x88000000/0x03758000` and `0x88d00000/0x0016c000`.
  J614s `/arm-io/ranges` adds `0x200000000`, so their CPU-physical
  candidates are `0x288000000` and `0x288d00000` respectively.
- SGX carries IRQs `1481, 1482, 1483, 1484, 1505, 1507, 1496, 1498`.
- `/arm-io/gfx-asc` is `iop,ascwrap-v6`.
- gfx-asc exposes two raw ADT bus ranges:
  `0x8a600000/0x00088000` and `0x8a050000/0x00060000`.
  After the same `+0x200000000` translation, the CPU-physical candidates
  are `0x28a600000` and `0x28a050000`.
- gfx-asc's raw ADT IRQ order is `1502, 1501, 1504, 1503`. The J614s ASC
  convention strongly derives the Linux mailbox semantic order as
  `1501, 1502, 1503, 1504`, but that remains explicitly marked
  `derived-not-driver-endorsed` until a T6040 driver contract exists.
- SGX advertises 16 performance states across 2 tables and
  `gpu-num-perf-states = 15`.
- Six GPU/RTKit reserved regions are inventoried in the JSON packet.
- The ADT-generated PMGR description already present in this tree gives
  `gpx@0` and `afr@0x100` as always-on domains and `gfx@0x110` as a child
  of `afr`.

The macOS 26.5.2 (25F84) evidence identifies the firmware generation as G16
(`AGXFirmwareKextG16RTBuddy`, `AGXG16X`) with
`RTKit-1558.40.16.release`.

### What is intentionally still unresolved

The raw ADT has **two SGX ranges and two gfx-asc ranges** (with the Linux
CPU-physical translations recorded separately), while the current downstream
G13/G14 Linux driver consumes named `sgx` and `asc` resources.
We will not guess which T6040 ranges should be collapsed, split, or exposed.
That mapping belongs to an explicit G16 driver contract.

Likewise, the six ADT reserved regions are evidence, not proof that the G14
`ttbs/pagetables/handoff/hw-cal-a/hw-cal-b/globals` layout is valid for G16.
m1n1's current GPU handoff code has no T6040 case and must learn the G16
calibration/UAT ABI before Linux probing is allowed.

## Read-only ADT verification

`tools/j614s/m1n1/collect-gpu-adt.py` can independently re-collect the GPU
inventory from a captured ADT or from a tethered m1n1 proxy. It deliberately
does not import `m1n1.setup`, power the GPU, access GPU/ASC MMIO, or start
firmware.

Offline:

```sh
python3 tools/j614s/m1n1/collect-gpu-adt.py \
  --m1n1 /path/to/m1n1 \
  --adt /path/to/j614s.adt \
  -o j614s-t6040-gpu-adt.json
```

Tethered read-only inventory:

```sh
python3 tools/j614s/m1n1/collect-gpu-adt.py \
  --m1n1 /path/to/m1n1 \
  --live \
  -o j614s-t6040-gpu-adt.json
```

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
