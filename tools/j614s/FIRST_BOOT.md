# J614s / T6040 first-boot integration

This branch combines the J614s kernel/DT bring-up, RAM-only boot artifacts,
and the guarded tethered-development installer in one place.

Target: Mac16,8 / J614s / T6040 (14-inch M4 Pro MacBook Pro).

## Goal

The first hardware milestone is deliberately small:

1. enroll the m1n1 development stub using the reviewed installer path;
2. enter m1n1 proxy mode from a second host over USB;
3. load the SAFE bundle entirely into RAM;
4. reach `J614S_RAMBOOT_OK` / initramfs userspace on one CPU;
5. collect console logs without mounting internal storage.

Do not start hardware bring-up with the diagnostic or yolo profile.

## Before any disk or boot-policy change

From normal macOS on the target:

```sh
sh tools/j614s/installer/bootstrap.sh --probe
sh tools/j614s/installer/bootstrap.sh --deep-probe
```

Both modes are read-only with respect to APFS and boot policy. The deep probe
downloads temporary files and verifies that the J614s 15.1 BaseSystem AEA path
can actually be decrypted.

Normal installer mode is intentionally separate because it *does* create the
stub environment and enters Apple's authenticated boot-policy flow. Have a
current backup before that step.

## Build artifacts

GitHub Actions builds three RAM-boot bundles:

- `j614s-ramboot-safe`: single CPU, no PCIe/DART/SMC/input/Wi-Fi/MMC/USB/NVMe.
- `j614s-ramboot-diagnostic`: single CPU, reviewed hardware nodes, drivers as modules.
- `j614s-ramboot-yolo`: reviewed nodes probe automatically; not a first-boot profile.

The SAFE bundle is the only intended first hardware boot.

All RAM-boot profiles use `panic=0` during bring-up. A kernel panic therefore
stays on the serial console instead of immediately rebooting the target and
discarding the most useful failure evidence.

## Host-side loader

Use a second Linux/macOS host connected to the target by USB-C and an m1n1
checkout compatible with the stage-1 m1n1 installed on the target.

First validate the downloaded SAFE artifact without contacting the target:

```sh
./BOOT_FROM_HOST.sh --check ./j614s-ramboot-safe /path/to/m1n1
```

When the target is already in m1n1 proxy mode:

```sh
./BOOT_FROM_HOST.sh --boot ./j614s-ramboot-safe /path/to/m1n1
```

The wrapper verifies SHA-256 hashes, gzip integrity, profile/bootargs, the DTB
when `dtc` is installed, and the required Python packages before invoking
`proxyclient/tools/linux.py`.

m1n1's proxy ABI is not stable. Do not assume an arbitrary current checkout is
compatible with the m1n1 binary enrolled by the installer; keep the host and
target m1n1 revisions aligned before the first boot attempt.

## Success criterion

The SAFE initramfs prints `=== J614S_RAMBOOT_OK ===`, the kernel/model/CPU
information, and then idles in RAM. It does not supply a root filesystem and
does not automatically mount internal storage.

Only after that baseline is stable should the diagnostic profile be used to
load SMC, DART, DockChannel input, PCIe, SD and Wi-Fi one dependency at a time.
