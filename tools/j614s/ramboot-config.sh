#!/bin/sh
# SPDX-License-Identifier: MIT
# Apply one of the J614s RAM-boot kernel profiles to an existing .config.

set -eu

PROFILE=${1:?usage: ramboot-config.sh safe|diagnostic|yolo|smp-thin|pcie-dart-thin|smc-thin|power-thin}
CFG=scripts/config

enable() { "$CFG" --enable "$1"; }
disable() { "$CFG" --disable "$1"; }
module() { "$CFG" --module "$1"; }

# Common boot/diagnostic foundation.
disable CONFIG_ARM64_4K_PAGES
enable CONFIG_ARM64_16K_PAGES
enable CONFIG_BLK_DEV_INITRD
enable CONFIG_DEVTMPFS
enable CONFIG_DEVTMPFS_MOUNT
enable CONFIG_SERIAL_SAMSUNG
enable CONFIG_SERIAL_SAMSUNG_CONSOLE
enable CONFIG_PRINTK_TIME
enable CONFIG_MAGIC_SYSRQ
enable CONFIG_KALLSYMS
enable CONFIG_PROC_FS
enable CONFIG_SYSFS
enable CONFIG_TMPFS
enable CONFIG_SMP

case "$PROFILE" in
safe|smp-thin)
	# Known-minimum rescue/SMP baseline. Do not probe DMA/storage/peripheral fabric.
	disable CONFIG_NVME_APPLE
	disable CONFIG_BLK_DEV_NVME
	disable CONFIG_PCIE_APPLE
	disable CONFIG_APPLE_DART
	disable CONFIG_MFD_MACSMC
	disable CONFIG_APPLE_DOCKCHANNEL
	disable CONFIG_HID_DOCKCHANNEL
	disable CONFIG_BRCMFMAC
	disable CONFIG_WLAN
	disable CONFIG_BT
	disable CONFIG_MMC
	disable CONFIG_USB
	;;

pcie-dart-thin)
	# Isolate the root complex and its two measured DARTs. Downstream ports
	# stay disabled in the dedicated DT, and SMC/endpoint stacks stay out.
	enable CONFIG_PM
	enable CONFIG_PCI
	enable CONFIG_PCI_MSI
	enable CONFIG_IOMMU_SUPPORT
	enable CONFIG_PINCTRL
	enable CONFIG_PINCTRL_APPLE_GPIO
	enable CONFIG_APPLE_DART
	enable CONFIG_PCIE_APPLE
	disable CONFIG_NVME_APPLE
	disable CONFIG_BLK_DEV_NVME
	disable CONFIG_MFD_MACSMC
	disable CONFIG_APPLE_DOCKCHANNEL
	disable CONFIG_HID_DOCKCHANNEL
	disable CONFIG_BRCMFMAC
	disable CONFIG_WLAN
	disable CONFIG_BT
	disable CONFIG_MMC
	disable CONFIG_USB
	;;

smc-thin)
	# Add the SMC transport/MFD core only. Every child consumer and endpoint
	# power path stays disabled for this stage.
	enable CONFIG_PM
	enable CONFIG_PCI
	enable CONFIG_PCI_MSI
	enable CONFIG_IOMMU_SUPPORT
	enable CONFIG_PINCTRL
	enable CONFIG_PINCTRL_APPLE_GPIO
	enable CONFIG_APPLE_DART
	enable CONFIG_PCIE_APPLE
	enable CONFIG_APPLE_MAILBOX
	enable CONFIG_APPLE_RTKIT
	enable CONFIG_MFD_MACSMC
	disable CONFIG_GPIO_MACSMC
	disable CONFIG_SENSORS_MACSMC_HWMON
	disable CONFIG_MACSMC_POWER
	disable CONFIG_INPUT_MACSMC_INPUT
	disable CONFIG_RTC_DRV_MACSMC
	disable CONFIG_POWER_RESET_MACSMC
	disable CONFIG_NVME_APPLE
	disable CONFIG_BLK_DEV_NVME
	disable CONFIG_APPLE_DOCKCHANNEL
	disable CONFIG_HID_DOCKCHANNEL
	disable CONFIG_BRCMFMAC
	disable CONFIG_WLAN
	disable CONFIG_BT
	disable CONFIG_MMC
	disable CONFIG_USB
	;;

power-thin)
	enable CONFIG_MODULES
	enable CONFIG_PM
	enable CONFIG_PCI
	enable CONFIG_PCI_MSI
	enable CONFIG_IOMMU_SUPPORT
	enable CONFIG_PINCTRL
	enable CONFIG_PINCTRL_APPLE_GPIO
	enable CONFIG_APPLE_DART
	enable CONFIG_PCIE_APPLE
	enable CONFIG_APPLE_MAILBOX
	enable CONFIG_APPLE_RTKIT
	enable CONFIG_MFD_MACSMC
	enable CONFIG_POWER_SUPPLY
	enable CONFIG_HWMON
	module CONFIG_MACSMC_POWER
	module CONFIG_SENSORS_MACSMC_HWMON
	module CONFIG_INPUT_MACSMC_INPUT
	module CONFIG_RTC_DRV_MACSMC
	module CONFIG_ARM_APPLE_SOC_CPUFREQ
	disable CONFIG_GPIO_MACSMC
	disable CONFIG_POWER_RESET_MACSMC
	disable CONFIG_BRCMFMAC
	disable CONFIG_WLAN
	disable CONFIG_BT
	disable CONFIG_MMC
	disable CONFIG_NVME_APPLE
	disable CONFIG_BLK_DEV_NVME
	disable CONFIG_APPLE_DOCKCHANNEL
	disable CONFIG_HID_DOCKCHANNEL
	disable CONFIG_USB
	;;

