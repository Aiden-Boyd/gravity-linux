# J614s iBoot 15.1 `:981` descriptor/alignment trace — 2026-10-08

**Scope:** static, offline, read-only analysis of the *user-provided* decompressed iBoot from the J614s/Apple T6040 Gravity installation. **Not a verified hardware fix.** The proprietary binary and device identifiers are **not committed to this repository**.

## Update: exact panic source identifier resolves the 981 collision

A fresh scan found **three** `mov w1,#981` instructions in this exact iBoot image. Their immediately preceding `bl` calls invoke small literal-loading functions, which return distinct 64-bit source identifiers in `x0`. All three sites then branch to the same panic reporter at `0x82250`.

| Line-981 site | Literal returned in `x0` | Equals recorded `3bdace14b1a9a68`? |
| --- | --- | --- |
| `0x3B83C` | `03bdace14b1a9a68` | **Yes** |
| `0x10C7B4` | `006b5f3c9b59dd40` | No |
| `0x15596C` | `099180f7bfe1a22b` | No |

Therefore the *full* firmware panic identifier **`3bdace14b1a9a68:981`**, as opposed to its line suffix, **identifies the translated-address alignment panic at `0x3B83C`** in this image. The remaining unknown is the *runtime memory descriptor and allocator state* that cause it to execute.

The checked-in Python script `tools/j614s/installer/audit_iboot_981_sites.py` rederives these source identifiers from the four MOVZ/MOVK literals and direct RET in each helper. It requires an exact SHA-256 match for the iBoot 15.1 binary. Its synthetic tests do not include firmware bytes.

## Reproducible input

- iBoot build: `RELEASE:iBoot-11881.41.5` (iBoot UUID `88DDD37F-DE0C-3B50-859C-5590A16B3384` as reported by SOCD).
- Decompressed image: **3,750,816 bytes**, SHA-256 `bd452a87420a03db8373c514a93014fdaa32019a43f1e830279ce2ea0c855e3b`.
- Linked image base: `0x10081AA4000`. All offsets below are **file offsets**; add base for linked virtual address.
- Prior original stage1 and new debug stage1 both produced **`3bdace14b1a9a68:981`**. Their SOCD reports lack runtime descriptor values and cannot identify which call site actually executed.

## Key instruction path

| Offset | Operation | Meaning |
| --- | --- | --- |
| `0x3B780` | `ldr x24, [x0,#0x20]` | Load requested size from descriptor |
| `0x3B784..0x3B78C` | `+0x3FFF; & ~0x3FFF` | Round size **up to 16KiB** |
| `0x3B794` | `bl 0x3B660` | Allocate rounded span from global cursor |
| `0x3B798..0x3B7A4` | `mov x1,x28; mov x2,x27; mov x3,x25; bl 0x3B61C` | Translate allocated address using a descriptor and verify descriptor pointer bounds |
| `0x3B634` | `ldr x8,[x1,#8]` | Load descriptor source base |
| `0x3B63C` | `ldr x9,[x1,#16]` | Load descriptor target base |
| `0x3B640..0x3B644` | `sub x8,x0,x8; add x0,x8,x9` | Return `allocated-source+target` |
| `0x3B7A8` | `tst x0,#0xFFF` | Require translated address aligned to **4KiB** |
| `0x3B7AC` | `b.ne 0x3B838` | Branch on misalignment |
| `0x3B83C` | `mov w1,#0x3D5` | `981` panic source-location argument |

The allocation function `0x3B660` calls `0x39AC0` to round the **size**, advances a global cursor and returns the previous cursor. The function does not independently force its **starting pointer** to be aligned. Therefore even a 16KiB-sized allocation does **not** independently establish its returned pointer's alignment. The actual global cursor initialization is not verified here.

At the test, the 4KiB residue is:

```
R = (allocator_return - descriptor.source_base + descriptor.target_base) mod 4096
if R != 0: enter the candidate line-981 panic block
```

**Important distinction:** the `0x800` FUOS `kcep` entry offset is **not an operand of this check**. There is no justified change to `kcep` or the four-byte tail on this evidence.

## Callers and alternate explanations

Four observed static higher-level calls (two via `0x3D57C`, two via `0x3D548`) reach the shared routine at `0x3B72C`:

- `0x372BC`, `0x37314` -> `0x3D57C` -> `0x3B72C`.
- `0x39390`, `0x393EC` -> `0x3D548` -> `0x3B72C`.

The callers at `0x372BC` and `0x39390` reference the literal string `SEPPatches`, and those at `0x37314` and `0x393EC` reference `uStuff`. These are *static names* visible in the binary, **not proof of a SEP failure or of the specific executing caller**.

At least three hypotheses are consistent with this path: (1) unaligned global allocator return, (2) source/target memory-mapping descriptor bases with unequal 4KiB remainders, or (3) invalid/stale descriptor data. Static iBoot and existing SOCD diagnostics cannot distinguish them.

## How to reproduce offline

```sh
python3 tools/j614s/installer/trace_alignment_callers.py /path/to/decompressed-iboot.bin --output /tmp/j614s-alignment-trace.json
python3 -m unittest discover -s tools/j614s/installer -p 'test_trace_alignment_callers.py' -v
```

The first command verifies exact known image SHA, linked base, **17 opcode fingerprints** and expected call-graph edges. It only *reads* a local file. The second command uses **synthetic test vectors** and no proprietary image. Optional `--allocation`, `--source-base`, `--target-base` take unsigned address values and calculate the residue. Those values must come from an independently verified runtime trace to be meaningful.

## Decision and safety gate

1. **No repeat boot yet:** release and debug builds show the same iBoot signature, so toggling m1n1 release/debug did not solve the first issue.
2. **No binary patching:** do not change iBoot, raw FUOS, signed kernelcache, SIP, 1TR boot policy or APFS merely to bypass this assertion.
3. **Next evidence needed:** capture firmware-time `allocator_return`, descriptor `+8/+16` for the exact failing call; alternatively locate a known-good, same-firmware boot-flow reference showing these operands. Generic USB monitoring after m1n1 would initialize cannot reveal this.
4. **Recovery:** keep normal macOS as default and the known-good original `boot-original.bin` backup intact until a controlled and reviewed test is justified.

**Boundary:** Source hash **plus** line 981 now identifies the iBoot translation/alignment assertion specifically. The runtime cause (allocator cursor, source/target mapping bases, input region, or OS-paired firmware interaction) remains unproven. This does **not** establish a fuOS payload corruption, nor does it justify patching signed firmware.
