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
