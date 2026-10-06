#!/bin/sh
# SPDX-License-Identifier: MIT
#
# Expert-only J614s/T6040 bootstrap for a tethered m1n1 development install.
#
# This wrapper intentionally reuses the upstream Asahi installer for APFS,
# stub macOS, Recovery/Preboot, authentication, boot policy, blessing, and
# stage-2 enrollment. It adds J614s admission, AEA BaseSystem handling,
# modern paired-Recovery support, and a tethered m1n1-only install profile.

set -eu

fail()
{
    echo
    echo "ERROR: $*" >&2
    exit 1
}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

MODE=install
case "${1:-}" in
    "") ;;
    --probe) MODE=probe ;;
    --deep-probe) MODE=deep-probe ;;
    --local-probe) MODE=local-probe ;;
    --cleanup-partial) MODE=cleanup-partial ;;
    *)
        echo "usage: $0 [--probe|--deep-probe|--local-probe|--cleanup-partial]" >&2
        exit 2
        ;;
esac

J614S_IPSW_URL="https://updates.cdn-apple.com/2024FallFCS/fullrestores/072-12302/3786987A-AD94-4BFB-81B8-56D3841CA81B/UniversalMac_15.1_24B2083_Restore.ipsw"

ASAHI_VERSION_URL="https://cdn.asahilinux.org/installer/latest"
ASAHI_INSTALLER_BASE="https://cdn.asahilinux.org/installer"

IPSW_TOOL_VERSION="3.1.730"
IPSW_TOOL_ARCHIVE="ipsw_3.1.730_macOS_arm64.tar.gz"
IPSW_TOOL_URL="https://github.com/blacktop/ipsw/releases/download/v3.1.730/$IPSW_TOOL_ARCHIVE"
IPSW_TOOL_SHA256="3f50591e4674daf27d2c82a3e9cd4e37ccaa6297197cb5adc6999571859cd321"

TMP="/tmp/gravity-j614s-installer"

echo
echo "Gravity Linux J614s tethered-development installer"
echo "=================================================="
echo
echo "This is EXPERT-ONLY bring-up tooling for Mac16,8 / J614s / T6040."
echo "It creates an Asahi-style stub boot environment and enrolls m1n1."
echo "It does NOT install a Linux root filesystem and does NOT enable NVMe,"
echo "Wi-Fi, Bluetooth, SD, USB, or other experimental J614s hardware."
echo

[ "$(uname -s)" = "Darwin" ] || fail "this bootstrap must run from macOS"
[ "$(uname -m)" = "arm64" ] || fail "this bootstrap requires Apple silicon"

MODEL=$(sysctl -n hw.model 2>/dev/null || true)
[ "$MODEL" = "Mac16,8" ] || fail "expected Mac16,8, got '$MODEL'"

OS_VERSION=$(sw_vers -productVersion)
OS_MAJOR=$(printf '%s\n' "$OS_VERSION" | awk -F. '{print $1}')
OS_MINOR=$(printf '%s\n' "$OS_VERSION" | awk -F. '{print $2}')
[ "$OS_MAJOR" = "26" ] || fail "this v1 installer is reviewed only for macOS 26.x (found $OS_VERSION)"
[ "$OS_MINOR" -ge 5 ] || fail "macOS 26.5 or newer is required (found $OS_VERSION)"

[ -d /System/Volumes/Data ] || fail "run this from the normal macOS installation"

if [ "$MODE" = "install" ] || [ "$MODE" = "cleanup-partial" ]; then
    if ! pmset -g batt | head -n 1 | grep -q "AC Power"; then
        fail "connect the MacBook to AC power before modifying APFS/boot state"
    fi

    PREEXISTING=$(
        diskutil list 2>/dev/null |
        awk '$0 ~ /APFS Volume m1n1([[:space:]]|$)/ {print $NF}' |
        tr '\n' ' '
    )
    if [ -n "$PREEXISTING" ]; then
        echo
        echo "Found manually-created APFS volume(s) named exactly 'm1n1':"
        for dev in $PREEXISTING; do
            echo "  $dev"
        done
        echo
        echo "This installer deliberately refuses to guess whether they are disposable."
        echo "Remove only the empty test volumes you created manually, then rerun."
        echo "Example (ONLY after verifying the identifier):"
        echo "  diskutil apfs deleteVolume <diskXsY>"
        exit 1
    fi

    if [ "$MODE" = "install" ] && diskutil list 2>/dev/null | grep -Fq "Gravity Linux J614s Dev"; then
        fail "an existing or partial 'Gravity Linux J614s Dev' stub is present; use --cleanup-partial after inspecting it"
    fi

    if [ "$MODE" = "cleanup-partial" ]; then
        echo "Preflight:"
        echo "  Mode:          guarded partial-stub cleanup"
        echo "  Model:         $MODEL"
        echo "  macOS:         $OS_VERSION ($(sw_vers -buildVersion))"
        echo "  Power:         AC"
        echo
    fi

    AVAIL_KB=$(df -k /System/Volumes/Data | awk 'NR==2 {print $4}')
    MIN_KB=$((12 * 1024 * 1024))
    [ "$AVAIL_KB" -ge "$MIN_KB" ] ||
        fail "keep at least 12 GiB free on the macOS APFS container before continuing"

    if [ "$MODE" = "install" ]; then
        echo "Preflight:"
        echo "  Mode:          install"
        echo "  Model:         $MODEL"
        echo "  macOS:         $OS_VERSION ($(sw_vers -buildVersion))"
        echo "  Free space:    $((AVAIL_KB / 1024 / 1024)) GiB"
        echo "  Power:         AC"
    fi
