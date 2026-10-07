# M4 Pro / J614s / T6040 known blockers

This file tracks distinct platform problems relevant to Mac16,8/J614s rather
than every experiment ticket. It is a bring-up ledger, not a support promise.

## First-boot safety

- **WFI/WFIT state loss:** M4 bare-metal Linux must avoid the affected idle
  instructions. Current bundles require `idle=nop arm64.nowfxt`.
- **SMP reliability:** Project Wallace reproduces a multi-core page-copy/MM
  failure on this exact model. Current Gravity J614s bundles force one CPU.
- **m1n1 generation:** the target stage-1 is `v1.9.9-j614s.1`, based on
  upstream v1.9.9 commit `809541515659bf4e504807fd72bc0a539be5eee7` plus
  only the reviewed exact-model T6040 hardening deltas.
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
- BCM4388 scan parsing accepts Apple firmware's hardware-proven BSS-info v116.
- Diagnostic/YOLO profiles explicitly build the BCM4388 PCIe Bluetooth HCI
  driver and Apple cpufreq driver; YOLO promotes RFKILL before Bluetooth so
  Kconfig cannot silently demote Bluetooth to a module.
- J614s input profiles explicitly build hid-apple plus hid-magicmouse and
  hid-multitouch. The MTP trackpad is a BUS_HOST Apple HID device and is
  handled by hid-magicmouse, not by hid-multitouch alone.
- SMC diagnostic profiles include lid/power-button input, battery/AC telemetry
  and hwmon sensors; the reset/RTC/SPMI path remains separately gated until
  the exact J614s NVMEM cell description is reviewed.
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
- **MTP ASC mailbox interrupt mapping:** the J614s ADT stores the four lines as
  `793, 792, 795, 794` (not-empty first in each pair), but the Linux mailbox
  binding names them `send-empty, send-not-empty, recv-empty, recv-not-empty`.
  The DTS therefore uses the hardware-proven semantic order
  `792, 793, 794, 795`; keeping raw ADT order loses the MTP hello interrupt.
- **DockChannel HID robustness:** invalid interface indices are rejected before
  indexing, zero-length events are dropped, malformed packet work is freed,
  and `starting` is cleared on ready and timeout so a failed start can retry.

## Driver hardening queue

The RAM diagnostic image now includes `j614s-diag`, a staged helper that
loads only the requested subsystem and prints a compact state/log snapshot.
It never has an "all" mode: PCIe, SD, Wi-Fi, Bluetooth and input remain
separate experiments so a failure can be attributed to the last step.

- **DockChannel receive re-arm:** header-read/allocation failures now return
  through the common re-arm path so one transient error cannot silently stop
  keyboard/trackpad RX.
- **DockChannel parser bounds:** report/ACK subheaders are length-checked before
  field access; zero-length raw HID requests and INIT product names are rejected
  safely; fixed-width interface names are copied into a NUL-terminated buffer.
- **DockChannel retry state:** asynchronous interface creation clears
  `creating` on all exits and reports a failed queue operation as `-EBUSY`.
- **DockChannel module teardown:** the deliberate `BUG_ON(1)` remove callback
  has been replaced with worker draining, HID-child destruction, and workqueue
  cleanup so diagnostic module unload cannot intentionally panic the kernel.
- **DockChannel lifetime/parser cleanup:** interface DT-node references and
  workqueues are released on failure/removal, failed packet queueing frees its
  work item, zero-sized commands are rejected before report-ID access, and
  GPIO init blocks are bounded by the block length with a fixed-width name copy.
- **cpufreq DT lifetime:** the performance-domain node reference is retained
  through `of_iomap()` and released only after the mapping attempt.
- **m1n1 stage1 provenance:** fixed. CI rebuilds the J614s-hardened v1.9.9
  source twice byte-identically with `RELEASE=1 CHAINLOADING=1`, GCC cross
  tools and Rust/Cargo 1.98.1, then compares it to the immutable binary at
  commit `a853472376b58b794637b43a9f34dc1ae76a7daa`. The installer verifies SHA-256
  `40e9510d539fb539f09c1b944ab3d1c23f2d7f8ed604e1c200bedf5564249499` and never substitutes the upstream stage2 release.


## Pinned M4 Pro stage-1 hardening

The pinned reproducible m1n1 stage-1 is built from upstream v1.9.9
commit `809541515659bf4e504807fd72bc0a539be5eee7` plus only the exact-model
J614s/T6040 fixes adapted from Project Wallace:

- force M4 secondaries into WFE before their first parking loop and refuse a
  later fallback to state-losing WFI;
- on T6040 initialize only the required `dart-mtp` DAPF and skip AOP/PMP/ISP
  filters which produced asynchronous L2C access-fault SErrors;
- leave a 16 KiB guard page above the m1n1 stage-2 log ring;
- support the T6041 MCC layout used by T6040 with one cache plane per AMCC and
  the hardware-verified 0x00010101 cache-status pattern;
- enable only the conservative T6040 cpufreq path around CLUSTER_PSTATE, never
  the T6030 throttle offsets which fault on T6040 P-clusters.

The Linux PMGR driver also preserves firmware-active T6041 raw-boot domains
and suppresses AUTO_ENABLE on `dispext0_cpu` and `dispext1_cpu`.
The exact stage-1 is pinned at commit `a853472376b58b794637b43a9f34dc1ae76a7daa`, SHA-256 `40e9510d539fb539f09c1b944ab3d1c23f2d7f8ed604e1c200bedf5564249499`.

<!-- Patched stage-1 verification trigger: 2026-10-06 -->
