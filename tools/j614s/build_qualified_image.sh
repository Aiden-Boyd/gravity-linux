#!/bin/sh
# SPDX-License-Identifier: MIT
# Build one J614s bring-up artifact only after source_qualify.py has passed.
set -eu

PROFILE=${1:?usage: build_qualified_image.sh <profile> <source-root> <output-dir> <qualified-sha>}
SRC=$(cd "${2:?missing source root}" && pwd)
OUT=${3:?missing output dir}
QUALIFIED_SHA=${4:?missing qualified source sha}

BRINGUP_DOC=
CONTROL_BOOTARGS=
NEED_MODULES=0
NEED_BUSYBOX=1

ONE_CPU_ARGS='earlycon=apple,s5l-uart console=ttySAC0,1500000 keep_bootcon ignore_loglevel loglevel=8 rdinit=/init panic=0 idle=nop arm64.nowfxt nr_cpus=1 maxcpus=1'
FOURTEEN_CPU_ARGS='earlycon=apple,s5l-uart console=ttySAC0,1500000 keep_bootcon ignore_loglevel loglevel=8 rdinit=/init panic=0 idle=nop arm64.nowfxt maxcpus=14'

cd "$SRC"

ACTUAL_SHA=$(git rev-parse HEAD)
[ "$ACTUAL_SHA" = "$QUALIFIED_SHA" ] || {
    echo "refusing build: checkout changed after source qualification" >&2
    exit 1
}
[ -z "$(git status --porcelain)" ] || {
    echo "refusing build: candidate source tree is dirty" >&2
    exit 1
}

case "$PROFILE" in
safe)
    KPROFILE=safe
    DTB=apple/t6040-j614s.dtb
    NEED_BUSYBOX=0
    BOOTARGS="$ONE_CPU_ARGS"
    ;;
smp-thin)
    KPROFILE=smp-thin
    DTB=apple/t6040-j614s.dtb
    BRINGUP_DOC=tools/j614s/SMP_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    ;;
pcie-dart-thin)
    KPROFILE=pcie-dart-thin
    DTB=apple/t6040-j614s-pcie-dart.dtb
    BRINGUP_DOC=tools/j614s/PCIE_DART_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    CONTROL_BOOTARGS="$ONE_CPU_ARGS"
    ;;
smc-thin)
    KPROFILE=smc-thin
    DTB=apple/t6040-j614s-smc.dtb
    BRINGUP_DOC=tools/j614s/SMC_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    CONTROL_BOOTARGS="$ONE_CPU_ARGS"
    ;;
wifi-bt)
    KPROFILE=wifi-bt
    DTB=apple/t6040-j614s-wifi-bt.dtb
    NEED_MODULES=1
    BRINGUP_DOC=tools/j614s/WIFI_BT_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    CONTROL_BOOTARGS="$ONE_CPU_ARGS"
    ;;
sd)
    KPROFILE=sd-thin
    DTB=apple/t6040-j614s-sd.dtb
    NEED_MODULES=1
    BRINGUP_DOC=tools/j614s/SD_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    CONTROL_BOOTARGS="$ONE_CPU_ARGS"
    ;;
input)
    KPROFILE=input-thin
    DTB=apple/t6040-j614s-input.dtb
    NEED_MODULES=1
    BRINGUP_DOC=tools/j614s/INPUT_BRINGUP.md
    BOOTARGS="$ONE_CPU_ARGS"
    ;;
power)
    KPROFILE=power-thin
    DTB=apple/t6040-j614s-power.dtb
    NEED_MODULES=1
    BRINGUP_DOC=tools/j614s/POWER_BRINGUP.md
    BOOTARGS="$FOURTEEN_CPU_ARGS"
    CONTROL_BOOTARGS="$ONE_CPU_ARGS"
    ;;
full-diagnostic)
    KPROFILE=diagnostic
    DTB=apple/t6040-j614s-all.dtb
    NEED_MODULES=1
    BOOTARGS="$ONE_CPU_ARGS"
    ;;
