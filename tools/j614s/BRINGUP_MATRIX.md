# J614s qualified bring-up image matrix

The rule is simple: **source first, artifact second**.

No test image is allowed into the build matrix from a moving branch head. Every
buildable profile is pinned to a full Git commit SHA in
`tools/j614s/bringup-images.json`. CI checks out that exact commit, runs
`source_qualify.py`, uploads a qualification record, and only then starts the
compiler. The build job verifies the qualification record and source SHA again
before invoking `build_qualified_image.sh`.

Changing any source commit in the manifest therefore requires a fresh source
qualification before a replacement image can exist.

## Planned boot order

| Order | Image | Current source state | Purpose |
|---:|---|---|---|
| 10 | SAFE | build-enabled | one-CPU UART/RAM baseline |
| 20 | SMP-THIN | build-enabled | isolated 14-CPU CPU/memory/interrupt test |
| 30 | PCIe-DART-THIN | blocked | PCIe + IOMMU without endpoint power |
| 40 | SMC-THIN | blocked | SMC/RTKit without endpoint consumers |
| 50 | WIFI-BT | blocked | BCM4388/gP13 path |
| 60 | SD | blocked | GL9755/gP19 path |
| 70 | NVME-READONLY | prep branch exists; build blocked | ANS/SART/NVMe bounded diagnostics |
| 80 | INPUT | blocked | MTP/DockChannel keyboard + trackpad |
| 90 | POWER | blocked | battery/sensors/lid/RTC/cpufreq |
| 100 | FULL-DIAGNOSTIC | build-enabled | manual module-by-module integration |
| 110 | FULL-YOLO | build-enabled | one-CPU automatic integration probe |
| 120 | GPU-NATIVE | prep branch exists; build blocked | future G16 acceleration |

A build-enabled state means only that the **source is eligible for
qualification and compilation**. It does not mean the image passed hardware
testing. Hardware pass/fail remains a separate admission step.

## What source qualification checks

Before compilation, the qualification gate verifies at minimum:

- checkout SHA exactly matches the immutable manifest SHA;
- source checkout is clean;
- custom shell/Python tooling parses;
- expected Linux 7.1 source baseline is present;
- M4 broken-WFI/WFE safety markers remain in the m1n1 patch source;
- T6040 AIC and CPU topology source markers remain intact;
- RAM init code automatically mounts only pseudo filesystems and contains no
  internal block-device paths;
- SAFE keeps hardware-facing fabric disabled;
- SMP-THIN remains tied to the minimal profile and keeps the known endpoint
  confounders disabled;
- FULL-DIAGNOSTIC keeps reviewed hardware drivers modular;
- FULL-YOLO contains the intended built-in driver requests;
- no admitted build silently grows native T6040 GPU or NVMe nodes while those
  hardware contracts remain gated.

SMP-THIN also runs its own `smp-audit.sh` during qualification.

## Artifact provenance

Every built bundle contains:

- `SOURCE_COMMIT.txt`
- `SOURCE_QUALIFICATION.json`
- `BRINGUP_IMAGE_MATRIX.json`
- `TEST_ORDER.json`
- `kernel.config`
- `BOOTARGS.txt`
- `SHA256SUMS`

That makes it possible to trace a hardware result back to exactly which source
was reviewed and compiled.

## Upstream caution

Asahi's public M4 Pro/Max feature table still lists much of T604x bring-up as
WIP or TBA. The matrix therefore treats local experimental success as evidence
for this J614s bring-up only; it does not relabel unsupported upstream features
as generally supported.
