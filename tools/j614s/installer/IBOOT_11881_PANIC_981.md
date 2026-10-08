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

## Caller and memory-descriptor dataflow — static AArch64 audit

This follow-up used the same **3,750,816-byte** decrypted/decompressed iBoot, wrapped **only in a temporary ELF for LLVM disassembly**. All addresses in this section are raw **file-relative instruction offsets (VMA 0)**; data/BSS symbol locations are likewise relative to the image base. They are *not physical addresses recovered from the panic log*.

### How the crashing routine is called

The 4 KiB assertion belongs to the function beginning **`0x3B72C`**. A scan for direct AArch64 `BL` calls to `0x3B72C` returns none because two branch-island forwarding stubs use `B`, not `BL`:

- `0x3D548` prepares arguments, checks pointer-authentication state, then `B 0x3B72C` at **`0x3D564`**.
- `0x3D57C` similarly forwards via **`B 0x3B72C`** at **`0x3D598`**.

Four statically identifiable call sites pass through these stubs:

| Caller `BL` | Forwarding entry | Named region |
|---|---|---|
| `0x372BC` | `0x3D57C` | `SEPPatches` |
| `0x37314` | `0x3D57C` | `uStuff` |
| `0x39390` | `0x3D548` | `SEPPatches` |
| `0x393EC` | `0x3D548` | `uStuff` |

The strings are embedded at **`0x2841F4`** (`SEPPatches\0`) and **`0x2841FF`** (`uStuff\0`), and their references can be verified at call-site setup `0x372A4/0x372FC` and `0x39378/0x393D4`.

These are memory/boot-region names; the surrounding string table also contains `SEPFW`, `preoslog`, `BootArgs`, and kernel-header region names. Public SPTM reverse-engineering references independently describe `SEPPatches` and `uStuff` as registered boot memory regions, but **that alone does not establish that SPTM is executing at this precise point**. It is the **iBoot code** that calls the line-981 assertion.

**Important constraint:** this proves that either named region *can reach* the crash, **not** which of the four calls actually ran during the observed failure. The SOCD report does not preserve that stack.

### Map descriptors and their initialization

The failing routine saves x5 as x28 (`0x3B758`), and calls the translation helper `0x3B61C` with x1 = x28 (`0x3B798`). The helper reads the mapping source and destination as **`[x1+8]`** and **`[x1+16]`**. Its result is checked at `0x3B7A8`.

First family (`0x372BC`, `0x37314`):
- `0x36458–0x3645C` sets x19 = **`0x395C48`**; the containing routine initializes a `0x488`-byte record here.
- `0x36B08–0x36B10` stores x25 and x27 beginning at **`0x395C58`** (descriptor+16 and +24).
- `0x371E4–0x371F0` translates using x19 as the mapping descriptor.
- `0x372B0` and `0x37308` pass x7 = x19+`0x488` as the bounds/end of that descriptor region. The stub at `0x3D57C` supplies x5=x6=x19 for the alignment-checked routine.

Second family (`0x39390`, `0x393EC`):
- `0x37640–0x37644` sets x19 = **`0x3960D0`** and initializes a `0x488`-byte record there.
- `0x37F08–0x37F14` sets x19 = `0x3960E0` (=descriptor+16) and stores **x20**, loaded from stack at `[sp+0x70]`, into `0x3960E0` (translation destination) and x27 into `0x3960E8`.
- `0x38ACC–0x38B10` computes translation source from earlier range metadata: `x20 = ([input+8] & 0xfffffffffe000000) + [sp+0x128]`; then `x8 = x20 - [sp+0x130]`; store x8 into **`0x3960D8`** (descriptor+8). The `[input+8]` value itself is populated earlier at runtime.
- `0x39248–0x3925C` sets x21 = `0x3960D0` for later allocations and translations. `0x39384/0x393E0` passes x7 = x21+`0x488`. The stub at `0x3D548` supplies x5=x6=x21.

All descriptor addresses are **beyond the decompressed image end `0x393BA0`** (i.e. runtime BSS/data, not present as initialized bytes in the uploaded payload). Hence exact mapping values depend on boot-time inputs and cannot be read from the static file.

