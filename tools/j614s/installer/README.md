# J614s tethered-development installer

Expert-only bootstrap for Mac16,8 / j614sap / T6040.

This is not a full Linux installer. It creates only the Asahi-style stub boot
environment required to enroll a T6040-capable m1n1 proxy for tethered, RAM-only
kernel bring-up.

## Safety

The bootstrap refuses to run unless the machine is Mac16,8, macOS is reviewed
26.x (26.5+), AC power is connected, at least 12 GiB is free, and no manually
created APFS volume named exactly m1n1 remains.

It exposes one installer profile only: Gravity Linux J614s tethered development
(m1n1 proxy only). That profile has no Linux partitions and does not request
firmware extraction.

APFS layout, stub macOS creation, Preboot/Recovery, machine-owner authentication,
Reduced Security, blessing, and stage-2 enrollment remain upstream Asahi installer
code.

## Provenance

- AsahiLinux/asahi-installer: MIT license.
- Reviewed upstream installer source shape: e93743d52178b3e26e428fa05174ef549abf30cb.
- That installer revision pins m1n1 809541515659bf4e504807fd72bc0a539be5eee7,
  which contains T6040 SoC, UART, SMP, and PCIe support.
- J614s restore identity: macOS 26.5.2 build 25F84, j614sap / Mac16,8.
- Recorded 25F84 BuildManifest SHA-256:
  a6e764ca158e10ea2ace9b74701f445eefbf012c9cdb5aaa616aa10a0b5197ef.
- macOS 26 AEA recovery decryption uses blacktop/ipsw (MIT), pinned to v3.1.730.
- Pinned blacktop/ipsw macOS arm64 archive SHA-256:
  3f50591e4674daf27d2c82a3e9cd4e37ccaa6297197cb5adc6999571859cd321.

No upstream Asahi or blacktop source is vendored into this repository.

## Run

From normal macOS:

    ./tools/j614s/installer/bootstrap.sh

The bootstrap enables the upstream installer's expert-mode prompt. Choose Yes.
The installer still asks for confirmation before resizing/creating the stub.

If empty manual m1n1 volumes from earlier testing still exist, remove only the
verified-empty ones first. The bootstrap never deletes them automatically.

After stage 1, follow the installer-provided shutdown and Startup Options /
Recovery instructions exactly. The resulting environment is only the m1n1 proxy;
the next step is the conservative J614s RAM-boot test bundle.
