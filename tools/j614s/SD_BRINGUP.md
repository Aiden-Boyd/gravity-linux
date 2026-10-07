# J614s SD isolated bring-up

This profile tests only the GL9755 SD-reader path on top of SMC-thin.

It enables SMC GPIO, PCIe port01 and the measured gP19 power line. PCIe port00
and BCM4388/gP13 remain disabled, so Wi-Fi/BT cannot contaminate the result.

The GL9755 SDHCI driver remains modular. The image can therefore first prove
port01 power/enumeration, inspect PCIe/DART state, and only then load the SD
driver manually.

A pass admits the gP19/port01/GL9755 path only. It does not admit BCM4388,
internal NVMe, or persistent-root operation.
