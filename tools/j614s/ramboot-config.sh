#!/bin/sh
# SPDX-License-Identifier: MIT
# Apply one of the J614s RAM-boot kernel profiles to an existing .config.

set -eu

PROFILE=${1:?usage: ramboot-config.sh safe|diagnostic|yolo}
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

case "$PROFILE" in
safe)
	# Known-minimum rescue baseline. Do not probe DMA/storage/peripheral fabric.
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

diagnostic|yolo)
	enable CONFIG_MODULES
	enable CONFIG_PM
	enable CONFIG_PCI
	enable CONFIG_PCI_MSI
	enable CONFIG_IOMMU_SUPPORT
	enable CONFIG_INPUT
	enable CONFIG_HID_SUPPORT
	enable CONFIG_HID
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
		module CONFIG_APPLE_DOCKCHANNEL
		module CONFIG_HID_DOCKCHANNEL
		module CONFIG_PCIE_APPLE
		module CONFIG_NVME_APPLE
		module CONFIG_SPI_APPLE
		module CONFIG_BRCMFMAC
		enable CONFIG_BRCMFMAC_PCIE
		module CONFIG_MMC_SDHCI
		module CONFIG_MMC_SDHCI_PCI
		module CONFIG_SND_SOC_APPLE_MCA
		module CONFIG_SND_SOC_APPLE_MACAUDIO
		module CONFIG_USB_XHCI_HCD
	else
		# YOLO: same reviewed nodes, but let supported drivers probe at boot.
		enable CONFIG_PINCTRL_APPLE_GPIO
		enable CONFIG_APPLE_MAILBOX
		enable CONFIG_APPLE_RTKIT
		enable CONFIG_APPLE_RTKIT_HELPER
		enable CONFIG_APPLE_DART
		enable CONFIG_APPLE_SART
		enable CONFIG_MFD_MACSMC
		enable CONFIG_APPLE_DOCKCHANNEL
		enable CONFIG_HID_DOCKCHANNEL
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
