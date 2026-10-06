#!/bin/sh
# SPDX-License-Identifier: MIT
# Conservative host-side loader for J614s/T6040 RAM-only bring-up.

set -eu

EXPECTED_M1N1_VERSION="v1.9.9"
EXPECTED_M1N1_COMMIT="809541515659bf4e504807fd72bc0a539be5eee7"

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

command -v git >/dev/null 2>&1 || fail "git is required to verify the m1n1 checkout"
M1N1_HEAD=$(git -C "$M1N1" rev-parse HEAD 2>/dev/null) ||
    fail "m1n1 path must be a git checkout of $EXPECTED_M1N1_VERSION"
[ "$M1N1_HEAD" = "$EXPECTED_M1N1_COMMIT" ] ||
    fail "m1n1 checkout mismatch: expected $EXPECTED_M1N1_VERSION ($EXPECTED_M1N1_COMMIT), got $M1N1_HEAD"
git -C "$M1N1" diff --quiet -- proxyclient m1n1 ||
    fail "m1n1 checkout has modified proxyclient/m1n1 files; use a clean $EXPECTED_M1N1_VERSION checkout"
git -C "$M1N1" diff --cached --quiet -- proxyclient m1n1 ||
    fail "m1n1 checkout has staged proxyclient/m1n1 changes; use a clean $EXPECTED_M1N1_VERSION checkout"

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
    safe) ;;
    diagnostic|yolo)
        [ "${J614S_ALLOW_EXPERIMENTAL:-}" = "YES" ] ||
            fail "$PROFILE profile refused; set J614S_ALLOW_EXPERIMENTAL=YES only for intentional staged bring-up"
        ;;
    *)
        fail "unknown profile: $PROFILE"
        ;;
esac

# Every current J614s profile is deliberately single-CPU. Exact-model testing
# has a reproducible T6040 multi-core page-copy/MM fault, so SMP gets its own
# future diagnostic profile instead of being enabled accidentally.
for required_arg in nr_cpus=1 maxcpus=1 idle=nop arm64.nowfxt panic=0; do
    case " $BOOTARGS " in
        *" $required_arg "*) ;;
        *) fail "$PROFILE bundle is missing required M4 bring-up argument: $required_arg" ;;
    esac
done

case " $BOOTARGS " in
    *" root="*) fail "RAM-only loader refuses bootargs containing root=" ;;
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
M1N1_SHORT=$(printf '%.12s' "$M1N1_HEAD")
echo "  m1n1:      $M1N1 ($EXPECTED_M1N1_VERSION / $M1N1_SHORT)"
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
