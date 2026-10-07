# J614s input-thin bring-up

Purpose: test only the internal keyboard/trackpad path.

The DT enables the measured MTP chain:

- MTP ASC mailbox
- MTP DART
- generic RTKit helper
- DockChannel FIFO
- DockChannel HID endpoint

PCIe, SMC, Wi-Fi/BT, SD, NVMe and USB remain disabled.

All hardware-facing MTP/DockChannel/HID drivers are modules so the RAM shell
can load the chain deliberately and inspect the log after each step.

A pass means the keyboard and trackpad enumerate and produce sane HID events
without requiring any unrelated platform subsystem.
