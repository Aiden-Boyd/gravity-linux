# J614s / T6040 internal NVMe bring-up

Status: **preparation only**. Gravity must not auto-probe, mount, repair, format,
or write the internal SSD from the normal J614s boot profiles.

## What is already known

The J614s ADT and later T6040 bring-up evidence establish the storage path:

- ANS ASC control: CPU PA `0x409600000 / 0x4000`
- ANS mailbox: CPU PA `0x409608000 / 0x4000`, IRQs 1530–1533 in Linux
  empty/not-empty semantic order
- SART v3: CPU PA `0x40dc50000 / 0xc000`
- CoastGuard SART power control: CPU PA `0x40dcc13e8`
- M4+ NVMMU aperture: reg[3], CPU PA `0x40dcc0000 / 0x60000`
- M4+ NVMe controller aperture: reg[9], CPU PA `0x44dcc0000`
- NVMe IRQ: 2583

The exact values and provenance are pinned in
`tools/j614s/t6040-nvme-evidence.json`.

## Why we are not adding a live NVMe DT node yet

Current Gravity already contains the M4-generation T8132 IO-queue additions in
`drivers/nvme/host/apple.c`, including `apple,t8132-nvme-ans2` and the
0x1200/0x1208/0x1210 IOQ setup.

T6040 evidence, however, distinguishes the reg[3] NVMMU aperture from the
reg[9] controller aperture. Gravity's current driver still consumes one named
`nvme` MMIO resource for both controller and NVMMU operations. Adding a
T6040 compatible or DT fallback merely to make probe run would hide that
contract mismatch.

There is also a later-runtime boundary: experimental Linux T6040 bring-up has
demonstrated ANS boot, namespace enumeration and GPT partition discovery, but
sustained I/O can hit ANS firmware assert 7454 at the first Linux I/O CQ wrap.
That makes the current state extremely useful for bring-up, but not acceptable
for a normal root filesystem.

## CoastGuard SART

This branch ports the reviewed T8140 CoastGuard primitive as an **unused
capability**:

- explicit power-managed compatible;
- active request = 0, inactive request = 1;
- 100 us settle delay with bounded readback polling;
- reference-counted power ownership;
- protected-entry scan deferred until the first allow-list operation;
- no probe-time CoastGuard MMIO on the power-managed variant.

The source behavior is adapted from the public Wallace T8140 SART patches.
The existing SART file remains dual MIT/GPL; the imported deltas retain the
same compatible licensing context.

## Hardware test stages

A future T6040 driver/DT candidate must remain separate from the normal boot
DT and move through these stages:

1. **N0 — static only:** DT schema/build and exact resource-contract review.
2. **N1 — mailbox/SART prerequisites:** no NVMe controller probe or namespace.
3. **N2 — controller identify:** controller/namespace metadata only; no mount.
4. **N3 — bounded read:** only after N2 logs are clean, use an explicitly
   reviewed single-LBA/read-only test.
5. **N4 — wrap discriminator:** reproduce or eliminate the known first-CQ-wrap
   failure before any filesystem workload.
6. **N5 — normal I/O:** only after the wrap boundary is resolved and recovery,
   teardown and repeated cold boots are proven.

At N0–N4, do not run `mkfs`, `wipefs`, `parted`, `sfdisk`, `gdisk`,
`fsck`, a writable mount, or any write benchmark against the internal SSD.

## Current upstream m1n1 reference

Current m1n1 contains the M4-era ANS changes that were absent from the old
v1.9.9 bring-up loader, including separate M4 reg[3]/reg[9] handling and
additional IOQ register setup. Gravity's enrolled/first-boot stage1 remains
pinned separately; this branch does **not** silently replace it.

That separation is intentional: updating the bootloader and enabling the
internal SSD are two different risk decisions.