else
    echo "Preflight:"
    if [ "$MODE" = "local-probe" ]; then
        echo "  Mode:          read-only local Tahoe layout probe"
    elif [ "$MODE" = "deep-probe" ]; then
        echo "  Mode:          deep BaseSystem AEA probe (temporary files only)"
    else
        echo "  Mode:          read-only IPSW probe"
    fi
    echo "  Model:         $MODEL"
    echo "  macOS:         $OS_VERSION ($(sw_vers -buildVersion))"
    echo "  Disk changes:  disabled"
fi
echo

echo "Downloading upstream Asahi installer..."
if [ -n "${ASAHI_INSTALLER_VERSION:-}" ]; then
    ASAHI_VERSION="$ASAHI_INSTALLER_VERSION"
else
    ASAHI_VERSION=$(curl -fsSL "$ASAHI_VERSION_URL")
fi
case "$ASAHI_VERSION" in
    ""|*[!A-Za-z0-9._-]*) fail "unexpected Asahi installer version string: '$ASAHI_VERSION'" ;;
esac

PKG="installer-$ASAHI_VERSION.tar.gz"
if [ -e "$TMP" ]; then
    mv "$TMP" "$TMP-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$TMP"
cd "$TMP"

curl -fL --progress-bar -o "$PKG" "$ASAHI_INSTALLER_BASE/$PKG"
tar xzf "$PKG"

[ -x ./install.sh ] || fail "unexpected Asahi installer package layout: install.sh missing"
[ -f ./main.py ] || fail "unexpected Asahi installer package layout: main.py missing"
[ -f ./stub.py ] || fail "unexpected Asahi installer package layout: stub.py missing"
[ -f ./boot/m1n1.bin ] || fail "unexpected Asahi installer package layout: m1n1 missing"

echo
echo "Verifying embedded m1n1 has T6040 support..."
if ! /usr/bin/strings ./boot/m1n1.bin | grep -qi "t6040"; then
    fail "the downloaded Asahi installer m1n1 does not advertise T6040 support"
fi

PY="./Frameworks/Python.framework/Versions/3.13/bin/python3.13"
[ -x "$PY" ] || fail "bundled Asahi Python runtime not found"

# Asahi's packaged Python is relocatable only when its bundled framework path
# is exported, matching src/install.sh.
export DYLD_LIBRARY_PATH="$TMP/Frameworks/Python.framework/Versions/Current/lib"
export DYLD_FRAMEWORK_PATH="$TMP/Frameworks"
export PYTHONPATH="$TMP${PYTHONPATH:+:$PYTHONPATH}"
if [ -f "$TMP/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem" ]; then
    export SSL_CERT_FILE="$TMP/Frameworks/Python.framework/Versions/Current/etc/openssl/cert.pem"
fi

M1N1_VER=$(
    "$PY" -c 'import m1n1; print(m1n1.get_version("boot/m1n1.bin") or "unknown")'
)
echo "  m1n1: $M1N1_VER"

if [ "$MODE" = "cleanup-partial" ]; then
    echo
    "$PY" "$SCRIPT_DIR/cleanup_partial.py"
    exit $?
fi

echo
echo "Checking host firmware / SystemRecovery alignment (read-only)..."
set +e
"$PY" "$SCRIPT_DIR/probe_host.py"
HOST_PROBE_RC=$?
set -e
if [ "$HOST_PROBE_RC" -eq 1 ]; then
    fail "host firmware/Recovery probe could not complete"
fi
if [ "$HOST_PROBE_RC" -ne 0 ] && [ "$MODE" = "install" ]; then
    fail "host firmware/SystemRecovery alignment is not ready for boot-policy work"
fi

if [ "$MODE" = "local-probe" ]; then
    echo
    echo "Inspecting currently working macOS Preboot/paired-Recovery layout (read-only)..."
    "$PY" "$SCRIPT_DIR/probe_local_layout.py"
    exit 0
