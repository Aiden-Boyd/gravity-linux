# J614s FUOS image audit — 2026-10-08

## Scope
Read-only analysis of two images from the user's mounted Gravity Preboot, against an independently reported recurring iBoot `3bdace14b1a9a68:981` SOCD panic. No disk, boot policy, SIP or IMG4 was modified. The physical image bytes were analyzed locally in the conversation, **not uploaded to this GitHub repo**.

## Files
- Normal `kernelcache`: 28,852,195 bytes; SHA-256 `d174b86394f74301280f559484ce52de78908f2dbbd074faff8ec1a236cc1d4b`.
- Gravity `kernelcache.custom.50AD5E77B497CE00881635BE3B95371E166183F5CD4C5D0624BD30B52CBEE2A575B69C2188FD136936B265CC593C1BD8`: 3,869,544 bytes; SHA-256 `2d513ff4d92539fc83957f3b3304f26dd44442e1d37bae3030634f7701fa53a1`. This reproduces the previously reported active Preboot SHA-256.

## Custom IMG4 facts verified against uploaded bytes
- Top-level DER parses as `IMG4`; `IM4P` type `fuos`, name `KernelManagement_executables-463.40.2`, followed by `IM4M` manifest.
- `IM4P` encoded sequence spans byte offsets `11..3866864` (3,866,853 bytes). SHA-384 `11927dab0d8be936593663b0f3e874f21f9336daa8d560bd55328fd5f436aa5f1f69ba4477681018553a0241999cd164` occurs in the `IM4M` manifest. This confirms the stored digest matches the IM4P bytes; it **does not** by itself cryptographically validate Apple's signature or boot authorization.
- Payload OCTET STRING begins at file offset `72`, length 3,866,628 (`0x3B0004`), consisting of an exact 3,866,624-byte pinned m1n1 binary followed by **four zero bytes**.
- Extracted 3,866,624-byte stage1 SHA-256: `29c9ac4542577e88e58734075d069835afac1a6b4db8b16b7aa7000942196411`, matching the pinned Gravity installer.
- `PAYP` contains `kcep=0x800` (entry offset 2048), `kclf=0x3B0004` (payload byte length), `kclo=0`, `kclz=0`, `kcrf=0`, `kcrz=0`, `kcwf=0`, `kcwz=0x3B0004`. The bytes at m1n1 payload offset `0x800` are AArch64 instructions (`f3 03 00 aa a0 0d 80 52 ...`).
- Manifest properties include `CHIP=0x6040` and `BORD=4`, consistent with T6040/J614s. Do not publish the target device's ECID.
- The raw stage1's byte length is 4096-aligned. The four-byte trailer yields payload length `4 mod 4096`. The entrypoint offset `0x800` is not 4096-aligned.

## Comparison with normal kernelcache
- Normal IMG4 `IM4P` type `krnl`, name `KernelManagement_host-463.40.2`, has an Apple-format payload and its own `IM4M` manifest.
- Normal PAYP's `kcep`, `kclf`, and `kcwz` are all 4 KiB aligned. **But** its compressed host-kernel format and memory layout are different from a `fuos` raw stage1. Direct alignment comparisons are diagnostic leads, **not evidence** that raw `fuos` values are invalid.
- The normal `IM4P` SHA-384 similarly appears in its manifest.

## Interpretation, limits, next action
The enrolled custom image is structurally well formed at the DER level, the payload precisely matches the pinned m1n1 build, its PAYP lengths correspond to its payload bytes, and the manifest has the correct IM4P SHA-384. We did **not** identify a truncated m1n1, missing header, or clear bad image digest.

Earlier offline iBoot disassembly found a 4096-alignment check associated with a panic-site instruction using 981. The report lacks runtime operands, so it is **not established** that `kcep=0x800` or `kclf=0x3B0004` caused the panic; Asahi intentionally calls `kmutil configure-boot --raw --entry-point 2048 --lowest-virtual-address 0`.

**Next work:** trace what value iBoot is checking at the `:981` path and identify how it is populated from the firmware image or memory descriptors. Static comparisons and a controlled debug experiment must precede any re-enrollment. Do not edit signed IMG4 blobs, pad the payload, reinstall the stub, or change SIP/boot policy merely to test a guess.
