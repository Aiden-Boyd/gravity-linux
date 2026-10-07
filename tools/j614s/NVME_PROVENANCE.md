# J614s NVMe prep provenance

This file records the external technical sources used by
`j614s-nvme-prep-v1`. It is deliberately separate from proof that any
hardware-facing path is safe to enable.

## Asahi Linux

Repository: `AsahiLinux/linux`

Gravity already contained the Apple ANS driver changes for the M4-generation
T8132 path before this branch was created, including the extra IO-queue
register setup and `apple,t8132-nvme-ans2` match.

Relevant public development lineage:

- M4/T8132 ANS IOQ handling: Yureka Lilian's 2026 M4 NVMe work.
- Current Gravity file: `drivers/nvme/host/apple.c`, GPL-2.0.
- SART base driver: `drivers/soc/apple/sart.c`, dual MIT/GPL.

No Asahi NVMe driver source was copied into this branch by the NVMe-prep work;
the existing Gravity driver is audited and gated as-is.

## Asahi m1n1

Repository: `AsahiLinux/m1n1`
Pinned reference used for source-state comparison:
`2460b604c6f016956ead711823605eea840c602e`.

Relevant commits:

- `53f8ee9b54ba52b7f87e607e8206a8c827f06b04` — T8132/M4 NVMe
  resource and IOQ setup.
- `0e77db5bf051274362bdf18540caa0f258aaac66` — zero NVMMU TCB
  opcode.
- `b0cdce107543235c8a83c616a0d12aae4c5fc248` — command DMA
  direction.
- `1aead9e78af0096d4dd2203ae73ec10556c8b26e` — remove obsolete PRP
  null-check workaround.
- `34925643ca627a95b193b43632fae09e270b175e` — newer-firmware
  single-block read semantics.

m1n1 is reference evidence here. This branch does not replace Gravity's
enrolled v1.9.9 stage1.

## Project Wallace

Repository: `damsleth/wallace`
Pinned reference:
`55f116dd0e0f28d1412c6be728a101f7d861c473`.

Hardware/resource evidence:

- `evidence/2026-07-13-t6040-nvme-map.md`
- `evidence/2026-07-30-t6040-NVME-READ-WORKS.md`
- `evidence/2026-07-30-t6040-nvme-linux-wrap-assert-E1-E5.md`
- `evidence/2026-08-03-t6040-nvme-E11-tag2-review.md`
- `evidence/2026-08-03-t6040-nvme-ansf-assert-7454-re.md`
- `evidence/2026-08-03-t6040-nvme-irq-completion-order-audit.md`

CoastGuard SART implementation reference:

- `patches/t8140-sart-power-bindings.patch`
- `patches/t8140-sart-power-managed.patch`
- `patches/t8140-sart-defer-scan.patch`

The CoastGuard changes were adapted into Gravity's existing dual-MIT/GPL SART
driver and binding. No Apple binary, firmware image, or extracted kernelcache
is stored in Gravity.

## Policy

External evidence is used to establish addresses, IRQs, protocol behavior and
known failure boundaries. It is not permission to auto-enable an internal
storage node. Hardware-facing promotion requires an explicit reviewed
candidate and separate test decision.