fi

echo
echo "Probing original J614s macOS 15.1 IPSW and stub plan (read-only)..."
set +e
"$PY" "$SCRIPT_DIR/probe_ipsw.py" "$J614S_IPSW_URL"
PROBE_RC=$?
set -e
if [ "$PROBE_RC" -ne 0 ]; then
    fail "J614s IPSW compatibility probe failed; no installer disk changes are permitted"
fi

if [ "$MODE" = "deep-probe" ]; then
    echo
    echo "Downloading pinned AEA helper for deep probe (blacktop/ipsw v$IPSW_TOOL_VERSION)..."
    curl -fL --progress-bar -o "$IPSW_TOOL_ARCHIVE" "$IPSW_TOOL_URL"
    ACTUAL_SHA=$(/usr/bin/shasum -a 256 "$IPSW_TOOL_ARCHIVE" | awk '{print $1}')
    [ "$ACTUAL_SHA" = "$IPSW_TOOL_SHA256" ] ||
        fail "AEA helper SHA-256 mismatch (got $ACTUAL_SHA)"
    mkdir -p ipsw-tool
    tar xzf "$IPSW_TOOL_ARCHIVE" -C ipsw-tool
    IPSW_AEA_TOOL=$(find "$TMP/ipsw-tool" -type f -name ipsw | head -n 1)
    [ -n "$IPSW_AEA_TOOL" ] || fail "could not find ipsw executable in pinned archive"
    chmod +x "$IPSW_AEA_TOOL"

    echo
    "$PY" "$SCRIPT_DIR/probe_aes_base_system.py"         "$J614S_IPSW_URL" --tool "$IPSW_AEA_TOOL"
    echo
    echo "Deep probe complete. No APFS, boot-policy, or Recovery changes were made."
    exit 0
fi

if [ "$MODE" = "probe" ]; then
    echo
    echo "Read-only probe complete. No APFS, boot-policy, or Recovery changes were made."
    if [ "$HOST_PROBE_RC" -ne 0 ]; then
        fail "IPSW/stub plan is compatible, but host firmware/SystemRecovery alignment blocks installation"
    fi
    exit 0
fi

echo
echo "Downloading pinned AEA helper (blacktop/ipsw v$IPSW_TOOL_VERSION)..."
curl -fL --progress-bar -o "$IPSW_TOOL_ARCHIVE" "$IPSW_TOOL_URL"

ACTUAL_SHA=$(/usr/bin/shasum -a 256 "$IPSW_TOOL_ARCHIVE" | awk '{print $1}')
[ "$ACTUAL_SHA" = "$IPSW_TOOL_SHA256" ] ||
    fail "AEA helper SHA-256 mismatch (got $ACTUAL_SHA)"

mkdir -p ipsw-tool
tar xzf "$IPSW_TOOL_ARCHIVE" -C ipsw-tool
IPSW_AEA_TOOL=$(find "$TMP/ipsw-tool" -type f -name ipsw | head -n 1)
[ -n "$IPSW_AEA_TOOL" ] || fail "could not find ipsw executable in pinned archive"
chmod +x "$IPSW_AEA_TOOL"

echo
echo "Applying J614s/T6040 installer patch..."
"$PY" "$SCRIPT_DIR/patch_installer.py" "$TMP"
"$PY" -m py_compile "$TMP/main.py" "$TMP/stub.py"

cp "$SCRIPT_DIR/installer_data.json" "$TMP/installer_data.json"

echo
echo "Patched installer ready:"
echo "  Asahi installer: $ASAHI_VERSION"
echo "  m1n1:            $M1N1_VER"
echo "  AEA helper:      ipsw v$IPSW_TOOL_VERSION (SHA-256 verified)"
echo "  Target:          Mac16,8 / j614sap / T6040"
echo "  Stub firmware:   macOS 15.1 (24B2083)"
echo "  Recovery model:  paired Preboot/Recovery"
echo "  Profile:         tethered m1n1 proxy only"
echo
echo "The upstream Asahi installer will still ask before resizing or creating"
echo "partitions, and its Recovery step will require your machine-owner approval."
echo

export EXPERT=1
export IPSW_AEA_TOOL
export REPO_BASE="https://cdn.asahilinux.org"
export DISTRO="Gravity Linux J614s Dev"
export DISTRO_DOCS="https://github.com/Aiden-Boyd/gravity-linux"
unset REPORT REPORT_TAG 2>/dev/null || true

if [ "$(id -u)" -ne 0 ]; then
    echo "The installer now needs administrator privileges."
    exec caffeinate -dis sudo -E ./install.sh
else
    exec caffeinate -dis ./install.sh
fi