Allocator **initialization** in the first-family loader is now found: **`0x36BC4–0x36BE0`**. The routine sets x10 = **`0x395C38`**, then performs `stp x8, x9, [x10]` at **`0x36BDC`**, writing the initial cursor (x8, loaded from `[x29-0xC8]`) and available-length value (x9, calculated as x27 minus a stack-frame value) into global fields `0x395C38/0x395C40`. The inputs are assembled from earlier boot-time range records rather than immutable bytes. This identifies the initializer, **not the actual failing cursor value**.

Allocator `0x3B660`: reads a runtime cursor from **`0x395C38`**, invokes `0x39AC0` to round a requested size **up to 16 KiB**, then increments `0x395C38` and decrements the available byte count at **`0x395C40`** by that rounded size. It returns the **previous cursor**. The 16 KiB increment preserves the cursor's lower 12 bits: it does *not* independently establish that the initial cursor was 4 KiB-aligned.

The actual check therefore reduces to:

```text
( initial allocator cursor - descriptor.source + descriptor.destination ) & 0xfff == 0
```

because every allocator size increment observed in this helper is a multiple of 16 KiB. **The relevant issue to investigate is the initial cursor and translation bases and how the two registration paths configure them.**

### Initial allocator cursor reconstructed to a runtime layout-record formula (Oct 7 follow-up)

**New result:** the first-family allocator initializer **is not opaque anymore**. Its low bits originate in a specific five-term expression built from the layout record being processed.

The caller sets up the layout parser `0x3AC18` at `0x36B24–0x36BA0`:

- At `0x36AD8–0x36ADC`, helper `0x3D304` rounds **both** x8 and x9 **up to 16 KiB**, then saves them in `[x29-0xF0]` / `[x29-0xE8]`.
- `0x36B24` loads x2 from `[x29-0xF0]`: **x2 is therefore 16 KiB-aligned** at parser entry.
- `0x36B8C` writes mode **1** to the parser's first stack argument; `0x36B98` sets x5=x28 (the runtime input layout-record pointer); `0x36BA0` calls `0x3AC18`.
- `0x3AC40` saves x5 in x19 and `0x3AC78` loads mode 1, selecting the `0x3AFF0` branch. At `0x3AD3C`, the parser saves its original x2 at `[sp+0xB0]`. It receives an output pointer to caller temporary `[x29-0xC8]`, which it handles through multiple stack-pointer arguments (from `0x36B40–0x36B7C`).
- At `0x3B0D4–0x3B0E4` the parser loads four 64-bit layout-record fields: `x8=[x19+0x18]`, `x9=[x19+0x88]`, `x10=[x19+0x98]`, `x11=[x19+0x08]`, with `x13=[sp+0xB0]` (the incoming x2).
- At `0x3D294–0x3D2AC`, the parser's shared helper restores x12 from `[x29-0x68]`, containing the output pointer to the caller's `[x29-0xC8]` temporary. Back at `0x3B168–0x3B17C`, mode 1 computes and **stores** the cursor into this temporary:

```asm
0x3B168  ldr x11, [x19, #0x08]       ; R8
0x3B16C  add x8,  x8,  x13           ; R18 + base
0x3B170  add x9,  x9,  x10           ; R88 + R98
0x3B174  add x8,  x8,  x9
0x3B178  add x8,  x8,  x11           ; + R8
0x3B17C  str x8, [x12]              ; caller's [x29-0xC8] output
```

- `0x36BD4` reads that output from `[x29-0xC8]` and `0x36BDC` writes it as allocator cursor at `0x395C38`.

Consequently, for **this first-family, mode-1 initialization**:

```text
base      = round_up_16K(previously computed base)
R         = runtime layout record at x28
cursor_0  = base + R[0x08] + R[0x18] + R[0x88] + R[0x98]
cursor_0 & 0xfff = (R[0x08]+R[0x18]+R[0x88]+R[0x98]) & 0xfff
```

This follows directly from the decoded instructions. **It does not establish the contents of R at crash time**; the input record lives in boot-time RAM. Other initializer paths must be analyzed separately.

For the line-981 panic on this path, since allocator increments are in 16 KiB units:

