#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
if [[ $# != 2 ]]; then
  echo "Usage: bash $0 /path/to/static-arm64-busybox output-directory" >&2
  exit 2
fi
busybox_path=$(realpath "$1")
output_path=$(realpath -m "$2")
repo_root=$(git rev-parse --show-toplevel)
init_path="$repo_root/tools/j614s/init"
for path in "$busybox_path" "$output_path" "$repo_root"; do
  if [[ "$path" =~ [[:space:]] ]]; then
    echo 'CPIO list paths must not contain whitespace' >&2
    exit 2
  fi
done
readelf -h "$busybox_path" | grep -q 'Machine:.*AArch64'
if readelf -l "$busybox_path" | grep -q INTERP; then
  echo 'BusyBox must be statically linked' >&2
  exit 1
fi
for applet in sh mount dmesg cat setsid cttyhack sleep; do
  "$busybox_path" --list | grep -qx "$applet"
done
"$busybox_path" sh -n "$init_path"
mkdir -p "$output_path"
work_path=$(mktemp -d)
trap 'rm -rf "$work_path"' EXIT
cc -O2 -Wall -Wextra "$repo_root/usr/gen_init_cpio.c" -o "$work_path/gen_init_cpio"
{
  for directory in bin sbin dev proc sys run tmp root; do
    mode=0755
    [[ "$directory" == tmp ]] && mode=1777
    [[ "$directory" == root ]] && mode=0700
    printf 'dir /%s %s 0 0\n' "$directory" "$mode"
  done
  printf 'nod /dev/console 0600 0 0 c 5 1\n'
  printf 'nod /dev/null 0666 0 0 c 1 3\n'
  printf 'file /bin/busybox %s 0755 0 0\n' "$busybox_path"
  printf 'file /init %s 0755 0 0\n' "$init_path"
  while IFS= read -r applet; do
    [[ "$applet" == busybox ]] && continue
    printf 'slink /bin/%s busybox 0777 0 0\n' "$applet"
  done < <("$busybox_path" --list)
} > "$output_path/initramfs.list"
"$work_path/gen_init_cpio" -t 0 "$output_path/initramfs.list" | gzip -n -9 > "$output_path/initramfs.cpio.gz"
cp "$init_path" "$output_path/init"
git -C "$repo_root" rev-parse HEAD > "$output_path/source-commit.txt"
(cd "$output_path" && sha256sum initramfs.cpio.gz init > SHA256SUMS)
