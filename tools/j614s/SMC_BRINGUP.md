# J614s SMC-thin bring-up

Purpose: add only the T6040 SMC mailbox, RTKit transport and macsmc MFD core
on top of the already-isolated PCIe/DART foundation.

This image intentionally does **not** exercise any SMC consumer. The SMC GPIO
and hwmon child nodes are disabled, and the kernel profile disables the GPIO,
battery/power, hwmon, input, RTC and reboot consumers. There are no endpoint
power GPIOs in the DT, so BCM4388 and the SD reader remain unpowered.

## Why

Earlier J614s testing showed that simply saying "SMC enabled" was too broad.
SMC RTKit initialization could coexist with high CPU counts, while downstream
GPIO/power activity changed behavior materially. This profile makes the SMC
transport itself a separate admission step.

## Source qualification requirements

Before compilation:

- SMC-thin must include PCIe/DART-thin rather than the full board DT;
- SMC mailbox + core are explicitly enabled;
- SMC GPIO and hwmon DT children are explicitly disabled;
- GPIO, battery, hwmon, input, RTC and reboot consumers are disabled in Kconfig;
- Wi-Fi, Bluetooth, SD, NVMe and USB remain disabled;
- no endpoint power property or PCI endpoint compatible is introduced.

## Hardware pass

A pass means the SMC RTKit/MFD core initializes and stays stable with the
previously admitted CPU + PCIe/DART foundation. It does not admit GPIO key
writes, battery/thermal polling, RTC, reboot control, Wi-Fi/BT or SD.
