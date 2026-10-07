#!/bin/sh
# SPDX-License-Identifier: MIT
# Final bundle QA for J614s qualified bring-up images.
set -eu

PROFILE=${1:?usage: artifact_qa.sh <profile> <source-sha> <artifact-dir> <manifest> <qualification-json>}
SOURCE_SHA=${2:?missing source sha}
OUT=$(cd "${3:?missing artifact dir}" && pwd)
MANIFEST=${4:?missing manifest}
QUAL=${5:?missing qualification json}

fail()
{
    echo "ARTIFACT QA FAILED [$PROFILE]: $*" >&2
    exit 1
}

for f in Image.gz initramfs.cpio.gz t6040-j614s.dtb kernel.config          BOOT_FROM_HOST.sh PROFILE.txt SOURCE_COMMIT.txt BOOTARGS.txt          SOURCE_POLICY.txt SOURCE_QUALIFICATION.json BRINGUP_IMAGE_MATRIX.json          TEST_ORDER.json SHA256SUMS; do
    [ -s "$OUT/$f" ] || fail "missing/empty $f"
done

[ "$(cat "$OUT/PROFILE.txt")" = "$PROFILE" ] || fail "PROFILE.txt mismatch"
[ "$(cat "$OUT/SOURCE_COMMIT.txt")" = "$SOURCE_SHA" ] || fail "SOURCE_COMMIT mismatch"
[ -x "$OUT/BOOT_FROM_HOST.sh" ] || fail "host boot helper is not executable"

# Hashes must describe the final uploaded set, excluding the manifest itself.
(
    cd "$OUT"
    grep -v '  SHA256SUMS$' SHA256SUMS | sha256sum -c -
) || fail "SHA256SUMS verification failed"

python3 - "$PROFILE" "$SOURCE_SHA" "$OUT" "$MANIFEST" "$QUAL" <<'PY'
import json, pathlib, sys
profile, sha, out_s, manifest_s, qual_s = sys.argv[1:]
out = pathlib.Path(out_s)
manifest = json.loads(pathlib.Path(manifest_s).read_text())
qual = json.loads(pathlib.Path(qual_s).read_text())
bundled_qual = json.loads((out / "SOURCE_QUALIFICATION.json").read_text())
bundled_manifest = json.loads((out / "BRINGUP_IMAGE_MATRIX.json").read_text())
order = json.loads((out / "TEST_ORDER.json").read_text())

p = next((x for x in manifest["profiles"] if x["id"] == profile), None)
assert p is not None, f"{profile}: absent from manifest"
assert p["build_enabled"] is True
assert p["source_commit"] == sha
assert qual["profile"] == profile
assert qual["source_commit"] == sha
assert qual["qualified"] is True
assert bundled_qual == qual
assert bundled_manifest == manifest
assert order["profile"] == profile
assert order["order"] == p["order"]
assert order["purpose"] == p["purpose"]
assert order["boot_after"] == p["boot_after"]
assert order["risk"] == p["risk"]

bootargs = (out / "BOOTARGS.txt").read_text().strip().split()
assert "panic=0" in bootargs
assert "idle=nop" in bootargs
assert "arm64.nowfxt" in bootargs
assert not any(x.startswith("root=") for x in bootargs), "persistent root= unexpectedly present"
assert "rw" not in bootargs, "rw boot argument unexpectedly present"

one_cpu = {"safe", "full-diagnostic", "full-yolo", "input"}
if profile in one_cpu:
    assert "nr_cpus=1" in bootargs
    assert "maxcpus=1" in bootargs
else:
    assert "maxcpus=14" in bootargs
    assert "nr_cpus=1" not in bootargs

control = out / "BOOTARGS_CONTROL_1CPU.txt"
if profile in {"pcie-dart-thin", "smc-thin", "wifi-bt", "sd", "power"}:
    assert control.is_file(), f"{profile}: one-CPU control bootargs missing"
    words = control.read_text().strip().split()
    assert "nr_cpus=1" in words and "maxcpus=1" in words
else:
    assert not control.exists(), f"{profile}: unexpected control bootargs"

cfg = (out / "kernel.config").read_text()
def enabled(sym, state="y"):
    return f"{sym}={state}" in cfg.splitlines()
def forbidden(sym):
    return enabled(sym, "y") or enabled(sym, "m")

assert enabled("CONFIG_ARM64_16K_PAGES")
assert enabled("CONFIG_SMP")

if profile == "safe":
    for s in ("CONFIG_PCIE_APPLE","CONFIG_APPLE_DART","CONFIG_MFD_MACSMC","CONFIG_NVME_APPLE"):
        assert not forbidden(s), f"{profile}: {s} unexpectedly enabled"