```text
panic iff (sum(R offsets) - descriptor.source + descriptor.destination) & 0xfff != 0
```

The boot-time descriptor values are still unknown, so this does **not** prove `R` was itself malformed or that these four fields individually require alignment. The invariant is on the *combined translation*, not on each record member independently.

**Second-family cross-check:** `0x37E48–0x37E78` passes a runtime base at `[sp+0x70]` through helper `0x3AA94` and stores its two results at `[sp+0x128]` / `[sp+0x130]`. `0x37F10–0x37F14` saves the original base as descriptor destination `[0x3960E0]`. At `0x38AC4–0x38B10` it sets descriptor source to `(R[0x08] & ~0x1ffffff) + [sp+0x128] - [sp+0x130]`. Its bottom 12 bits are therefore determined by **the difference between those two helper outputs**, since the 32 MiB mask removes low bits of the other term. Exact runtime helper outputs are not available from the uploaded firmware.

**Practical next step:** acquire an aligned-versus-failing boot-memory-layout *observation* (or precise caller context) before changing m1n1, `fuOS`, or iBoot. The input record R and the descriptor source/destination values are the minimal unknowns to capture. Static analysis has identified the arithmetic, not the specific corrupted or incompatible memory value.

### What is known vs not known

**Confirmed statically:** four call sites, two tail-branch stubs, names `SEPPatches`/`uStuff`, runtime descriptor addresses, source/destination calculation sites, 16 KiB-rounded bump allocator, fatal low-12-bit alignment assertion.

**Unproven:** actual runtime cursor and descriptors; which of the four calls ran on October 7; whether SPTM, a 15.1 stub/26.6.2 firmware combination, or a distinct memory-range input creates the mismatch; whether any revised m1n1 would be entered. **Do not install an RVBAR candidate or repack fuOS as a speculative fix.**

The next read-only investigation should trace the initializer for **`0x395C38/0x395C40`** and the origin of the second path's **`[sp+0x70]`**, **`[sp+0x128]`**, and **`[sp+0x130]`** inputs. If the initial cursor is guaranteed page-aligned, then a mismatch between translation bases must explain the line-981 panic. If the runtime inputs remain unknown, request a *recoverable* debug trace instead of changing boot bytes blindly.

## Image4 property-to-layout-record mapping: confirmed 4-byte residue (October 7, read-only)

### Provenance and caveat

Examined the **exact uploaded active Gravity fuOS** (`gravity-active-fuos.img4`, SHA-256 `2d513ff4d92539fc83957f3b3304f26dd44442e1d37bae3030634f7701fa53a1`) alongside the UUID-matched J614s iBoot 11881.41.5 executable. This is **static reverse engineering**, not a record of live CPU registers from the failed boot.

**New direct link** between the *Image4 manifest* and the *runtime layout parser*: `0x3593C` parses 4-character `kcXX` property names and dispatches by little-endian inverted comparison through `0x3CFE0`, which ORs high halfword `0x6B63` (`kc`) onto a suffix. For example `kcwz` corresponds to `w9=0x777A` at `0x35A60`, comparison `0x3CFE0`, then store into `[x19+0x88]` at `0x35C18`.

| Image4 property | Dispatch/store site | Runtime record field | Value in Gravity fuOS |
|---|---|---|---|
| `kclo` | `0x35A74` / `0x35A8C` | `R+0x08` | 0 |
| `kclz` | `0x35A00` / `0x35B20` | `R+0x98` | 0 |
| `kcwz` | `0x35A5C` / `0x35C18` | `R+0x88` | **`0x3B0004`** |
| `kclf` | `0x359E4` / `0x35AF8` | `R+0x90` | `0x3B0004` |
| `kcbz`, `kcxz`, `kcrz`, `kcsz` | `0x35AC4`, `0x35B00`, `0x35B84`, `0x35BCC`; accumulation `0x35BE8–0x35BF0` | `R+0x18` sum | 0: first two and fourth absent; `kcrz=0` |

All eight present properties were confirmed directly as DER `IA5String`/INTEGER objects near the end of the uploaded Image4: `kcep=0x800`, `kclf=0x3B0004`, `kclo=0`, `kclz=0`, `kcrf=0`, `kcrz=0`, `kcwf=0`, `kcwz=0x3B0004`.

