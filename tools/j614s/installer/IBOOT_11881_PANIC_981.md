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

## Active J614s fuOS image analyzed (read-only upload, October 7)

Source: the user's copied **active** `kernelcache.custom.<coih>` file, **not** an edited or repacked boot image.

- Exact Image4 file length **3,869,544 bytes** (SHA-256 `2d513ff4d92539fc83957f3b3304f26dd44442e1d37bae3030634f7701fa53a1`). DER outer sequence ends exactly at EOF; contains `IMG4`, an `IM4P` with type `fuos`, a `PAYP` property set, and an `IM4M` manifest. **This checks structural parsing, not signature trust at boot.**
- Raw `fuos` byte payload begins at **file offset `0x48`** (72) and has size **`0x3B0004`** (3,866,628 bytes). SHA-256 `32cb8425aab65952c5421034f422444c28c0cafd476497846174edc658ff38be` exactly matches the previously verified `boot.bin`.
- Removing exactly **four final NUL bytes** yields the pinned m1n1 stage1 binary of size **`0x3B0000`** (3,866,624 bytes) and SHA-256 **`29c9ac4542577e88e58734075d069835afac1a6b4db8b16b7aa7000942196411`**. Asahi upstream's installer convention appends the four NUL bytes. **Do not remove the terminator speculatively.**
- The PAYP integers are **`kcep=0x800`** (2048 entry-point byte offset), **`kclf=0x3B0004`**, **`kcwz=0x3B0004`**, and `kclo=kclz=kcrf=kcrz=kcwf=0`. `0x800` points to nonpadding ARM64 code (begins with bytes `f3 03 00 aa`), and the configured entry-point matches Asahi's `kmutil --entry-point 2048 --lowest-virtual-address 0`.

### Important 4-byte size/alignment distinction

The pinned source binary was already **16 KiB aligned** (`0x3B0000`). The standard four-byte end marker produces an **unaligned file length** (`0x3B0004`). If that length is fed into the allocator at `0x3B72C`, iBoot rounds it to **`0x3B4000`**, one extra 16 KiB page.

However the **line-981 assertion is not directly a file-length assertion.** Verified surrounding disassembly:

```asm
0x3B780  ldr  x24, [x0, #0x20]         ; descriptor size, exact field meaning not proven
0x3B784  mov  w8, #0x3fff
0x3B788  add  x8, x24, x8
0x3B78C  and  x23, x8, #~0x3fff       ; allocation length rounded up to 16 KiB
0x3B790  mov  x0, x23
0x3B794  bl   0x3B660                   ; get allocation address; advance allocator by rounded size
0x3B798  mov  x1, x28                    ; address mapping descriptor
0x3B79C  mov  x2, x27
0x3B7A0  mov  x3, x25
0x3B7A4  bl   0x3B61C                   ; translated address = allocated_base - [x1+8] + [x1+16]
0x3B7A8  tst  x0, #0xfff               ; check returned ADDRESS, not length
0x3B7AC  b.ne 0x3B838                 ; panic at source line 981 if unaligned
```

The allocator at `0x3B660` uses a global cursor and advances it by **16 KiB-rounded** amounts via `0x39AC0`. Thus the relevant invariant for this translated address is **`(allocator_cursor - mapping_source + mapping_destination) % 4096 == 0`**. The four-byte padding convention **does not directly explain a nonzero remainder**, because the subsequent allocator increment is a multiple of 16 KiB. A secondary effect or another path cannot yet be excluded, but an image edit to remove the four bytes is **not justified** by the current data.

The function containing the line-981 panic also appears in iBoot's memory/kernel collection layout region, but whether it was invoked for this custom `fuos` payload, an Apple BootKC, or another boot allocation remains **unproven**. We do not have the runtime mapping descriptor, cursor, or caller context needed to derive the actual offending pointer. The DER payload's physical byte offset `0x48` is not evidence that iBoot loads or executes code from an address ending in `0x48`; Image4 is parsed and unwrapped first.

**Disposition:** no defective boot-image wrapper, wrong entry offset, missing source bytes, or mismatched file metadata has been demonstrated. The file-length anomaly is recorded as an investigative clue but **not** a validated root cause. No installed firmware or boot policy should be changed based on it.

## Next engineering steps

1. **Complete:** verified the active Image4 payload, entry point, length fields, exact original source bytes, and 4-byte terminator; see above. Do not assume this is the root cause.
2. **Priority:** identify the invocation path and initialization of the allocator cursor and mapping descriptor bases (`[x1+8]` / `[x1+16]`) before a hardware test. Recovering the offending `x0` from this particular panic likely requires instrumentation/runtime evidence absent from the SOCD report.
3. Compare stock paired-Recovery/firmware compatibility for a 15.1 J614s stub on a 26.6.2 host as an *unproven* compatibility hypothesis.
4. Keep the independently reproducible experimental m1n1 RVBAR guard in **draft PR #9**, unmerged and uninstalled. It operates after m1n1 executes and is not a proven solution to an earlier iBoot address-alignment assertion.

No data from the physical Mac's installed boot volume were modified by this offline analysis.
