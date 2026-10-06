#!/bin/sh
# SPDX-License-Identifier: MIT
# Conservative host-side loader for J614s/T6040 RAM-only bring-up.

set -eu

usage()
{
    cat >&2 <<'EOF'
usage:
  tethered-boot.sh --check <bundle-dir> <m1n1-checkout>
  tethered-boot.sh --boot  <bundle-dir> <m1n1-checkout>

The SAFE profile is accepted by default. To intentionally load diagnostic or
yolo bundles, set J614S_ALLOW_EXPERIMENTAL=YES.
EOF
    exit 2
}

[ "$#" -eq 3 ] || usage
MODE=$1
BUNDLE=$2
M1N1=$3

case "$MODE" in
    --check|--boot) ;;
    *) usage ;;
esac

fail()
{
    echo "ERROR: $*" >&2
    exit 1
}

for f in Image.gz t6040-j614s.dtb initramfs.cpio.gz BOOTARGS.txt PROFILE.txt SHA256SUMS; do
    [ -s "$BUNDLE/$f" ] || fail "missing bundle file: $BUNDLE/$f"
done

[ -f "$M1N1/proxyclient/tools/linux.py" ] ||
    fail "m1n1 checkout is missing proxyclient/tools/linux.py"

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$BUNDLE" && sha256sum -c SHA256SUMS)
elif command -v shasum >/dev/null 2>&1; then
    (cd "$BUNDLE" && shasum -a 256 -c SHA256SUMS)
else
    fail "need sha256sum or shasum to verify the bundle"
fi

gzip -t "$BUNDLE/Image.gz"
gzip -t "$BUNDLE/initramfs.cpio.gz"

PROFILE=$(tr -d '\r\n' < "$BUNDLE/PROFILE.txt")
BOOTARGS=$(tr '\n' ' ' < "$BUNDLE/BOOTARGS.txt" | sed 's/[[:space:]][[:space:]]*/ /g; s/^ //; s/ $//')

case "$PROFILE" in
    safe)
        case " $BOOTARGS " in
            *" nr_cpus=1 "*) ;;
            *) fail "SAFE bundle is missing nr_cpus=1" ;;
        esac
        case " $BOOTARGS " in
            *" maxcpus=1 "*) ;;
            *) fail "SAFE bundle is missing maxcpus=1" ;;
        esac
        ;;
    diagnostic|yolo)
        [ "${J614S_ALLOW_EXPERIMENTAL:-}" = "YES" ] ||
            fail "$PROFILE profile refused; set J614S_ALLOW_EXPERIMENTAL=YES only for intentional staged bring-up"
        ;;
    *)
        fail "unknown profile: $PROFILE"
        ;;
esac

case " $BOOTARGS " in
    *" root="*) fail "RAM-only loader refuses bootargs containing root=" ;;
esac

case " $BOOTARGS " in
    *" panic=0 "*) ;;
    *) fail "bring-up bundle must use panic=0 so kernel panics stay visible on the console" ;;
esac

if command -v dtc >/dev/null 2>&1; then
    DT_TEXT=$(mktemp)
    trap 'rm -f "$DT_TEXT"' EXIT HUP INT TERM
    dtc -q -I dtb -O dts "$BUNDLE/t6040-j614s.dtb" > "$DT_TEXT"
    grep -Eq 'apple,(j614s|t6040)' "$DT_TEXT" ||
        fail "DTB does not advertise J614s/T6040 compatibility"
fi

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
python3 -c 'import serial, construct' >/dev/null 2>&1 ||
    fail "m1n1 Python dependencies missing (install pyserial and construct)"

echo
echo "J614s tethered RAM-boot preflight passed"
echo "  profile:   $PROFILE"
echo "  bundle:    $BUNDLE"
echo "  m1n1:      $M1N1"
echo "  bootargs:  $BOOTARGS"
if [ -n "${M1N1DEVICE:-}" ]; then
    echo "  device:    $M1N1DEVICE"
else
    echo "  device:    auto-detect by m1n1 proxyclient"
fi
echo
echo "No Linux root filesystem will be supplied by this wrapper."

if [ "$MODE" = "--check" ]; then
    echo "Check-only mode complete; target was not contacted."
    exit 0
fi

echo
echo "Starting m1n1 linux.py. This loads the selected kernel, DTB and initramfs"
echo "into RAM on the connected target."
exec python3 "$M1N1/proxyclient/tools/linux.py" \
    -b "$BOOTARGS" \
    "$BUNDLE/Image.gz" \
    "$BUNDLE/t6040-j614s.dtb" \
    "$BUNDLE/initramfs.cpio.gz"
