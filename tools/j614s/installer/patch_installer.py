#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Patch a stock Asahi Linux installer release for expert-only J614s/T6040
bring-up.

This intentionally changes only:
  * T6040/J614s admission in main.py
  * the original macOS 15.1 J614s restore identity
  * AEA BaseSystem handling in stub.py
  * modern paired-Recovery restore-bundle placement when Apple's bless2
    metadata omits the legacy RestoreBundlePath key

Everything else (APFS layout, authentication, Reduced Security setup,
blessing, and stage-2 enrollment) remains the upstream Asahi installer
implementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path


J614S_IPSW_URL = (
    "https://updates.cdn-apple.com/2024FallFCS/fullrestores/072-12302/"
    "3786987A-AD94-4BFB-81B8-56D3841CA81B/"
    "UniversalMac_15.1_24B2083_Restore.ipsw"
)


def insert_before_block_end(
    text: str, start_marker: str, end_marker: str, insertion: str
) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"missing start marker: {start_marker!r}")

    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(
            f"missing end marker after {start_marker!r}: {end_marker!r}"
        )

    if insertion.strip() in text[start:end]:
        return text

    return text[:end] + insertion + text[end:]


def patch_main(path: Path) -> None:
    text = path.read_text()

    text = insert_before_block_end(
        text,
        "CHIP_MIN_VER = {\n",
        "}\n\nDEVICES = {",
        '    0x6040: "15.1",     # T6040, M4 Pro (expert-only J614s bring-up)\n',
    )

    text = insert_before_block_end(
        text,
        "DEVICES = {\n",
        "}\n\n# Asahi Linux does not support running in a virtual machine",
        '    "j614sap": Device("15.1", True), # MacBook Pro (14-inch, M4 Pro, Mac16,8)\n',
    )

    ipsw_entry = f'''    IPSW("15.1",
         "15.1",
         "iBoot-0",
         "0",
         True,
         ["j614sap"],
         "{J614S_IPSW_URL}"),
'''

    text = insert_before_block_end(
        text,
        "IPSW_VERSIONS = [\n",
        "]\n\nclass InstallerMain:",
        ipsw_entry,
    )

    path.write_text(text)


