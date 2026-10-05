J614s M4 Pro development status
===============================

Scope
-----

This branch targets the 14-inch MacBook Pro (2024), J614s / Mac16,8,
with the T6040 M4 Pro. Other MacBook sizes and chips are not validated.

The development kernel workflow builds a linked ARM64 Image, loadable
modules, the J614s DTB, exact kernel configuration, source revision and
checksums. It also builds a static ARM64 BusyBox initramfs and runs a
QEMU virt interactive-shell smoke test after both artifacts are built.
This is a C-driver bring-up configuration with 16 KiB pages.
Rust drivers, including Asahi GPU acceleration, are excluded. It is not
the complete Asahi distribution kernel configuration.

Build success establishes compilation and linkage only. It does not
establish successful boot, working input, storage, cooling or recovery.

Current source-level blockers
-----------------------------

* The base board DT contains bootloader-filled memory and framebuffer
  placeholders. A compatible loader must populate these correctly.
* The MTP mailbox, DART, DockChannel and HID nodes exist but remain
  disabled. Built-in driver compilation does not activate these nodes.
* The current T6040 DT does not describe internal NVMe or USB controllers.
  Neither an internal-disk installation nor a USB-root development system
  is supported by this DT.
* SMC nodes exist, but hardware communication, sensor reporting and thermal
  behaviour have not been verified on J614s.
* The 14-core CPU description requires loader fixups and pruning on
  differently binned hardware. Topology has not been verified on the
  user's physical laptop.
* A RAM-only diagnostic root filesystem is delivered, but no compatible
  loader, firmware bundle, persistent root filesystem or installer is
  delivered by the development kernel workflow.

Next development gates
----------------------

1. Pass the complete kernel build, targeted driver/DT validation and
   QEMU virt interactive-shell test. QEMU is a generic ARM64 platform;
   passing does not validate Apple interrupt, input or thermal hardware.
2. Establish the existing project's documented J614s boot chain and
   recovery procedure; verify loader support for this DT and CPU fixups.
3. Collect read-only hardware identification and ADT evidence from the
   target laptop. Reconcile registers, interrupts and power dependencies
   before enabling untested hardware nodes.
4. Demonstrate serial or framebuffer boot into an initramfs without
   depending on internal storage, with logs and a verified recovery path.
5. Validate interrupt delivery, SMC sensors and thermal behaviour; then
   enable and test the keyboard stack in a separate bring-up DT.
6. Implement and test the chosen storage/USB path, then establish a
   development root filesystem and reproducible kernel update procedure.
7. Consider installation only after boot and recovery are demonstrated
   on the exact model and the user explicitly authorizes the concrete
   disk and boot-security operations.

No installer commands are provided at this stage. The earlier user
constraint excludes repartitioning and boot-security/bootloader changes.
If the project's supported boot path requires those operations, that
constraint must be revisited explicitly before installation can proceed.

RAM-only shell artifacts
------------------------

The J614s Development Kernel workflow publishes separate kernel and
initramfs artifacts, each identified by the exact Git source revision.
The initramfs contains /init, static ARM64 BusyBox and its applet links,
a console device node, and package provenance with corresponding BusyBox
source downloads. The build does not need root privileges.

At boot, /init mounts only devtmpfs, procfs, sysfs and temporary RAM
filesystems. It saves dmesg to /run/boot.log and starts a console shell.
Exiting the shell restarts it rather than exiting PID 1. There is no
automatic disk mount, network setup, firmware loading or fan control.
The shell is a diagnostic environment, not an installation image.

The QEMU test uses the same built Image and initramfs, verifies checksums,
and requires both startup markers and a command executed through the
interactive console. Its transcript is uploaded as a separate artifact.
The model-specific DTB is not used by QEMU virt.

Boot-chain evidence
-------------------

GravityLinux/bootloader main contains T6040 CPU identification and SMP
handling, and its README describes initramfs payloads. These are source
capabilities, not a demonstrated J614s boot procedure. GravityLinux/installer
main explicitly supports only the M4 Mac mini (t8132 / j773gap). Do not
bypass its model restriction for this MacBook.