elif profile == "smp-thin":
    for s in ("CONFIG_PCIE_APPLE","CONFIG_APPLE_DART","CONFIG_MFD_MACSMC","CONFIG_NVME_APPLE"):
        assert not forbidden(s), f"{profile}: {s} unexpectedly enabled"
elif profile == "pcie-dart-thin":
    assert enabled("CONFIG_PCIE_APPLE") and enabled("CONFIG_APPLE_DART")
    assert not forbidden("CONFIG_MFD_MACSMC")
elif profile == "smc-thin":
    assert enabled("CONFIG_PCIE_APPLE") and enabled("CONFIG_APPLE_DART")
    assert enabled("CONFIG_MFD_MACSMC")
    assert not forbidden("CONFIG_GPIO_MACSMC")
elif profile == "wifi-bt":
    assert enabled("CONFIG_GPIO_MACSMC")
    assert enabled("CONFIG_BRCMFMAC","m")
    assert enabled("CONFIG_BT_HCIBCM4377","m")
    assert not forbidden("CONFIG_MMC_SDHCI_PCI")
elif profile == "sd":
    assert enabled("CONFIG_GPIO_MACSMC")
    assert enabled("CONFIG_MMC_SDHCI_PCI","m")
    assert not forbidden("CONFIG_BRCMFMAC")
elif profile == "input":
    assert enabled("CONFIG_APPLE_DOCKCHANNEL","m")
    assert enabled("CONFIG_HID_DOCKCHANNEL","m")
    assert not forbidden("CONFIG_PCIE_APPLE")
    assert not forbidden("CONFIG_MFD_MACSMC")
elif profile == "power":
    assert enabled("CONFIG_MFD_MACSMC")
    assert enabled("CONFIG_ARM_APPLE_SOC_CPUFREQ","m")
    assert enabled("CONFIG_MACSMC_POWER","m")
    assert not forbidden("CONFIG_GPIO_MACSMC")
elif profile == "full-diagnostic":
    for s in ("CONFIG_APPLE_DART","CONFIG_PCIE_APPLE","CONFIG_MFD_MACSMC",
              "CONFIG_BRCMFMAC","CONFIG_BT_HCIBCM4377","CONFIG_MMC_SDHCI_PCI"):
        assert enabled(s,"m"), f"{profile}: {s} is not modular"
elif profile == "full-yolo":
    for s in ("CONFIG_APPLE_DART","CONFIG_PCIE_APPLE","CONFIG_MFD_MACSMC",
              "CONFIG_BRCMFMAC","CONFIG_BT_HCIBCM4377","CONFIG_MMC_SDHCI_PCI"):
        assert enabled(s,"y"), f"{profile}: {s} is not built-in"
PY

# Initramfs must actually contain its expected userspace.
TMP_LIST=$(mktemp)
trap 'rm -f "$TMP_LIST"' EXIT
gzip -dc "$OUT/initramfs.cpio.gz" | cpio -it 2>/dev/null > "$TMP_LIST" ||
    fail "cannot enumerate initramfs"
grep -Eq '^(\./)?init$' "$TMP_LIST" || fail "initramfs lacks /init"

if [ "$PROFILE" = safe ]; then
    ! grep -Eq '^(\./)?bin/busybox$' "$TMP_LIST" || fail "SAFE unexpectedly contains BusyBox"
else
    grep -Eq '^(\./)?bin/busybox$' "$TMP_LIST" || fail "interactive image lacks BusyBox"
    grep -Eq '^(\./)?bin/j614s-diag$' "$TMP_LIST" || fail "interactive image lacks j614s-diag"
fi

# Final DTB isolation checks.
status()
{
    fdtget -t s "$OUT/t6040-j614s.dtb" "$1" status 2>/dev/null || echo missing
}

case "$PROFILE" in
safe|smp-thin|input)
    [ "$(status /soc/pcie@1cb0000000)" = disabled ] || fail "PCIe should be disabled"
    [ "$(status /soc/smc@50c600000)" = disabled ] || fail "SMC should be disabled"
    ;;
pcie-dart-thin)
    [ "$(status /soc/pcie@1cb0000000)" = okay ] || fail "PCIe root should be enabled"
    [ "$(status /soc/smc@50c600000)" = disabled ] || fail "SMC should be disabled"
    ;;
smc-thin|power)
    [ "$(status /soc/pcie@1cb0000000)" = okay ] || fail "PCIe root should be enabled"
    [ "$(status /soc/smc@50c600000)" = okay ] || fail "SMC should be enabled"
    ;;
wifi-bt|sd|full-diagnostic|full-yolo)
    [ "$(status /soc/pcie@1cb0000000)" = okay ] || fail "PCIe root should be enabled"
    [ "$(status /soc/smc@50c600000)" = okay ] || fail "SMC should be enabled"
    ;;
esac

echo "ARTIFACT_QA_PASS $PROFILE $SOURCE_SHA"