def patch_stub(path: Path) -> None:
    text = path.read_text()

    import_anchor = (
        "import os, os.path, plistlib, shutil, sys, stat, subprocess, "
        "urlcache, zipfile, logging, json, tempfile\n"
    )
    import_replacement = (
        "import os, os.path, plistlib, shutil, sys, stat, subprocess, "
        "urlcache, zipfile, logging, json, tempfile, hashlib\n"
    )
    if import_anchor not in text and import_replacement not in text:
        raise RuntimeError("unexpected stub.py import layout")
    text = text.replace(import_anchor, import_replacement, 1)

    method_marker = "    def install_files(self, cur_os):\n"
    if method_marker not in text:
        raise RuntimeError("missing StubInstaller.install_files marker")

    aea_method = '''    def copy_aea_compress(self, src, path):
        """Decrypt an AEA-wrapped BaseSystem and store it compressed.

        The helper is deliberately external: the bootstrap downloads a pinned
        arm64 build of blacktop/ipsw, verifies its SHA-256, and passes its path
        via IPSW_AEA_TOOL. No tool is installed system-wide.
        """
        tool = os.environ.get("IPSW_AEA_TOOL")
        if not tool or not os.path.isfile(tool):
            raise RuntimeError("IPSW_AEA_TOOL is missing or not a file")

        src = self.path(src)
        info = self.pkg.getinfo(src)

        with tempfile.TemporaryDirectory(prefix="j614s-aea-") as tmp:
            aea_path = os.path.join(tmp, "BaseSystem.dmg.aea")
            with self.pkg.open(src) as sfd, open(aea_path, "wb") as dfd:
                self.fdcopy(sfd, dfd, info.file_size)

            logging.info("Decrypting AEA-wrapped BaseSystem")
            subprocess.run(
                [tool, "fw", "aea", aea_path, "-o", tmp],
                check=True,
            )

            candidates = []
            for root, _dirs, files in os.walk(tmp):
                for name in files:
                    if name.endswith(".dmg"):
                        candidates.append(os.path.join(root, name))

            if len(candidates) != 1:
                raise RuntimeError(
                    f"expected exactly one decrypted BaseSystem DMG, got {candidates!r}"
                )

            dmg = candidates[0]
            sha1 = hashlib.sha1()
            with open(dmg, "rb") as fd:
                while True:
                    data = fd.read(16 * 1024 * 1024)
                    if not data:
                        break
                    sha1.update(data)

            size = os.path.getsize(dmg)
            with open(dmg, "rb") as fd:
                self.stream_compress(fd, size, path, sha1=sha1.digest())

'''

    paired_method = '''    def get_restore_bundle_relpath(self):
        """Return the Preboot-relative restore path and whether it was explicit."""
        bless2 = self.bootcaches.get("bless2")
        if not isinstance(bless2, dict):
            raise RuntimeError("bootcaches.plist has no bless2 dictionary")

        relpath = bless2.get("RestoreBundlePath")
        explicit = relpath is not None

        if relpath is None:
            if not bless2.get("SupportsPairedRecovery"):
                raise RuntimeError(
                    "bless2 has neither RestoreBundlePath nor SupportsPairedRecovery"
                )

            # Modern Apple Silicon bootcaches use paired Recovery and omit
            # RestoreBundlePath. The preserved restore bundle lives at
            # <Preboot>/<VGID>/restore.
            relpath = "restore"

        if not isinstance(relpath, str) or not relpath:
            raise RuntimeError(f"invalid restore bundle path: {relpath!r}")

        relpath = os.path.normpath(relpath)
        if (
            os.path.isabs(relpath)
            or relpath in (".", "..")
            or relpath.startswith("../")
            or "\\x00" in relpath
        ):
            raise RuntimeError(f"unsafe restore bundle path: {relpath!r}")

        return relpath, explicit

'''

    if "    def copy_aea_compress(self, src, path):\n" not in text:
        text = text.replace(method_marker, aea_method + method_marker, 1)

    if "    def get_restore_bundle_relpath(self):\n" not in text:
        text = text.replace(method_marker, paired_method + method_marker, 1)

    old_restore = '''        bless2 = self.bootcaches["bless2"]

        restore_bundle = os.path.join(self.pb_vgid, bless2["RestoreBundlePath"])
        os.makedirs(restore_bundle, exist_ok=True)
'''
    new_restore = '''        restore_relpath, restore_path_explicit = self.get_restore_bundle_relpath()

        restore_bundle = os.path.join(self.pb_vgid, restore_relpath)
        os.makedirs(restore_bundle, exist_ok=True)
'''
    if old_restore not in text and new_restore not in text:
        raise RuntimeError("unexpected restore-bundle layout in stub.py")
    text = text.replace(old_restore, new_restore, 1)

    old_symlink = '''        # This is a workaround for some screwiness in the macOS <12.0 bootability
        # code, which ends up putting the apticket in the wrong volume...
        sys_restore_bundle = os.path.join(self.osi.system, bless2["RestoreBundlePath"])
        if os.path.lexists(sys_restore_bundle):
            os.unlink(sys_restore_bundle)
        os.symlink(restore_bundle, sys_restore_bundle)
'''
    new_symlink = '''        # This symlink is an upstream workaround for legacy bootability metadata.
        # Modern paired-Recovery metadata has no RestoreBundlePath and uses
        # the Preboot <VGID>/restore bundle directly.
        if restore_path_explicit:
            sys_restore_bundle = os.path.join(self.osi.system, restore_relpath)
            if os.path.lexists(sys_restore_bundle):
                os.unlink(sys_restore_bundle)
            os.symlink(restore_bundle, sys_restore_bundle)
'''
    if old_symlink not in text and new_symlink not in text:
        raise RuntimeError("unexpected restore symlink layout in stub.py")
    text = text.replace(old_symlink, new_symlink, 1)

    old_base_system = '''        if self.is_ota:
            self.copy_recompress("AssetData/payloadv2/basesystem_patches/arm64eBaseSystem.dmg",
                                 os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
        else:
            self.copy_compress(identity["Manifest"]["BaseSystem"]["Info"]["Path"],
                               os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
'''

    new_base_system = '''        if self.is_ota:
            self.copy_recompress("AssetData/payloadv2/basesystem_patches/arm64eBaseSystem.dmg",
                                 os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
        else:
            base_system_src = identity["Manifest"]["BaseSystem"]["Info"]["Path"]
            base_system_dst = os.path.join(basesystem_path, "arm64eBaseSystem.dmg")
            if base_system_src.endswith(".aea"):
                self.copy_aea_compress(base_system_src, base_system_dst)
            else:
                self.copy_compress(base_system_src, base_system_dst)
'''

    if old_base_system not in text and new_base_system not in text:
        raise RuntimeError("unexpected BaseSystem extraction layout in stub.py")
    text = text.replace(old_base_system, new_base_system, 1)

    path.write_text(text)


def verify(main_py: Path, stub_py: Path) -> None:
    main = main_py.read_text()
    stub = stub_py.read_text()

    required = [
        '0x6040: "15.1"',
        '"j614sap": Device("15.1", True)',
        'IPSW("15.1"',
        J614S_IPSW_URL,
    ]
    for item in required:
        if item not in main:
            raise RuntimeError(f"main.py verification failed: missing {item!r}")

    for item in (
        "def copy_aea_compress(self, src, path):",
        'os.environ.get("IPSW_AEA_TOOL")',
        'base_system_src.endswith(".aea")',
        "def get_restore_bundle_relpath(self):",
        'bless2.get("SupportsPairedRecovery")',
        'relpath = "restore"',
        "if restore_path_explicit:",
    ):
        if item not in stub:
            raise RuntimeError(f"stub.py verification failed: missing {item!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("installer_root", type=Path)
    args = parser.parse_args()

    root = args.installer_root.resolve()

    # Git checkout layout: <root>/src/main.py
    # Release tarball layout: <root>/main.py
    if (root / "main.py").is_file() and (root / "stub.py").is_file():
        main_py = root / "main.py"
        stub_py = root / "stub.py"
    elif (root / "src/main.py").is_file() and (root / "src/stub.py").is_file():
        main_py = root / "src/main.py"
        stub_py = root / "src/stub.py"
    else:
        raise SystemExit("not an Asahi installer source or release tree")

    patch_main(main_py)
    patch_stub(stub_py)
    verify(main_py, stub_py)

    print("J614s installer patch applied and verified.")


if __name__ == "__main__":
    main()