diagnostic|yolo)
	enable CONFIG_MODULES
	enable CONFIG_PM
	enable CONFIG_PCI
	enable CONFIG_PCI_MSI
	enable CONFIG_IOMMU_SUPPORT
	enable CONFIG_INPUT
	enable CONFIG_HID_SUPPORT
	enable CONFIG_HID
	enable CONFIG_NEW_LEDS
	enable CONFIG_LEDS_CLASS
	enable CONFIG_POWER_SUPPLY
	enable CONFIG_HWMON
	enable CONFIG_BLOCK
	enable CONFIG_NET
	enable CONFIG_WLAN
	enable CONFIG_CFG80211
	enable CONFIG_MMC
	enable CONFIG_USB
	enable CONFIG_SND
	enable CONFIG_SND_SOC
	enable CONFIG_DRM
	enable CONFIG_DRM_SIMPLEDRM

	if [ "$PROFILE" = diagnostic ]; then
		# Keep hardware-facing drivers unloadable until explicitly requested.
		module CONFIG_PINCTRL_APPLE_GPIO
		module CONFIG_APPLE_MAILBOX
		module CONFIG_APPLE_RTKIT
		module CONFIG_APPLE_RTKIT_HELPER
		module CONFIG_APPLE_DART
		module CONFIG_APPLE_SART
		module CONFIG_MFD_MACSMC
		module CONFIG_GPIO_MACSMC
		module CONFIG_APPLE_DOCKCHANNEL
		module CONFIG_HID_DOCKCHANNEL
		module CONFIG_HID_APPLE
		module CONFIG_HID_MAGICMOUSE
		module CONFIG_MACSMC_POWER
		module CONFIG_SENSORS_MACSMC_HWMON
		module CONFIG_INPUT_MACSMC_INPUT
		module CONFIG_PCIE_APPLE
		module CONFIG_NVME_APPLE
		module CONFIG_SPI_APPLE
		module CONFIG_BRCMFMAC
		enable CONFIG_BRCMFMAC_PCIE
		module CONFIG_BT_HCIBCM4377
		module CONFIG_ARM_APPLE_SOC_CPUFREQ
		module CONFIG_MMC_SDHCI
		module CONFIG_MMC_SDHCI_PCI
		module CONFIG_SND_SOC_APPLE_MCA
		module CONFIG_SND_SOC_APPLE_MACAUDIO
		module CONFIG_USB_XHCI_HCD
	else
		# YOLO: same reviewed nodes, but let supported drivers probe at boot.
		# arm64 defconfig leaves RFKILL modular; that caps CFG80211 and
		# BRCMFMAC at =m even when requested built-in. Make the dependency
		# built-in too so Wi-Fi can actually probe automatically.
		enable CONFIG_RFKILL
		enable CONFIG_CFG80211
		# BT depends on RFKILL || !RFKILL. Re-promote it only after
		# RFKILL=y so the exact BCM4388 PCIe HCI driver can be built in.
		enable CONFIG_BT
		enable CONFIG_BT_HCIBCM4377
		enable CONFIG_ARM_APPLE_SOC_CPUFREQ
		enable CONFIG_PINCTRL_APPLE_GPIO
		enable CONFIG_APPLE_MAILBOX
		enable CONFIG_APPLE_RTKIT
		enable CONFIG_APPLE_RTKIT_HELPER
		enable CONFIG_APPLE_DART
		enable CONFIG_APPLE_SART
		enable CONFIG_MFD_MACSMC
		enable CONFIG_GPIO_MACSMC
		enable CONFIG_APPLE_DOCKCHANNEL
		enable CONFIG_HID_DOCKCHANNEL
		enable CONFIG_HID_APPLE
		enable CONFIG_HID_MAGICMOUSE
		enable CONFIG_MACSMC_POWER
		enable CONFIG_SENSORS_MACSMC_HWMON
		enable CONFIG_INPUT_MACSMC_INPUT
		enable CONFIG_PCIE_APPLE
		enable CONFIG_NVME_APPLE
		enable CONFIG_SPI_APPLE
		enable CONFIG_BRCMFMAC
		enable CONFIG_BRCMFMAC_PCIE
		enable CONFIG_MMC_SDHCI
		enable CONFIG_MMC_SDHCI_PCI
		enable CONFIG_SND_SOC_APPLE_MCA
		enable CONFIG_SND_SOC_APPLE_MACAUDIO
		enable CONFIG_USB_XHCI_HCD
	fi
	;;

*)
	echo "unknown profile: $PROFILE" >&2
	exit 2
	;;
esac
