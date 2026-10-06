# M4 Pro / J614s / T6040 known blockers

This file tracks distinct platform problems relevant to Mac16,8/J614s rather
than every experiment ticket. It is a bring-up ledger, not a support promise.

## First-boot safety

- **WFI/WFIT state loss:** M4 bare-metal Linux must avoid the affected idle
  instructions. Current bundles require `idle=nop arm64.nowfxt`.
- **SMP reliability:** Project Wallace reproduces a multi-core page-copy/MM
  failure on this exact model. Current Gravity J614s bundles force one CPU.
- **m1n1 generation:** use signed m1n1 v1.9.9, commit
  `809541515659bf4e504807fd72bc0a539be5eee7`; v1.6.1 predates important M4
  SMP/cache, WFI/WFIT, MCC, NVMe and USB-C work.
- **Storage isolation:** SAFE keeps NVMe, PCIe, DART, SMC, DockChannel HID,
  Wi-Fi, MMC and USB disabled and supplies no persistent root filesystem.

## Exact-model hardware issues

- **Trackpad interface power:** J614s MTP rejects the old 4-byte command-0x40
  request. Project Wallace ticket 230 proved the 9-byte v2 will-change /
  has-changed form and live touch+haptics. The driver in this branch carries
  that protocol fix; Apple firmware is not redistributed here.
- **Internal NVMe:** exact-model testing reaches media, but Linux can trigger
  an ANS firmware assert around the first I/O completion-queue wrap. A separate
  dead-controller teardown/UAF path has also been observed. Keep ANS disabled
  for first boot.
- **USB host:** USB2 data-path work exists externally, but Type-C/VBUS/SPMI
  ownership remains experimental on J614s. Keep USB disabled for first boot.
- **GPU/display acceleration:** simple framebuffer use is distinct from G16
  acceleration. Do not substitute older G14 tables.
- **Power management:** cpuidle, suspend/retention, lid integration and
  production thermal policy are not considered complete.
- **Multimedia:** audio and camera/ISP remain unfinished.

## Already handled in this tree

- ARM64 `idle=nop` parser/back-end exists.
- ARM64 `arm64.nowfxt` ID-register override exists.
- Apple cpufreq kHz-to-Hz conversion uses `1000UL`, avoiding the M4 Pro
  >4.294 GHz 32-bit overflow.
- J614s MTP helper/DockChannel topology and the SMC GPIO dependency are
  represented in the reviewed diagnostic DT.
- Panic policy is `panic=0` for bring-up so failures remain visible.

## Provenance

- AsahiLinux/m1n1 v1.9.9 release and merged M4 work, especially PRs 536, 578,
  593, 597, 633, 652, 657, 659, 672, 680, 682 and 692.
- damsleth/wallace (Project Wallace), exact Mac16,8/J614s/T6040 hardware
  evidence, especially tickets 205 (SMP), 206/227 (NVMe), 230 (trackpad),
  108/231/305 (USB/PD), and cpufreq ticket 006.
- Trackpad protocol adaptation is based on CJ Damsleth's GPL kernel patch
  `t6040-dockchannel-hid-reset-contract.patch`.

## Hardened after initial audit

- **AIC locked EL2 registers:** T6040 AICv3 now has an explicit quirk that
  avoids all driver accesses to the firmware-locked guest-timer FIQ control
  and ICH_HCR_EL2 registers. This extends the Project Wallace bring-up patch
  from only the init writes to the later IRQ/FIQ mask/handler paths as well.
- **MTP ASC mailbox interrupt order:** corrected to the exact J614s ADT order
  `793, 792, 795, 794` (non-empty interrupt first in each ASC pair).
- **DockChannel HID robustness:** invalid interface indices are rejected before
  indexing, zero-length events are dropped, malformed packet work is freed,
  and `starting` is cleared on ready and timeout so a failed start can retry.
