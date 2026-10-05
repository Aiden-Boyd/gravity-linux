#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Patch a stock Asahi Linux installer release for expert-only J614s/T6040
bring-up.

This intentionally changes only:
  * T6040/J614s admission in src/main.py
  * the macOS 26.5.2 J614s restore identity
  * AEA BaseSystem handling in src/stub.py

Everything else (APFS layout, stub OS construction, Preboot/Recovery handling,
authentication, Reduced Security setup, blessing, and stage-2 enrollment)
remains the upstream Asahi installer implementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path


J614S_IPSW_URL = (
    "https://updates.cdn-apple.com/2026SpringFCS/fullrestores/140-24263/"
    "B95838F0-6815-4F0B-A039-156526C081AD/"
    "UniversalMac_26.5.2_25F84_Restore.ipsw"
)


def insert_before_block_end(text: str, start_marker: str, end_marker: str, insertion: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"missing start marker: {start_marker!r}")

    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"missing end marker after {start_marker!r}: {end_marker!r}")

    if insertion.strip() in text[start:end]:
        return text

    return text[:end] + insertion + text[end:]


def patch_main(path: Path) -> None:
    text = path.read_text()

    text = insert_before_block_end(
        text,
        "CHIP_MIN_VER = {\n",
        "}\n\nDEVICES = {",
        '    0x6040: "26.5.2",   # T6040, M4 Pro (expert-only J614s bring-up)\n',
    )

    text = insert_before_block_end(
        text,
        "DEVICES = {\n",
        "}\n\n# Asahi Linux does not support running in a virtual machine",
        '    "j614sap": Device("26.5.2", True), # MacBook Pro (14-inch, M4 Pro, Mac16,8)\n',
    )

    ipsw_entry = f'''    IPSW("26.5.2",
         "26.5.2",
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
        raise RuntimeError("unexpected src/stub.py import layout")
    text = text.replace(import_anchor, import_replacement, 1)

    method_marker = "    def install_files(self, cur_os):\n"
    if method_marker not in text:
        raise RuntimeError("missing StubInstaller.install_files marker")

    method = '''    def copy_aea_compress(self, src, path):
        """Decrypt a macOS 26 AEA-wrapped BaseSystem and store it compressed.

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

    if "    def copy_aea_compress(self, src, path):\n" not in text:
        text = text.replace(method_marker, method + method_marker, 1)

    old = '''        if self.is_ota:
            self.copy_recompress("AssetData/payloadv2/basesystem_patches/arm64eBaseSystem.dmg",
                                 os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
        else:
            self.copy_compress(identity["Manifest"]["BaseSystem"]["Info"]["Path"],
                               os.path.join(basesystem_path, "arm64eBaseSystem.dmg"))
'''

    new = '''        if self.is_ota:
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

    if old not in text and new not in text:
        raise RuntimeError("unexpected BaseSystem extraction layout in src/stub.py")
    text = text.replace(old, new, 1)

    path.write_text(text)


def verify(root: Path) -> None:
    main = (root / "src/main.py").read_text()
    stub = (root / "src/stub.py").read_text()

    required = [
        '0x6040: "26.5.2"',
        '"j614sap": Device("26.5.2", True)',
        'IPSW("26.5.2"',
        J614S_IPSW_URL,
    ]
    for item in required:
        if item not in main:
            raise RuntimeError(f"main.py verification failed: missing {item!r}")

    for item in (
        "def copy_aea_compress(self, src, path):",
        'os.environ.get("IPSW_AEA_TOOL")',
        'base_system_src.endswith(".aea")',
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
    verify(root)

    print("J614s installer patch applied and verified.")


if __name__ == "__main__":
    main()
