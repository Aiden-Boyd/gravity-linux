# J614s tethered-development installer

Expert-only bootstrap for Mac16,8 / j614sap / T6040.

This is not a full Linux installer. It creates only the Asahi-style stub boot
environment required to enroll a T6040-capable m1n1 proxy for tethered,
RAM-only kernel bring-up.

## Safety

The bootstrap refuses normal install mode unless the machine is Mac16,8,
macOS is reviewed 26.x (26.5+), AC power is connected, at least 12 GiB is
free, and no manually created APFS volume named exactly `m1n1` remains.

It also requires the currently booted macOS version, current System Firmware
(SFR) version, and SystemRecovery product version to match, requires normal
`macOS` boot mode, and requires the default boot volume group to be the
currently booted macOS volume group. This is a conservative J614s bring-up
gate before Apple's later bless/boot-policy flow.

It also refuses normal install mode when an existing or partial
`Gravity Linux J614s Dev` stub is visible. Cleanup is intentionally manual
so the bootstrap never guesses that an APFS container is disposable.

The installer exposes one profile only:

    Gravity Linux J614s tethered development (m1n1 proxy only)

That profile has no Linux root partition and does not request firmware
extraction.

APFS partitioning, machine-owner authentication, Reduced Security, blessing,
and stage-2 enrollment remain upstream Asahi installer code. The local patch
only adds J614s admission, AEA BaseSystem handling, and the paired-Recovery
stub layout required by J614s firmware.

## J614s stub firmware and paired Recovery

J614s shipped with macOS 15.1. The bootstrap deliberately uses the original
J614s restore image:

- macOS 15.1 (24B2083)
- device class `j614sap`
- product `Mac16,8`
- chip `0x6040`, board `0x04`
- IPSW SHA-256:
  `db472ab82a4909699de188a9a4a53f3617824b5c5bad629b139dd5ec5d781ef4`

J614s bootcaches metadata advertises `SupportsPairedRecovery` and omits the
legacy `RestoreBundlePath` key expected by current upstream Asahi
`stub.py`. The patch handles both layouts:

- legacy metadata: use the explicit `RestoreBundlePath`;
- paired-Recovery metadata: stage the preserved restore bundle at
  `<Preboot>/<VGID>/restore`.

The upstream System-volume restore symlink is retained only for the legacy
explicit-path case. Modern paired-Recovery stubs use the Preboot restore
bundle directly.

This fixes stub construction. It does not repair or update the host Mac's
SystemRecovery firmware. A host with mismatched macOS/main firmware and
SystemRecovery may still fail later during Apple's bless/boot-policy flow.

## Provenance

- AsahiLinux/asahi-installer: MIT license.
- Reviewed upstream installer source shape:
  `e93743d52178b3e26e428fa05174ef549abf30cb`.
- That installer revision pins m1n1
  `809541515659bf4e504807fd72bc0a539be5eee7`, which contains T6040
  SoC, UART, SMP, and PCIe support.
- Apple macOS 15.1 J614s restore image is downloaded directly from Apple's
  update CDN and is not redistributed.
- AEA BaseSystem decryption uses blacktop/ipsw (MIT), pinned to v3.1.730.
- Pinned blacktop/ipsw macOS arm64 archive SHA-256:
  `3f50591e4674daf27d2c82a3e9cd4e37ccaa6297197cb5adc6999571859cd321`.

No upstream Asahi source, blacktop source, Apple firmware, or proprietary
firmware blobs are vendored into this repository.

## Read-only compatibility probe

Before any install attempt, run:

    ./tools/j614s/installer/bootstrap.sh --probe

Probe mode downloads the packaged Asahi installer, verifies its embedded m1n1
has T6040 support, and range-reads the original J614s macOS 15.1 restore IPSW.
It checks:

- the exact J614s erase identity;
- the BaseSystem member and AEA wrapping;
- the bless2 paired-Recovery model;
- the restore-bundle strategy;
- fixed files consumed by current upstream `stub.py`;
- the Bootability and restore-manifest trees;
- every selected BuildManifest path that current `stub.py` would extract.

Probe mode does not require AC power and does not resize, create, mount, or
delete APFS partitions. It does not alter boot policy or Recovery state.

Normal install mode runs the same probe automatically and refuses to proceed
if the real IPSW cannot satisfy the planned stub construction.

The same command also performs a read-only host firmware/Recovery preflight.
It reports macOS, SFR, SystemRecovery, RestoreLongVersion values, boot mode,
and boot/default VGIDs. A version or boot-target mismatch blocks normal install
mode before APFS or boot-policy work.

For additional inspection of the currently working macOS Preboot layout, run:

    ./tools/j614s/installer/bootstrap.sh --local-probe

The local probe enumerates the existing Preboot VGID directories and shallow
restore/boot metadata without mounting Recovery volumes or modifying any disk,
APFS, boot-policy, or Recovery state.

## Run

From normal macOS:

    ./tools/j614s/installer/bootstrap.sh

The bootstrap enables the upstream installer's expert-mode prompt. Choose Yes.
The installer still asks for confirmation before resizing or creating the
stub.

If empty manual `m1n1` volumes from earlier testing still exist, remove only
the verified-empty ones first. The bootstrap never deletes them automatically.

If an earlier stage-1 attempt left a volume/container named
`Gravity Linux J614s Dev`, inspect and clean the partial stub explicitly
before retrying. Probe mode remains available while the partial stub exists.

After stage 1, follow the installer-provided shutdown and Startup Options /
Recovery instructions exactly. The resulting environment is only the m1n1
proxy; the next Linux step is the conservative J614s RAM-boot test bundle.
