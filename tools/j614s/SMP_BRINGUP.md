# J614s / T6040 SMP-thin bring-up

Status: **gated RAM-only diagnostic**.

This profile exists to separate CPU/SMP behavior from the platform devices
that complicated earlier J614s testing. It is not a daily-driver profile and
does not replace SAFE, DIAGNOSTIC, or YOLO.

## Proven CPU topology

Hardware evidence for Mac16,8 / J614s shows 14 active CPUs:

- 4 Sawtooth E cores: MPIDR 0x0..0x3
- 5 Everest P cores in cluster 1: MPIDR 0x10100..0x10104
- 5 Everest P cores in cluster 2: MPIDR 0x10200..0x10204

The T6040 die also has the positional cpu@10105 slot represented in the DT as
disabled. m1n1 uses that positional slot while reconciling ADT CPU numbering;
it must remain present but disabled.

Project Wallace demonstrated all 14 active cores entering Linux and completing
SMP bring-up. It also demonstrated real secondary execution with pinned tasks.

## Why this profile is thin

Later experiments showed that full-platform SMP results were heavily affected
by device power-up and endpoint activity. In particular, powering the BCM4388
Wi-Fi/BT module through the J614s gP13 path produced a deterministic high-core
boot failure in the tested tree. Separate multi-core memory/store faults were
also observed under heavier platform configurations.

Therefore SMP-thin deliberately uses the minimal t6040-j614s DTB and keeps
these blocks disabled:

- SMC and SMC GPIO consumers
- PCIe and Apple DART
- BCM4388 Wi-Fi/BT
- GL9755 SD
- internal NVMe
- USB
- DockChannel HID

The initramfs is RAM-only and contains no kernel driver modules.

## M4 CPU safety constraints

The current stage1 patch preserves the T6040 workaround for broken WFI
retention:

- M4 is marked broken_wfi.
- secondaries are parked in WFE instead of deep WFI.
- attempts to switch secondaries back to WFI are refused.

The Linux command line keeps:

- idle=nop
- arm64.nowfxt
- maxcpus=14

It intentionally does **not** use nr_cpus=1 or maxcpus=1.

## First hardware test

After the BusyBox shell appears:

    j614s-diag smp

Expected minimum success criteria:

1. Linux reports 14 possible/present CPUs.
2. /sys/devices/system/cpu/online reports 0-13.
3. dmesg shows 14 processors activated without an Internal error/Oops.
4. If BusyBox taskset is present, the diagnostic successfully runs a tiny
   pinned task on every online CPU.

A successful boot proves the isolated CPU/SMP path only. It does not prove that
the full platform is safe with 14 CPUs.

## Provenance

Primary retained evidence:

- damsleth/wallace at 55f116dd0e0f28d1412c6be728a101f7d861c473
- evidence/2026-07-10-t6040-smp-writeup.md
- evidence/2026-07-29-t6040-SMP-14-CORES-UP.md
- evidence/2026-08-03-t6040-205-smp-cow-investigation.md

Stage1 WFE workaround provenance is already documented in
tools/j614s/m1n1/patch-v1.9.9-j614s.py.
