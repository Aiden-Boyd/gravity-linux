# Gravity Linux J614s: M4 first-handoff playbook (2026-10-08)

**Scope**: Mac16,8 / J614s / T6040, installed Gravity stub macOS 15.1, pinned m1n1 v1.9.9-j614s.4. This is a diagnostic workflow, **not** an established working M4 Pro recipe.

## References

- Yureka Lilian, *The forgetful CPU (Linux on M4)* (2026-10-02): https://yuka.dev/blog-2026-10-02-linux-m4.html
- Asahi m1n1 user guide: https://asahilinux.org/docs/sw/m1n1-user-guide/
- M4 Mini independent project (Mac16,10/T8132, NOT this Mac16,8/T6040): https://github.com/0xSero/mac-mini-m4-linux

## Verified from the Gravity repo

- `installer/bootstrap.sh` pins a stage-1 m1n1 build, sha256 `29c9ac4542577e88e58734075d069835afac1a6b4db8b16b7aa7000942196411`, 3,866,624 bytes. Installer generates a tethered **m1n1 proxy-only** stub and does not install a Linux root filesystem.
- Stage 1 was built with `RELEASE=1 CHAINLOADING=1`. Standard m1n1 release builds **hide console output by default**. Absence of screen output is not evidence that iBoot did not hand off.
- A previous host-independent read-only audit found the active custom FUOS embeds this build. The active/inactive Apple iBoot images embed identical IM4P payloads; 197-byte difference comes from their respective personalization tickets.
- Prior iBoot panic reported `3bdace14b1a9a68:981`; static disassembly has an alignment check and a panic with 981, but runtime operands and any direct causal relationship remain **unproven**.
- `tools/j614s/tethered-boot.sh --check` validates a Linux RAM-boot bundle and pinned m1n1 proxy checkout. It **cannot** detect a stage-1 boot failure on its own.

## Apply M4 Mini findings **in order**, without changing too many variables

1. **Pre-m1n1 handoff:** attempt existing authorized stage-1 **once**, with external boot observation and panic timestamp. If line-981 iBoot panic recurs without USB enumeration, don't start debugging Linux kernel, GPU, WFI, or device tree yet.
2. **m1n1 platform initialization:** confirm source/build contains T6040-specific bypasses for locked GXF and RVBAR writes. These were early M4-specific crashes in Yureka's M4 Mini work; existing Gravity's pin may already contain them. Do not assume a T8132 Mac mini patch can be applied unchanged to T6040.
3. **USB proxy:** connect a second macOS/Linux host with a data cable; run `tools/j614s/installer/watch_m1n1_usb.py` on the **host** *before* selecting Gravity in the target boot picker. A new `cu.usbmodem`/`ttyACM` device is evidence of USB enumeration, **not** by itself a complete m1n1 proxy session.
4. **Stage-1 release caveat:** Asahi documents that its release-build *backdoor* proxy mode requires `boot-args=-v` **and** SIP disabled from appropriate Recovery, and the host must open an ACM interface inside a short window. **Do not change SIP or NVRAM until the unmodified passive test and recovery plan are documented.** Merely waiting for USB CDC devices may be insufficient because release mode hides the console and continues booting.
5. **First confirmed proxy session:** test with the matching upstream m1n1 proxyclient against the enumerated m1n1 port, recording version and logs. Avoid copying unknown commands from T8132-specific tools to T6040 hardware.
6. **Minimal RAM Linux:** only after (5), use one-core diagnostic kernel with correct J614s DTB and serial `stdout-path` / `earlycon`; verify WFI/WFIT erratum workaround availability in the exact kernel. Yureka's work used minimal DTB, early UART markers, and then proper earlycon.
7. **Driver bring-up:** only after Linux reaches a shell, begin single-subsystem hardware tests, retaining macOS/Recovery. Do not touch NVMe writes or claim GPU/Bazzite support.

## Decision matrix

| Observation | Interpretation | Next investigation |
|---|---|---|
| iBoot panic :981, no m1n1 USB or console | Likely failed before accessible proxy; not proof m1n1 never executed | Map FUOS/iBoot descriptor, compare exact boot handoff; serial debug |
| New USB ACM nodes then disappear | m1n1 USB path might have initialized | Check USB device identity and timing; review release mode |
| m1n1 proxy handshake succeeds | Stage-1 execution proven | Set up known-pinned minimal RAM kernel |
| m1n1 GXF/RVBAR panic output | m1n1 executed but platform init failed | Upstream M4 conditional GXF/RVBAR fixes |
| Linux reaches shell but cores/idle crash | Kernel issue, not iBoot pre-handoff | Upstream WFI/WFIT and earlycon tests |

## Evidence checklist for each physical attempt

Record (a) target model and firmware, (b) image hashes, (c) whether the host was connected and logging before choosing Gravity, (d) clock time of selection, (e) host USB events with timestamps, (f) screen output, (g) resulting newest macOS panic signature. Retain original logs and keep one change per attempt.

## Safety

Do not re-install the existing Gravity stub, change boot policy or SIP, edit APFS volumes, pad signed images, suppress iBoot assertions, or write internal storage for this diagnostic. Physical execution of the test must occur on the user's Mac and (for USB) a separate monitoring host; repo editing cannot substitute for it.
