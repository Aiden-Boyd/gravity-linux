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

The bootstrap keeps the reviewed Asahi installer logic at `v0.9.2`, but
replaces its older **stage-1** binary with the reproducible
`v1.9.9-j614s.1` chainloading build based on upstream m1n1 source commit
`809541515659bf4e504807fd72bc0a539be5eee7`. The J614s build adds only the
reviewed T6040 WFI, DAPF, log-buffer, MCC and conservative cpufreq deltas.
It was built twice byte-identically in CI using
`RELEASE=1 CHAINLOADING=1`, GCC cross tools, and Rust/Cargo 1.98.1.

The exact binary is pinned at repository commit
`a853472376b58b794637b43a9f34dc1ae76a7daa`, size 3,866,624 bytes, SHA-256
`40e9510d539fb539f09c1b944ab3d1c23f2d7f8ed604e1c200bedf5564249499`.
The installer verifies all of those properties before replacing the packaged
stage-1. It does **not** install the upstream `m1n1-stage2-v1.9.9.zip` in the
stage-1 slot.

Normal installer mode is intentionally separate because it *does* create the
stub environment and enters Apple's authenticated boot-policy flow. Have a
current backup before that step.

## Build artifacts

GitHub Actions builds three RAM-boot bundles:

- `j614s-ramboot-safe`: single CPU, no PCIe/DART/SMC/input/Wi-Fi/MMC/USB/NVMe.
- `j614s-ramboot-diagnostic`: single CPU, reviewed hardware nodes, drivers as modules.
- `j614s-ramboot-yolo`: reviewed nodes probe automatically; not a first-boot profile.

All three profiles currently force `nr_cpus=1 maxcpus=1 idle=nop arm64.nowfxt`.
The WFI/WFIT flags are the current M4 bare-metal mitigation, while the one-CPU
limit also avoids the reproducible J614s/T6040 multi-core page-copy/MM fault.
SMP testing must be introduced as a separate, explicit diagnostic profile.

The SAFE bundle is the only intended first hardware boot.

All RAM-boot profiles use `panic=0` during bring-up. A kernel panic therefore
stays on the serial console instead of immediately rebooting the target and
discarding the most useful failure evidence.

## Host-side loader

Use a second Linux/macOS host connected to the target by USB-C and the exact
reviewed m1n1 v1.9.9 checkout matching the enrolled stage-1 source revision:

```sh
git clone --depth 1 --branch v1.9.9 https://github.com/AsahiLinux/m1n1.git
```

The host loader verifies the checkout is commit
`809541515659bf4e504807fd72bc0a539be5eee7` before contacting the target.
The enrolled target binary identifies as `v1.9.9-j614s.1`, while the host
proxy tools remain the exact upstream v1.9.9 checkout; the J614s patch keeps
the proxy feature-structure size/ABI compatible.

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

## J614s trackpad protocol

The DockChannel HID driver carries the J614s/T6040 interface-power protocol
fix proven by Project Wallace: command 0x40 uses the 9-byte version-2
will-change/has-changed request on J614s, with a version-1 fallback for older
firmware. SAFE does not enable this driver. Diagnostic/yolo can exercise it
only after the machine-specific trackpad firmware is supplied.

The Apple firmware blob is intentionally not stored in this repository.

## Additional J614s runtime guards

The T6040 AIC path avoids firmware-locked EL2 guest-timer/vGIC system
registers, the MTP ASC mailbox uses the measured J614s interrupt ordering
`793, 792, 795, 794`, and DockChannel HID rejects invalid interface indices
and recovers its interface-start state after timeouts. These are runtime
guards; they complement, rather than replace, the single-CPU/WFI mitigations.