Sources:

* https://github.com/GravityLinux/bootloader/blob/main/src/chickens.c
* https://github.com/GravityLinux/bootloader/blob/main/src/smp.c
* https://github.com/GravityLinux/bootloader/blob/main/README.md
* https://github.com/GravityLinux/installer/blob/main/README.md

Read-only PCIe/SD hardware evidence
-----------------------------------

Before adding PCIe, DART or SD-card nodes to the J614s device tree, collect
the exact controller layout from the target Mac instead of copying addresses
from another Apple SoC or an experimental branch. In macOS, run::

    python3 tools/j614s/adt_pcie_report.py --output j614s-pcie-report.json

The collector uses only ``sysctl``, ``sw_vers`` and
``ioreg -p IODeviceTree -a``. It does not require sudo and does not invoke
``diskutil``, ``csrutil``, ``bputil``, ``kmutil`` or ``nvram``. It exports a
small allow-listed set of structural Device Tree properties for PCIe, DART,
SMC and SD-related nodes. Serial numbers, MAC/Bluetooth addresses,
calibration blobs and other unique identifiers are not exported.

The reviewed GravityLinux/bootloader revision
``950e6b7f268e71cf77889f27a760782bf898b651`` already contains the
T8132/T6040 PCIe initialization added by commit
``0c1ba6b65a1426aeb60acfa11ff0e068a3d0ba84``. That loader change handles
the M4-generation PHY reset-bit difference. The Linux Apple PCIe driver does
not currently reproduce that low-level reset sequence; existing T8132 device
trees bind through the ``apple,t6020-pcie`` fallback. Therefore do not add a
speculative T6040 PCIe C-driver variant unless captured hardware evidence
shows a Linux-visible register-layout difference.
The report is hardware evidence, not boot approval. Keep PCIe/SD support in a
disabled-by-default or bring-up-only DT until the captured J614s values have
been reconciled with the kernel driver and the matching m1n1 PCIe support.
Internal NVMe remains outside this evidence pass.

Read-only target report and recovery prerequisites
-------------------------------------------------

Run "python3 tools/j614s/preflight.py" in macOS on the target laptop.
It reports only whitelisted sysctl hardware fields and sw_vers version/build.
It does not collect serial numbers, identifiers, disk layouts or account data,
and does not invoke diskutil, csrutil, bputil, kmutil or nvram. It prints JSON
to stdout and returns a nonzero status if the model cannot be confirmed.
Even a model match always reports ready_to_boot=false.

Reviewed loader revision:
GravityLinux/bootloader 950e6b7f268e71cf77889f27a760782bf898b651.
Its dt_set_cpus implementation matches CPU nodes positionally against
loader SMP indices, verifies MPIDR, fills release addresses and prunes
inactive CPUs and their cpu-map references. J614s ADT CPU indices and the
12-core/14-core bin must be reconciled with this behaviour before a test.
Source-level T6040 recognition is not evidence of a successful board boot.

The documented Asahi stage-1 flow requires an internal OS boot identity
and recovery-mediated boot-policy enrollment. Tethered boot also requires
an enrolled m1n1 stage 1 and a host connection. A RAM-only root filesystem
does not eliminate those initial disk and boot-policy requirements.
These generic documents are not a qualified M4 Pro installation recipe.

Before a physical boot experiment, establish an independent backup and
the machine-specific fallback procedure. Apple's firmware recovery guide
requires another Mac on macOS 14 or later, internet access, and a USB-C cable
supporting data and charging. Revive preserves data; Restore erases it.
Do not perform either action merely to test readiness. Record availability
of the recovery host and cable; the collector cannot verify them.

The next hardware decision requires the target report, the availability of
a recovery host, the backup state, and an explicit, concrete decision about
the separate Linux boot identity. No stage-1 replacement, enrollment,
partition change or installer model override is automated by this branch.

References:

* https://asahilinux.org/docs/alt/boot-process-guide/
* https://asahilinux.org/docs/sw/tethered-boot/
* https://support.apple.com/en-us/108900
