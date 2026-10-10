#!/bin/bash
# SPDX-License-Identifier: MIT
# macOS preparation only: no partitioning, formatting, or boot-policy changes.
set -eu
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin
[ "$(uname -s)" = Darwin ] && [ "$(sysctl -n hw.model)" = Mac16,8 ] || {
  echo "This script is only for the J614s Mac16,8."; exit 1;
}
desktop=${1:-"$HOME/Desktop"}
[ -d "$desktop" ] || { echo "Desktop directory missing."; exit 1; }
work=$(mktemp -d "$desktop/gravity-boot-check.XXXXXX")
report="$work/report.txt"
data_uuid=1B517D62-C96F-4CC6-BD52-6320F1AC845D
system_uuid=7BB3DC62-3D93-4B51-8D8B-A922DE5E5CCB
preboot_uuid=F6046501-3B40-4329-95AB-684C11AD6B1B
for uuid in "$data_uuid" "$system_uuid" "$preboot_uuid"; do
  diskutil mount "$uuid" >> "$report" 2>&1 || true
done
mountpoint() {
  diskutil info -plist "$1" | plutil -extract MountPoint raw -o - -
}
data=$(mountpoint "$data_uuid")
system=$(mountpoint "$system_uuid")
preboot=$(mountpoint "$preboot_uuid")
[ -d "$data" ] && [ -d "$system" ] && [ -d "$preboot" ]
stage="$data/boot-check"
mkdir -p "$stage"
{
  echo "GRAVITY BOOT CHECK — $(date -u)"
  sw_vers
  sysctl hw.model
  diskutil list internal
  for uuid in "$data_uuid" "$system_uuid" "$preboot_uuid"; do diskutil info "$uuid"; done
  echo "BOOT FOLDER POINTER"
  cat "$preboot/$data_uuid/boot/active" || true
  echo
  echo "BOOT OBJECTS: sizes, hashes, first 96 bytes"
  find "$preboot/$data_uuid" -type f -name 'kernelcache.custom.*' -print |
  while IFS= read -r file; do
    ls -ln "$file"
    shasum -a 256 "$file"
    od -An -tx1 -N96 "$file"
  done
  echo "STAGED PAYLOAD"
  if [ -f "$data/standalone/gravity-standalone.bin" ]; then
    ls -ln "$data/standalone/gravity-standalone.bin"
    shasum -a 256 "$data/standalone/gravity-standalone.bin"
    cat "$data/standalone/gravity-standalone.bin.sha256" || true
  fi
} >> "$report" 2>&1
mkdir -p "$work/panics"
find /Library/Logs/DiagnosticReports -maxdepth 1 -type f -name '*socd*.panic' -exec cp {} "$work/panics/" \; 2>> "$report" || true
# Recovery helper collects its current policy and fresh report before any reboot.
cat > "$stage/recovery.sh" <<'RECOVERY'
#!/bin/sh
set -eu
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
[ "$(sysctl -n hw.model)" = Mac16,8 ]
diskutil mount 1B517D62-C96F-4CC6-BD52-6320F1AC845D
data=$(diskutil info -plist 1B517D62-C96F-4CC6-BD52-6320F1AC845D | plutil -extract MountPoint raw -o - -)
out="$data/boot-check/recovery-report"
mkdir -p "$out"
find /Library/Logs/DiagnosticReports -type f -name '*socd*.panic' -exec cp {} "$out/" \;
bputil -d > "$out/boot-policy.txt" 2>&1 || true
ls -lh "$out"
sync
echo "Report saved on Gravity Data. Boot Macintosh HD and upload the files in boot-check/recovery-report."
RECOVERY
# Stage a separately named diagnostic payload only when authenticated gh is available.
# Reuse the existing tested Linux/DT/initramfs bytes; change only the m1n1 prefix.
if command -v gh >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  mkdir -p "$work/diagnostic-build"
  if gh run download 38051370707 -R Aiden-Boyd/gravity-linux -n j614s-m1n1-ssd -D "$work/diagnostic-build" >> "$report" 2>&1; then
    if python3 - "$data/standalone/gravity-standalone.bin" "$work/diagnostic-build" "$stage" >> "$report" 2>&1 <<'PY'
import hashlib, pathlib, sys
source, build, stage = map(pathlib.Path, sys.argv[1:])
def checked(path, expected):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected.lower(): raise SystemExit("Checksum mismatch: "+str(path))
    return data
expected=source.with_suffix(".bin.sha256").read_text().split()[0]
old=checked(source, expected)
for line in (build/"SHA256SUMS").read_text().splitlines():
    digest, name=line.split(None,1)
    name=name.strip().lstrip("*")
    if pathlib.Path(name).name!=name: raise SystemExit("Invalid artifact manifest")
    checked(build/name,digest)
base=(build/"m1n1.bin").read_bytes()
if b"J614S_SSD_DIAG:" not in base or b"J614S_SSD_PAYLOAD:" not in base: raise SystemExit("Wrong diagnostic build")
marker=b"chosen.bootargs="
offset=old.find(marker)
if offset<0x800 or old.count(marker)!=1: raise SystemExit("Cannot safely identify payload boundary")
newline=old.find(b"\n",offset)
if newline<0 or old[newline+1:newline+5]!=b"\xd0\x0d\xfe\xed": raise SystemExit("DTB boundary mismatch")
new=base+old[offset:]
out=stage/"gravity-diagnostic.bin"
out.write_bytes(new)
out.with_suffix(".bin.sha256").write_text(hashlib.sha256(new).hexdigest()+"  "+out.name+"\n")
print("Diagnostic payload staged:",out,len(new),"bytes")
PY
    then
      echo "Diagnostic payload verification passed." >> "$report"
    else
      rm -f "$stage/gravity-diagnostic.bin" "$stage/gravity-diagnostic.bin.sha256"
      echo "Diagnostic staging failed; no payload will be installed." >> "$report"
    fi
  fi
fi
cp "$report" "$stage/macos-report.txt"
cp "$stage/recovery.sh" "$work/"
if [ -f "$stage/gravity-diagnostic.bin" ]; then
  echo "Diagnostic payload staged; it has NOT been installed."
else
  echo "Boot report and Recovery helper staged. Diagnostic build was not downloaded; see report."
fi
tar -czf "$desktop/gravity-boot-check.tgz" -C "$work" .
if [ -n "${SUDO_UID:-}" ]; then
  chown -R "$SUDO_UID:${SUDO_GID}" "$work" "$desktop/gravity-boot-check.tgz"
fi
echo "DONE. Upload $desktop/gravity-boot-check.tgz to this chat."
echo "No boot policy was changed. Stay in macOS."
