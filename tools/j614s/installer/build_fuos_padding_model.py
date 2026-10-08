#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Construct an OFFLINE fuOS padding model from the pinned J614s m1n1 binary.

This is *not* an Image4 file, an installer input, or a bootable image.
It checks the effect on a hypothetical raw payload length if zeros are
appended *after* the standard four-byte m1n1 termination marker.

Never install this experimental candidate or modify existing Preboot files.
"""

import argparse
import hashlib
import json
from pathlib import Path

PINNED_SHA256 = "29c9ac4542577e88e58734075d069835afac1a6b4db8b16b7aa7000942196411"
PINNED_LENGTH = 0x3B0000
PAGE_ALIGNMENT = 0x4000
TERMINATOR = b"\x00" * 4


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_model(source: bytes, *, expected_hash: str = PINNED_SHA256,
               expected_length: int = PINNED_LENGTH) -> tuple[bytes, dict]:
    """Pure model. Override expected_hash/length only in synthetic unit tests."""
    if len(source) != expected_length:
        raise ValueError(f"wrong source length: {len(source)} != {expected_length}")
    actual_hash = sha256(source)
    if actual_hash != expected_hash:
        raise ValueError(f"source SHA256 mismatch: {actual_hash} != {expected_hash}")
    if len(source) % PAGE_ALIGNMENT:
        raise ValueError("source must already be aligned to 16 KiB")

    installed = source + TERMINATOR
    additional_padding = (-len(installed)) % PAGE_ALIGNMENT
    candidate = installed + b"\x00" * additional_padding
    if not additional_padding or additional_padding != PAGE_ALIGNMENT - 4:
        raise ValueError("unexpected terminator/padding relationship")
    if candidate[:len(source)] != source or candidate[len(source):len(installed)] != TERMINATOR:
        raise ValueError("original bytes or four-byte terminator not preserved")
    if any(candidate[len(installed):]):
        raise ValueError("post-terminator padding is not all zero")
    if len(candidate) % PAGE_ALIGNMENT or len(candidate) != len(source) + PAGE_ALIGNMENT:
        raise ValueError("model size does not meet 16 KiB alignment")

    report = {
        "description": "Nonbootable offline size/alignment model, not a signed Image4",
        "source_sha256": actual_hash,
        "source_length": len(source),
        "original_terminator_hex": TERMINATOR.hex(),
        "observed_boot_bin_length": len(installed),
        "observed_boot_bin_sha256": sha256(installed),
        "extra_post_terminator_padding": additional_padding,
        "model_length": len(candidate),
        "model_sha256": sha256(candidate),
        "hypothetical_kcwz_if_kmutil_used_full_model_length": len(candidate),
        "current_conditional_mode1_low12": len(installed) & 0xFFF,
        "model_conditional_mode1_low12": len(candidate) & 0xFFF,
        "alignment": PAGE_ALIGNMENT,
        "status": "Unverified. iBoot translation delta, parsing semantics, runtime path and bootability unknown.",
    }
    return candidate, report


def main() -> None:
    repo_source = Path(__file__).resolve().parents[1] / (
        "m1n1/m1n1-v1.9.9-j614s.4-chainloading.bin")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo_source)
    parser.add_argument("--output", type=Path, required=True,
                        help="scratch candidate file; never point into mounted Preboot")
    parser.add_argument("--report", type=Path, required=True,
                        help="output manifest JSON path")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    if len({source, output, report_path}) != 3:
        parser.error("source/output/report must be three distinct files")
    if any(str(p).startswith("/Volumes/") for p in (output, report_path)):
        parser.error("refusing to write on mounted macOS volumes")

    candidate, manifest = make_model(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or report_path.exists():
        parser.error("output/report already exists; use a fresh scratch location")
    output.write_bytes(candidate)
    report_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("NOT INSTALLABLE: generated raw padding model only; no Image4 packaging performed.")


if __name__ == "__main__":
    main()