full-yolo)
    KPROFILE=yolo
    DTB=apple/t6040-j614s-all.dtb
    NEED_MODULES=1
    BOOTARGS="$ONE_CPU_ARGS"
    ;;
*)
    echo "refusing build: unsupported qualified profile $PROFILE" >&2
    exit 1
    ;;
esac

make ARCH=arm64 LLVM=1 defconfig
sh tools/j614s/ramboot-config.sh "$KPROFILE"
make ARCH=arm64 LLVM=1 olddefconfig

grep -qx 'CONFIG_ARM64_16K_PAGES=y' .config
grep -qx 'CONFIG_SMP=y' .config

case "$PROFILE" in
smp-thin)
    ! grep -Eq '^CONFIG_(PCIE_APPLE|APPLE_DART|MFD_MACSMC|BRCMFMAC|BT_HCIBCM4377|NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
pcie-dart-thin)
    grep -qx 'CONFIG_PCIE_APPLE=y' .config
    grep -qx 'CONFIG_APPLE_DART=y' .config
    ! grep -Eq '^CONFIG_(MFD_MACSMC|BRCMFMAC|BT_HCIBCM4377|NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
smc-thin)
    grep -qx 'CONFIG_PCIE_APPLE=y' .config
    grep -qx 'CONFIG_APPLE_DART=y' .config
    grep -qx 'CONFIG_MFD_MACSMC=y' .config
    ! grep -Eq '^CONFIG_(GPIO_MACSMC|BRCMFMAC|BT_HCIBCM4377|NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
wifi-bt)
    grep -qx 'CONFIG_GPIO_MACSMC=y' .config
    grep -qx 'CONFIG_BRCMFMAC=m' .config
    grep -qx 'CONFIG_BT_HCIBCM4377=m' .config
    ! grep -Eq '^CONFIG_(NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
sd)
    grep -qx 'CONFIG_GPIO_MACSMC=y' .config
    grep -qx 'CONFIG_MMC_SDHCI_PCI=m' .config
    ! grep -Eq '^CONFIG_(BRCMFMAC|BT_HCIBCM4377|NVME_APPLE)=[ym]$' .config
    ;;
input)
    grep -qx 'CONFIG_APPLE_DOCKCHANNEL=m' .config
    grep -qx 'CONFIG_HID_DOCKCHANNEL=m' .config
    ! grep -Eq '^CONFIG_(PCIE_APPLE|MFD_MACSMC|BRCMFMAC|BT_HCIBCM4377|NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
power)
    grep -qx 'CONFIG_MFD_MACSMC=y' .config
    grep -qx 'CONFIG_ARM_APPLE_SOC_CPUFREQ=m' .config
    grep -qx 'CONFIG_MACSMC_POWER=m' .config
    ! grep -Eq '^CONFIG_(GPIO_MACSMC|BRCMFMAC|BT_HCIBCM4377|NVME_APPLE|MMC_SDHCI_PCI)=[ym]$' .config
    ;;
esac

if [ "$NEED_MODULES" = 1 ]; then
    make -j"$(nproc)" ARCH=arm64 LLVM=1 Image modules "$DTB"
else
    make -j"$(nproc)" ARCH=arm64 LLVM=1 Image "$DTB"
fi

gzip -n -9 -c arch/arm64/boot/Image > Image.gz
DTB_PATH="arch/arm64/boot/dts/$DTB"
test -s "$DTB_PATH"

rm -rf ramroot
mkdir -p ramroot/{proc,sys,dev,etc,bin,sbin,run,tmp}

if [ "$NEED_BUSYBOX" = 0 ]; then
    aarch64-linux-gnu-gcc -static -Os -s tools/j614s/ramboot-init.c -o ramroot/init
    readelf -h ramroot/init | grep -q 'Machine:.*AArch64'
