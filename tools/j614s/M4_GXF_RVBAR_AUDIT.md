# J614s M4 Pro: pinned m1n1 GXF/RVBAR audit

Date: 2026-10-08
Upstream m1n1 pin: `809541515659bf4e504807fd72bc0a539be5eee7`
Gravity installed stage-1: `v1.9.9-j614s.4`; claimed source based on pin plus J614s deltas. This audit verifies the **upstream source at pin**; the downstream binary's exact provenance still depends on matching the patch/reproducible-build attestation.

## Result

**GXF fix is present in the pinned source.** `src/main.c` calls `gxf_init()` only behind `if (supports_gxf())`. `src/chickens.c` maps T6040/M4 Pro cores to `features_m4`, whose feature flags do not enable GXF. No additional unconditional `gxf_init` call was found in the inspected main path.

**RVBAR fix is present for secondary-core initiation in the pinned source.** `src/smp.c:smp_start_cpu()` writes RVBAR only when `cpu_features->apple_sysregs_unlocked` is true. `features_m4` does not set this flag. The separate boot-core path in `smp_start_secondaries()` checks RVBAR_LOCK before a write; do not generalize that every possible RVBAR write is eliminated. This is source verification only; no runtime execution traced.

**Consequences**: Reapplying the original M4 Mini GXF/RVBAR patches is unnecessary as a first action. The known iBoot panic could occur *before* these paths execute. Neither source-level fix establishes that the J614s image reaches m1n1.

## Exact upstream source links

- https://github.com/AsahiLinux/m1n1/blob/809541515659bf4e504807fd72bc0a539be5eee7/src/main.c
- https://github.com/AsahiLinux/m1n1/blob/809541515659bf4e504807fd72bc0a539be5eee7/src/chickens.c
- https://github.com/AsahiLinux/m1n1/blob/809541515659bf4e504807fd72bc0a539be5eee7/src/smp.c
- https://yuka.dev/blog-2026-10-02-linux-m4.html

## Next controlled physical boot

1. Keep installed Gravity stub and FUOS untouched.
2. If a separate macOS/Linux **host** is available, connect a USB-C **data** cable and start `tools/j614s/installer/watch_m1n1_usb.py` on host **before** choosing Gravity. USB node enumeration is not automatically a confirmed proxy connection; release stage-1 may not enter interactive proxy under default boot policy.
3. Select the existing Gravity startup option once, record time and any screen or host events.
4. Return to macOS, recover the *new* panic. Correlate its timestamp and signature with the attempt; no new panic plus successful proxy is strongest.
5. If another `:981` iBoot panic occurs, do **not** blame GXF/RVBAR or Linux MMU/WFI. Focus on FUOS loading and the earlier iBoot handoff using captured evidence.
6. If m1n1 USB appears, identify manufacturer and negotiate proxy with a version-matched proxyclient *before* attempting a RAM Linux boot.

No SIP changes, NVRAM modifications, installer reruns, iBoot patches, or FUOS padding are included in this plan.
