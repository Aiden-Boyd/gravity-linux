#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""T6040/J614s GPU ADT inventory collector.

The collector is GPU-read-only: it does not enable GPU power, access GPU/ASC
MMIO, start firmware, write NVRAM, or write persistent storage. Offline mode
only parses a captured ADT. Live mode uses m1n1's proxy helpers, which may
allocate transient proxy scratch/heap memory while retrieving the existing ADT.
"""

import argparse
import hashlib
import json
import pathlib
import sys

GPU_NODE_PATHS = ("/arm-io/sgx", "/arm-io/gfx-asc")
GPU_WORDS = ("gpu", "gfx", "sgx", "agx", "uat", "dart")
PMGR_WORDS = ("gpu", "gfx", "sgx", "agx", "gpx", "afr")
SELECTED_SGX_PROPS = (
    "compatible", "interrupts", "perf-state-count", "perf-state-table-count",
    "gpu-num-perf-states", "metal-standard", "opengl-standard",
    "agx-address-space-mgmt-mode", "has-kf",
    "gpu-region-base", "gpu-region-size",
    "gfx-handoff-base", "gfx-handoff-size",
    "gfx-shared-region-base", "gfx-shared-region-size",
    "gfx-shared-l2-region-base", "gfx-shared-l2-region-size",
    "gfx-data-base", "gfx-data-size",
    "rtkit-private-vm-region-base", "rtkit-private-vm-region-size",
)


def add_m1n1_path(path):
    root = pathlib.Path(path).expanduser().resolve()
    proxyclient = root / "proxyclient"
    if not proxyclient.is_dir():
        raise SystemExit(f"m1n1 proxyclient directory not found: {proxyclient}")
    sys.path.insert(0, str(proxyclient))


def plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"hex": value.hex(), "length": len(value)}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if hasattr(value, "items"):
        try:
            return {str(k): plain(v) for k, v in value.items()}
        except Exception:
            pass
    if isinstance(value, (list, tuple)) or (
        hasattr(value, "__iter__") and not isinstance(value, str)
    ):
        try:
            return [plain(v) for v in value]
        except Exception:
            pass
    return str(value)


def translated_regs(node):
    regs = getattr(node, "reg", None)
    if not isinstance(regs, list):
        return []
    out = []
    for idx in range(len(regs)):
        try:
            addr, size = node.get_reg(idx)
            out.append({"index": idx, "base": addr, "size": size})
        except Exception as exc:
            out.append({"index": idx, "error": str(exc)})
    return out


def node_snapshot(node, selected_props=None):
    if selected_props is None:
        props = node._properties
    else:
        props = {k: node.getprop(k) for k in selected_props if k in node._properties}
    return {
        "path": node._path,
        "name": node.name,
        "regs_translated": translated_regs(node),
        "properties": plain(props),
    }


def relevant_arm_io_nodes(dt):
    out = []
    for node in dt["/arm-io"]:
        compatibles = getattr(node, "compatible", [])
        if isinstance(compatibles, str):
            compatibles = [compatibles]
        haystack = " ".join([node.name, *map(str, compatibles)]).lower()
        if any(word in haystack for word in GPU_WORDS):
            out.append(node_snapshot(node))
    return out


def relevant_pmgr(dt):
    pmgr = dt[dt._pmgr_path]
    pd_by_id = {
        getattr(pd, "id", None): getattr(pd, "name", None)
        for pd in getattr(pmgr, "power_domains", [])
    }
    dev_by_id = {}
    for dev in getattr(pmgr, "devices", []):
        try:
            dev_by_id[dt.pmgr_dev_get_id(dev)] = dev
        except Exception:
            pass

    out = []
    for dev_id, dev in dev_by_id.items():
        name = str(getattr(dev, "name", ""))
        if not any(word in name.lower() for word in PMGR_WORDS):
            continue
        entry = {
            "name": name,
            "id": dev_id,
            "power_domain_id": getattr(dev, "pd", None),
            "power_domain_name": pd_by_id.get(getattr(dev, "pd", None)),
            "parents": [],
        }
        try:
            entry["parents"] = [
                {"id": pid, "name": getattr(dev_by_id.get(pid), "name", None)}
                for pid in dt.pmgr_dev_get_parents(dev)
                if pid
            ]
        except Exception as exc:
            entry["parents_error"] = str(exc)
        try:
            base, size = dt.pmgr_dev_get_block(dev)
            entry["block"] = {"base": base, "size": size}
            entry["offset"] = dt.pmgr_dev_get_offset(dev)
            entry["control_address"] = dt.pmgr_dev_get_addr(dev)
        except Exception as exc:
            entry["mapping_error"] = str(exc)
        out.append(entry)
    return out


def load_offline(path):
    from m1n1 import adt

    data = pathlib.Path(path).read_bytes()
    return adt.load_adt(data), data


def load_live():
    # Do not import m1n1.setup: it resets the panic counter as a side effect.
    from m1n1.proxy import M1N1Proxy, UartInterface
    from m1n1.proxyutils import ProxyUtils, bootstrap_port

    iface = UartInterface()
    proxy = M1N1Proxy(iface, debug=False)
    bootstrap_port(iface, proxy)
    utils = ProxyUtils(proxy)
    dt = utils.adt
    _ = dt["/chosen"]  # force LazyADT parse; no GPU MMIO or power operation
    return dt, getattr(utils, "adt_data", None)


def main():
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--adt", type=pathlib.Path, help="captured Apple ADT file")
    src.add_argument("--live", action="store_true",
                     help="retrieve the current ADT through m1n1; GPU MMIO/power remain untouched")
    parser.add_argument("--m1n1", type=pathlib.Path, required=True,
                        help="path to an m1n1 source checkout")
    parser.add_argument("-o", "--output", type=pathlib.Path,
                        default=pathlib.Path("j614s-t6040-gpu-adt.json"))
    args = parser.parse_args()

    add_m1n1_path(args.m1n1)
    if args.adt:
        dt, adt_data = load_offline(args.adt)
        source = {"mode": "offline", "path": str(args.adt)}
    else:
        dt, adt_data = load_live()
        source = {"mode": "live-m1n1-proxy"}

    nodes = {}
    for path in GPU_NODE_PATHS:
        try:
            node = dt[path]
        except KeyError:
            nodes[path] = {"missing": True}
            continue
        props = SELECTED_SGX_PROPS if path.endswith("/sgx") else None
        nodes[path] = node_snapshot(node, props)

    report = {
        "schema_version": 1,
        "safety": {
            "gpu_read_only_inventory": True,
            "proxy_may_allocate_transient_memory": bool(args.live),
            "powers_gpu": False,
            "reads_gpu_mmio": False,
            "writes_gpu_mmio": False,
            "starts_gpu_firmware": False
        },
        "source": source,
        "chip_id": dt["/chosen"].getprop("chip-id"),
        "nodes": nodes,
        "related_arm_io_nodes": relevant_arm_io_nodes(dt),
        "pmgr_gpu_related": relevant_pmgr(dt),
    }

    if adt_data:
        report["source"]["adt_sha256"] = hashlib.sha256(adt_data).hexdigest()
        report["source"]["adt_size"] = len(adt_data)

    args.output.write_text(json.dumps(plain(report), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