The first-family caller `0x36100` saves **x2 as x28**; its dispatcher `0x1210` passes the caller's parsed layout record as x2 through `0x12C8`. At `0x36B98` it passes that record as x5 to `0x3AC18`, with mode=1 at `0x36B8C`. Consequently the computation already reconstructed at `0x3B168–0x3B17C` can be **evaluated for the specific Gravity `fuos` record**, provided that record is the runtime input to this path:

```text
cursor0 = align_up_16K(base) + R[kclo] + R[kclz] + R[kcwz]
          + (R[kcbz] + R[kcxz] + R[kcrz] + R[kcsz])

cursor0 (mod 4096) = (0 + 0 + 0x3B0004 + 0) & 0xFFF = **0x004**
```

**Why the extra four bytes now matter:** the original pinned m1n1 is **`0x3B0000`** bytes, which is 16 KiB-aligned. The installer appends the standard four NUL terminator bytes, causing `boot.bin` and Image4 `kcwz` to be **`0x3B0004`**. If the remaining memory-translation delta preserves low page bits, iBoot's line-981 assertion would indeed be reachable. This contradicts the previous weaker assumption that 16 KiB *allocation rounding alone* makes the four-byte suffix irrelevant: rounding allocation **increments** cannot fix a misaligned **initial cursor**.

**However, no root cause is proven yet.** The line-981 check tests `cursor0 - descriptor.source + descriptor.destination`. We have **not** recovered the *runtime* descriptor source/destination or a stack trace showing which of four `SEPPatches`/`uStuff` callers ran during the actual panic. Their delta could cancel the `+4`. Also, Asahi's m1n1 packaging intentionally uses a 4-byte terminator; do **not** remove it, pad the payload, patch iBoot, install experimental images, or reboot on this inference alone.

**Direct normal-macOS comparison is not yet possible** from the uploaded files: we have the Gravity custom Image4 and its 15.1 iBoot executable, but *no stock boot Image4 from the working 26.6.2 macOS installation*, which may use a different firmware code path. This must be recorded as missing evidence, not filled by assumptions.

### Read-only reproducer

The accompanying `probe_j614s_fuos_layout.py` parses the actual DER `kcXX` integer pairs from an Image4 copy and reports the **conditional mode-1 cursor low bits**. It does not touch the disk, `kmutil`, or policy. On the uploaded image:

```text
kcwz = 0x3b0004 (3,866,628)
kclf = 0x3b0004 (3,866,628)
kclo = 0
kclz = 0
kcrz = 0
iBoot 11881 mode-1 cursor initial low 12 bits: 0x004
```

A synthetic test setting `kcwz=0x3B0000` (metadata-only calculation, **not a proposed image edit**) yields `0x000`. This supports the arithmetic, not an end-to-end boot result.

**Best next evidence:** (1) identify whether `fuos` reaches the mode-1 parser in the actual failed boot; (2) derive or observe `descriptor.destination - descriptor.source` low 12 bits; (3) obtain the boot image from a **normal, successful** macOS boot and compare `kcwz` alignment as a control. Keep PR #9's RVBAR guard separate.

## Next engineering steps

1. **Complete:** verified the active Image4 payload, entry point, length fields, exact original source bytes, and 4-byte terminator; see above. Do not assume this is the root cause.
2. **Priority:** identify the invocation path and initialization of the allocator cursor and mapping descriptor bases (`[x1+8]` / `[x1+16]`) before a hardware test. Recovering the offending `x0` from this particular panic likely requires instrumentation/runtime evidence absent from the SOCD report.
3. Compare stock paired-Recovery/firmware compatibility for a 15.1 J614s stub on a 26.6.2 host as an *unproven* compatibility hypothesis.
4. Keep the independently reproducible experimental m1n1 RVBAR guard in **draft PR #9**, unmerged and uninstalled. It operates after m1n1 executes and is not a proven solution to an earlier iBoot address-alignment assertion.

No data from the physical Mac's installed boot volume were modified by this offline analysis.
