# J614s Wi-Fi / Bluetooth isolated bring-up

This profile adds exactly one endpoint-power path to SMC-thin: PCIe port00 and
SMC GPIO key gP13 for the BCM4388 Wi-Fi/Bluetooth module.

The SD-reader path remains disabled and gP19 is never driven.

BCM4388 endpoint drivers are intentionally modules. The PCIe port power-up and
enumeration happen before userspace chooses whether to load brcmfmac or the
BCM4377-family Bluetooth HCI driver, which keeps endpoint power behavior
separate from endpoint-driver behavior.

## Source admission

Qualification must prove:

- the source includes SMC-thin;
- only port00 is enabled;
- gP13 is present and gP19 is absent;
- the exact measured BCM4388 Wi-Fi and Bluetooth PCI IDs are present;
- no GL9755/SD endpoint is present;
- SMC GPIO is enabled;
- Wi-Fi and Bluetooth endpoint drivers remain modular;
- battery/hwmon/input/RTC, SD, NVMe and USB remain disabled.

## Hardware controls

This path has prior J614s evidence of a high-core-count interaction when the
BCM4388 is powered. The eventual artifact should therefore carry both its
target boot arguments and a one-CPU control boot argument. A target failure
followed by a clean one-CPU control is useful evidence rather than a reason to
change unrelated code.

A pass admits port00 power/enumeration and then the manually loaded BCM4388
drivers. It does not admit the SD reader or any other PCIe endpoint.
