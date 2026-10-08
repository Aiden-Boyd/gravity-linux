# Gravity J614s first-boot firmware contract audit — 2026-10-08

**Status:** read-only investigation. This report is not an authorized firmware upgrade or a tested repair. Target: M4 Pro Mac16,8 / j614sap / T6040.

## High-confidence result: exact iBoot panic site identified

Original m1n1 release build and later debug m1n1 build produced the same SOCD signature:
`3bdace14b1a9a68:981` from `RELEASE:iBoot-11881.41.5`. The debug panic metadata specifies macOS 15.1 (24B2083), the Gravity stub.

The **line suffix 981 is not unique** in this iBoot (three `MOV W1,#981` sites), but each candidate sets `X0` to a distinct, 64-bit source identifier via four MOVZ/MOVK instructions and `RET`, then calls the same reporter at `0x82250`:

| File offset (MOV W1,#981) | X0 source identifier | Reporter |
|---|---|---|
| `0x3B83C` | `03bdace14b1a9a68` | `0x82250` |
| `0x10C7B4` | `006b5f3c9b59dd40` | `0x82250` |
| `0x15596C` | `099180f7bfe1a22b` | `0x82250` |

The recorded panic matches **only** the first identifier. It therefore identifies the translated-address alignment branch at `0x3B7A8` and its `0x3B83C` panic site in the exact decompressed iBoot (SHA-256 `bd452a87420a03db8373c514a93014fdaa32019a43f1e830279ce2ea0c855e3b`).

Instruction sequence: descriptor size at +0x20 rounded up to 16 KiB; global cursor allocator returns a starting address; translation computes `allocated - descriptor[+8] + descriptor[+16]`; result tested with `TST X0,#0xFFF`; misalignment branches to the matched panic. The allocator does **not** force its returned starting address to be 4KiB-aligned. Its cursor and limit are stored in runtime global data (references near `0x395C38/0x395C40`, beyond the decompressed file image); no runtime cursor value is recoverable from this static image. **Do not assert which operand was unaligned.**

Reproduce locally (no Apple binary committed):
```
python3 tools/j614s/installer/audit_iboot_981_sites.py /path/to/decompressed-iboot.bin
```

## Upstream installer compatibility comparison

Asahi's pinned `v0.9.2` `src/main.py` lists supported `CHIP_MIN_VER`, `DEVICES`, and `IPSW_VERSIONS`. It **does not** list T6040, `j614sap`, or a 15.1 IPSW entry. These have been added by Gravity's `tools/j614s/installer/patch_installer.py`:

- `0x6040: "15.1"` in the chip minimum list;
- `"j614sap": Device("15.1", True)` in the device list;
- `IPSW("15.1", "15.1", "iBoot-0", "0", True, ["j614sap"], <Apple 15.1 restore URL>)`.

**The minimum iBoot and SFR gate values are placeholders (`iBoot-0`, `0`)**, not independently established platform thresholds. Gravity's `probe_host.py` checks the *currently booted* macOS / main SFR correspondence, Recovery presence, and boot/default VGID compatibility. It **does not establish** whether **15.1 OS-paired firmware** has correct memory descriptors on a machine whose system-global firmware is now from macOS 26.6.2.

Gravity's installed custom FUOS was already audited: valid parse and digest and exact m1n1 payload embedding. These checks rule out simple file corruption, but not OS-paired firmware memory-map behavior.

## Apple / Asahi firmware distinction

Asahi documents (a) **system-global** firmware as updated by macOS, intended to be backward-compatible, and (b) **OS-paired** firmware installed in a stub OS, which is version-specific. The main OS being 26.6.2 while Gravity's OS-paired iBoot is 15.1 **does not alone demonstrate incompatibility**; it does create an important axis to investigate. The 15.1 paired Recovery booted and successfully enrolled the custom stage1, so part of the paired boot environment was functional.

Sources:
- https://asahilinux.org/docs/platform/quirks/
- https://asahilinux.org/docs/fw/boot/
- https://github.com/AsahiLinux/asahi-installer/blob/v0.9.2/src/main.py
- https://github.com/AsahiLinux/asahi-installer/blob/v0.9.2/src/step2/step2.sh
- https://github.com/Aiden-Boyd/gravity-linux/blob/j614s-one-shot-diagnostics/tools/j614s/installer/patch_installer.py

## What remains unknown / safe next research

1. Runtime allocator cursor before `0x3B660` and source/target descriptor bases at `0x3B61C`.
2. Whether descriptor chosen is for a system-global region, `SEPPatches`, `uStuff`, or another firmware boot range. Those labels are *not* themselves proof of an SEP failure. A separate SPTM technical analysis shows they are ordinary named bootstrap regions.
3. Whether a **documented** M4 Pro / j614sap reference uses a newer OS-paired firmware successfully. No such same-hardware, verified reference has been established in this audit.

**Safety:** Keep Macintosh HD as default, preserve original stage1 on USB. Do not overwrite signed IMG4/iBoot, bypass the 981 assertion, change SIP/boot policy, or attempt a 15.1→26 stub firmware swap from copied files. Any future paired-stub experiment requires official device-specific IPSW inputs, a documented Recovery and rollback plan, and explicit user approval.

## Relevant follow-up check

Because the source hash resolves the exact panic site, further static work should trace where `0x395C38` is initialized and which descriptor pointer `0x3B72C` receives along the four known callers. A future authorized runtime trace would distinguish the actual misaligned value. Generic USB-only diagnostics cannot capture that iBoot internal state.