else
    BUSYBOX_VERSION=1.38.0
    BUSYBOX_DIR="/tmp/busybox-$BUSYBOX_VERSION-$$"
    mkdir -p "$BUSYBOX_DIR"
    (
        cd "$BUSYBOX_DIR"
        curl -fsSLO "https://busybox.net/downloads/busybox-$BUSYBOX_VERSION.tar.bz2"
        curl -fsSLO "https://busybox.net/downloads/busybox-$BUSYBOX_VERSION.tar.bz2.sha256"
        sha256sum -c "busybox-$BUSYBOX_VERSION.tar.bz2.sha256"
        tar xjf "busybox-$BUSYBOX_VERSION.tar.bz2"
        cd "busybox-$BUSYBOX_VERSION"
        make CROSS_COMPILE=aarch64-linux-gnu- defconfig
        sed -i 's/# CONFIG_STATIC is not set/CONFIG_STATIC=y/' .config
        sed -i 's/CONFIG_TC=y/# CONFIG_TC is not set/' .config
        yes "" | make CROSS_COMPILE=aarch64-linux-gnu- oldconfig >/dev/null
        make -j"$(nproc)" CROSS_COMPILE=aarch64-linux-gnu- busybox
        cp busybox "$SRC/ramroot/bin/busybox"
    )
    chmod 0755 ramroot/bin/busybox
    readelf -h ramroot/bin/busybox | grep -q 'Machine:.*AArch64'
    cp tools/j614s/ramboot-diag.sh ramroot/bin/j614s-diag
    chmod 0755 ramroot/bin/j614s-diag
    cp tools/j614s/ramboot-shell-init.sh ramroot/init
    chmod 0755 ramroot/init
    printf '%s\n' "$PROFILE" > ramroot/etc/j614s-profile
    rm -rf "$BUSYBOX_DIR"

    if [ "$NEED_MODULES" = 1 ]; then
        KREL=$(make -s ARCH=arm64 LLVM=1 kernelrelease)
        make ARCH=arm64 LLVM=1 \
            INSTALL_MOD_PATH="$SRC/ramroot" \
            INSTALL_MOD_STRIP=1 modules_install
        rm -f "ramroot/lib/modules/$KREL/build" "ramroot/lib/modules/$KREL/source"
        depmod -b ramroot "$KREL"
    fi
fi

(
    cd ramroot
    find . -print0 | sort -z | cpio --null -o --format=newc
) | gzip -n -9 > initramfs.cpio.gz

rm -rf "$OUT"
mkdir -p "$OUT"
cp Image.gz "$OUT/Image.gz"
cp initramfs.cpio.gz "$OUT/initramfs.cpio.gz"
cp "$DTB_PATH" "$OUT/t6040-j614s.dtb"
cp .config "$OUT/kernel.config"
cp tools/j614s/tethered-boot.sh "$OUT/BOOT_FROM_HOST.sh"
chmod 0755 "$OUT/BOOT_FROM_HOST.sh"
printf '%s\n' "$PROFILE" > "$OUT/PROFILE.txt"
printf '%s\n' "$QUALIFIED_SHA" > "$OUT/SOURCE_COMMIT.txt"
printf '%s\n' "$BOOTARGS" > "$OUT/BOOTARGS.txt"

if [ -n "$CONTROL_BOOTARGS" ]; then
    printf '%s\n' "$CONTROL_BOOTARGS" > "$OUT/BOOTARGS_CONTROL_1CPU.txt"
fi

if [ -n "$BRINGUP_DOC" ]; then
    cp "$BRINGUP_DOC" "$OUT/BRINGUP.md"
fi

if [ "$NEED_MODULES" = 1 ]; then
    cp tools/j614s/RAMBOOT_LOAD_ORDER.txt "$OUT/LOAD_ORDER.txt"
fi

cat > "$OUT/SOURCE_POLICY.txt" <<EOF
This artifact was built only after the immutable source commit passed
tools/j614s/source_qualify.py from the J614s bring-up matrix.

Profile: $PROFILE
Qualified source commit: $QUALIFIED_SHA

Source qualification includes syntax checks, resolved Kconfig checks, and a
compile-check of this profile's DTB before full kernel/image compilation.
Runtime hardware testing is still required and may reject the artifact.
EOF

(
    cd "$OUT"
    sha256sum * > SHA256SUMS
)
