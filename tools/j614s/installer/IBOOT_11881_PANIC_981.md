# J614s iBoot 11881.41.5 — panic marker `3bdace14b1a9a68:981`

**Status:** static reverse engineering reproduced from the user's own **decompressed** J614s iBoot 15.1 (24B2083) payload. This is a **failure-path identification**, **not a root-cause fix**. Do not change boot policy, rebuild Apple firmware, install a candidate binary, or reboot solely on this finding.

## Evidence and exact-file correlation

- J614s / T6040, Apple silicon `iBoot-11881.41.5`, previously reported as an SOCD `(iBoot panic)` at `2026-10-07 22:39:35 UTC`.
- Decompressed iBoot payload: **3,750,816 bytes** (raw ARM64, not a Mach-O executable); SHA-256:
  `bd452a87420a03db8373c514a93014fdaa32019a43f1e830279ce2ea0c855e3b`.
- The panic report's image UUID **`88DDD37F-DE0C-3B50-859C-5590A16B3384`** occurs in the raw executable at **file offset `0x182810`**, in network byte order. Matching both iBoot version and UUID strongly identifies the image; do not publish raw Apple firmware.
- The source hash `03bdace14b1a9a68` is constructed **at runtime** in AArch64 `mov/movk` instructions at offsets `0x3CE3C..0x3CE48`; byte-searching for the 64-bit hash does *not* find it because it is an instruction-embedded immediate.
- Hash helper `0x3CE3C`, decimal line **981** at `0x3B83C`, panic routine `0x82250`. This is the exact `3bdace14b1a9a68:981` marker reported on the Mac.

## Reconstructed failure path (file offsets with image analyzed at base zero)

```asm
0x3B798  mov   x1, x28
0x3B79C  mov   x2, x27
0x3B7A0  mov   x3, x25
0x3B7A4  bl    0x3B61C      ; calculate translated address in x0
0x3B7A8  tst   x0, #0xfff   ; require 4 KiB address alignment
0x3B7AC  b.ne  0x3B838     ; if not aligned, go to matching panic
...
0x3B838  bl    0x3CE3C     ; x0 = 0x03bdace14b1a9a68
0x3B83C  mov   w1, #981
0x3B840  bl    0x82250     ; fatal panic path
```

At `0x3B61C`, after validating the range and a non-null base, the helper reads `[x1+8]` into `x8`, reads `[x1+16]` into `x9`, and returns `x0 = input_x0 - x8 + x9`. The panic is reached if the returned address has one or more of the low twelve bits set.

**Most specific justified conclusion:** Apple iBoot's address/memory mapping path encountered a translation result that violates its 4 KiB-alignment assertion.

**Not established:** the offending input address, which component supplied the mapping, whether this happened while loading/customizing the `fuOS` image, whether SPTM is involved, or whether m1n1 had started executing. The SOCD report contains no register dump that can recover `x0` on the failing branch. In particular, this is **not evidence that the RVBAR workaround fixes the iBoot panic**.

## Reproducible offline inspection

For instruction disassembly, place the raw ARM64 payload in an analysis-only AArch64 ELF section at VMA zero, without modifying the bytes, and use LLVM objdump:

```text
llvm-objdump -d --start-address=0x3b61c --stop-address=0x3b66c wrapped.o
llvm-objdump -d --start-address=0x3b790 --stop-address=0x3b848 wrapped.o
llvm-objdump -d --start-address=0x3ce3c --stop-address=0x3ce50 wrapped.o
```

Instruction encodings: `0x3B7A8: f2402c1f`, `0x3B7AC: 54000461`, `0x3B83C: 52807aa1`, `0x3B840: 94011a84`. The `b.ne` immediate is encoded in bits **[23:5]**, so its verified target is `0x3B838`.

## Next engineering steps

1. Compare the actual custom Image4 `kernelcache.custom.<coih>` from Gravity Preboot with the configured `boot.bin`; verify any address/size/entry-point fields in the envelope and assess relevant alignment assumptions. This file is roughly 3.7 MiB and should be copied **read-only**, never rewritten in place.
2. Trace callers or dataflow into the mapping function enclosing `0x3B7A8`, especially the descriptor bases `[x1+8]` / `[x1+16]`. Recovering the offending value of `x0` requires runtime evidence not currently present.
3. Compare stock paired-Recovery/firmware compatibility for a 15.1 J614s stub on a 26.6.2 host as an *unproven* compatibility hypothesis.
4. Keep the independently reproducible experimental m1n1 RVBAR guard in **draft PR #9**, unmerged and uninstalled. It operates after m1n1 executes and is not a proven solution to an earlier iBoot address-alignment assertion.

No data from the physical Mac's installed boot volume were modified by this offline analysis.
