#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Apply the reviewed J614s/T6040 deltas to the exact AsahiLinux/m1n1 v1.9.9
source tree (809541515659bf4e504807fd72bc0a539be5eee7).

Provenance: adapted from Project Wallace's hardware-verified J614s patch
series by CJ Damsleth, especially patches 1, 3, 5, 6, and 8 of
m1n1-t6040-upstream-v1. This script deliberately omits watchdog, display,
storage, and USB policy changes. Upstream v1.9.9 already carries the
hardware-proven T6040 PCIe reset-bit fix; the guarded stage1 runs that PCIe
path only when the supplied Linux DT explicitly enables apple,t6040-pcie.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("m1n1")

def edit(path, old, new):
    p = root / path
    s = p.read_text()
    if s.count(old) != 1:
        raise SystemExit(f"{path}: expected one exact patch anchor, got {s.count(old)}")
    p.write_text(s.replace(old, new, 1))

# M4 WFI loses architectural state: mark the feature and park secondaries in WFE.
edit("src/utils.h",
"""    bool actlr_el2;
    bool counter_redirect;
};
""",
"""    bool actlr_el2;
    bool counter_redirect;
    bool broken_wfi;
};
""")
edit("src/chickens.c",
"""const struct midr_part_features features_m4 = {
    .sleep_mode = SLEEP_NONE, // XXX probably new mode required
    .fast_ipi = true,
    .actlr_el2 = true,
};
""",
"""const struct midr_part_features features_m4 = {
    .sleep_mode = SLEEP_NONE, // XXX probably new mode required
    .fast_ipi = true,
    .actlr_el2 = true,
    .broken_wfi = true,
};
""")
edit("proxyclient/m1n1/proxy.py",
'''    "counter_redirect" / bool_,
    "padding" / Bytes(1),
)
''',
'''    "counter_redirect" / bool_,
    "broken_wfi" / bool_,
)
''')
edit("src/smp.c",
"""void smp_start_secondaries(void)
{
    printf("Starting secondary CPUs...\\n");

    if (!smp_initialized)
""",
"""void smp_start_secondaries(void)
{
    printf("Starting secondary CPUs...\\n");

    if (cpu_features->broken_wfi && !wfe_mode) {
        printf("smp: broken WFI on this SoC, parking secondaries in WFE\\n");
        wfe_mode = true;
    }

    if (!smp_initialized)
""")
edit("src/smp.c",
"""void smp_set_wfe_mode(bool new_mode)
{
    wfe_mode = new_mode;
""",
"""void smp_set_wfe_mode(bool new_mode)
{
    if (cpu_features->broken_wfi && !new_mode) {
        printf("smp: refusing to disable WFE mode, WFI is broken on this SoC\\n");
        return;
    }

    wfe_mode = new_mode;
""")

# First-boot isolation without breaking the later diagnostic profile.
# Upstream v1.9.9's T6040 PCIe path contains the hardware-proven BIT(4)
# PHY-reset fix used successfully on J614s. SAFE keeps the Linux PCIe node
# disabled, so stage1 must not touch PCIe. Diagnostic/yolo explicitly enable
# apple,t6040-pcie and therefore request the proven one-shot m1n1 handoff.
edit("src/kboot.c",
"""int kboot_boot(void *kernel)
{
""",
"""static bool t6040_pcie_requested(void)
{
    int node = fdt_node_offset_by_compatible(dt, -1, "apple,t6040-pcie");
    int len = 0;
    const char *status;

    if (node < 0)
        return false;

    status = fdt_getprop(dt, node, "status", &len);
    return !status || !strcmp(status, "okay") || !strcmp(status, "ok");
}

int kboot_boot(void *kernel)
{
""")
edit("src/kboot.c",
"""    usb_init();
    pcie_init();
    dapf_init_all();
""",
"""    usb_init();
    if (chip_id == T6040 && !t6040_pcie_requested()) {
        printf("pcie: T6040 disabled by target DT; leaving PCIe untouched\\n");
    } else {
        pcie_init();
    }
    dapf_init_all();
""")

# T6040 DAPF: only dart-mtp is hardware-verified safe/required.
edit("src/dapf.c",
"""struct entry {
    const char *path;
    int index;
};

struct entry dapf_entries[] = {
    {"/arm-io/dart-aop", 1}, {"/arm-io/dart-mtp", 1},  {"/arm-io/dart-pmp", 1},
    {"/arm-io/dart-isp", 5}, {"/arm-io/dart-isp0", 5}, {NULL, -1},
};
""",
"""struct entry {
    const char *path;
    int index;
    bool t8132_broken;
};

struct entry dapf_entries[] = {
    {"/arm-io/dart-aop", 1, true},  {"/arm-io/dart-mtp", 1, false},
    {"/arm-io/dart-pmp", 1, false}, {"/arm-io/dart-isp", 5, true},
    {"/arm-io/dart-isp0", 5, true}, {NULL, -1, false},
};

static bool dapf_skip_entry(const struct entry *entry)
{
    if (chip_id == T6040)
        return strcmp(entry->path, "/arm-io/dart-mtp") != 0;
    if (chip_id == T8132)
        return entry->t8132_broken;
    return false;
}
""")
edit("src/dapf.c",
"""        if (adt_path_offset(adt, entry->path) < 0) {
            entry++;
            continue;
        }
        if (dapf_init(entry->path, entry->index) < 0) {
""",
"""        if (adt_path_offset(adt, entry->path) < 0) {
            entry++;
            continue;
        }
        if (dapf_skip_entry(entry)) {
            printf("dapf: Skipping %s (async L2C SError on this M4 SoC)\\n", entry->path);
            entry++;
            continue;
        }
        if (dapf_init(entry->path, entry->index) < 0) {
""")

# Keep the active stage-2 log ring one 16K page below the top-of-RAM boundary.
edit("src/kboot.c",
"""#define LOGBUF_SIZE SZ_16K
""",
"""#define LOGBUF_SIZE           SZ_16K
#define LOGBUF_TOP_GUARD_SIZE SZ_16K
""")
edit("src/kboot.c",
"""    // init memory backed iodev for console log
    logbuf.buffer = (void *)top_of_memory_alloc(LOGBUF_SIZE);
""",
"""    // Keep T6040's live ring away from the exclusive top-of-RAM boundary.
    logbuf.buffer = (void *)top_of_memory_alloc(LOGBUF_SIZE + LOGBUF_TOP_GUARD_SIZE);
""")

# T6041/T6040 MCC: four AMCCs, one cache plane each, ADT-provided reg index,
# and a different validated cache-status pattern.
edit("src/mcc.c",
"""#define T8112_CACHE_DISABLE 0x424
""",
"""#define T6041_CACHE_STATUS_MASK 0x00010101
#define T6041_CACHE_STATUS_VAL  0x00010101
#define T6041_PLANE_COUNT       1

#define T8112_CACHE_DISABLE 0x424
""")
edit("src/mcc.c",
"""    u32 plane_count = 0;
    u32 dcs_count = 0;

    if (!ADT_GETPROP(adt, node, "dcs-count-per-amcc", &dcs_count)) {
        printf("MCC: Failed to get dcs count!\\n");
        return -1;
    }

    if (!ADT_GETPROP(adt, node, "plane-count-per-amcc", &plane_count)) {
        printf("MCC: Failed to get plane count!\\n");
        return -1;
    }

    printf("MCC: Initializing T%x MCCs (%d instances)...\\n", chip_id, mcc_count);

    int ret = -1;
    if (adt_is_compatible(adt, node, "mcc,t8132")) {
        int reg_offset = 7;
        ret = mcc_init_t8122(path, reg_offset, plane_count, dcs_count, &t6030_tz_regs);
    } else {
""",
"""    u32 plane_count = 0;
    u32 dcs_count = 0;
    u32 reg_offset = 0;

    if (!ADT_GETPROP(adt, node, "dcs-count-per-amcc", &dcs_count)) {
        printf("MCC: Failed to get dcs count!\\n");
        return -1;
    }

    printf("MCC: Initializing T%x MCCs (%d instances)...\\n", chip_id, mcc_count);

    int ret = -1;
    if (adt_is_compatible(adt, node, "mcc,t8132")) {
        if (!ADT_GETPROP(adt, node, "plane-count-per-amcc", &plane_count)) {
            printf("MCC: Failed to get plane count!\\n");
            return -1;
        }
        reg_offset = 7;
        ret = mcc_init_t8122(path, reg_offset, plane_count, dcs_count, &t6030_tz_regs);
    } else if (adt_is_compatible(adt, node, "mcc,t6041")) {
        if (ADT_GETPROP(adt, node, "amcc-reg-idx", &reg_offset) < 0) {
            printf("MCC: Failed to get amcc-reg-idx!\\n");
            return -1;
        }
        plane_count = T6041_PLANE_COUNT;
        ret = mcc_init_t6031(path, reg_offset, plane_count, dcs_count);
        if (!ret) {
            for (int i = 0; i < mcc_count; i++) {
                mcc_regs[i].cache_status_mask = T6041_CACHE_STATUS_MASK;
                mcc_regs[i].cache_status_val = T6041_CACHE_STATUS_VAL;
            }
        }
    } else {
""")
edit("src/mcc.c",
"""    } else if (adt_is_compatible(adt, node, "mcc,t8132")) {
        return mcc_init_m4(node, path);
    } else if (adt_is_compatible(adt, node, "mcc,t6030")) {
""",
"""    } else if (adt_is_compatible(adt, node, "mcc,t8132") ||
               adt_is_compatible(adt, node, "mcc,t6041")) {
        return mcc_init_m4(node, path);
    } else if (adt_is_compatible(adt, node, "mcc,t6030")) {
""")

# T6040 cpufreq: only the validated CLUSTER_PSTATE path; never touch the
# T6030 throttle/snooze offsets which SError on T6040 P-clusters.
for old, new in [
("""        case T6030 ... T6034:
        case T8122:
            return FIELD_GET(CLUSTER_PSTATE_DESIRED1, val);
""",
"""        case T6030 ... T6034:
        case T6040:
        case T8122:
            return FIELD_GET(CLUSTER_PSTATE_DESIRED1, val);
"""),
("""            case T6030 ... T6034:
            case T8122:
                val &= ~CLUSTER_PSTATE_DESIRED1;
""",
"""            case T6030 ... T6034:
            case T6040:
            case T8122:
                val &= ~CLUSTER_PSTATE_DESIRED1;
"""),
("""        case T6030 ... T6034:
        case T8122:
            /* Unknown */
            write64(cluster->base + 0x440f8, 1);
            break;
""",
"""        case T6040:
            /* Only CLUSTER_PSTATE is validated safe on T6040. */
            break;
        case T6030 ... T6034:
        case T8122:
            /* Unknown */
            write64(cluster->base + 0x440f8, 1);
            break;
"""),
("""        case T6031:
        case T6034:
            return t6031_clusters;
""",
"""        case T6031:
        case T6034:
        case T6040:
            return t6031_clusters;
""")
]:
    edit("src/cpufreq.c", old, new)

edit("src/cpufreq.c",
"""static const struct feat_t t6030_features[] = {
    {"cpu-apsc", CLUSTER_PSTATE, CLUSTER_PSTATE_M2_APSC_DIS, 0, CLUSTER_PSTATE_APSC_BUSY, false},
""",
"""static const struct feat_t t6040_features[] = {
    {"cpu-apsc", CLUSTER_PSTATE, CLUSTER_PSTATE_M2_APSC_DIS, 0, CLUSTER_PSTATE_APSC_BUSY, false},
    {"cpu-fixed-freq-pll-relock", CLUSTER_PSTATE, 0, CLUSTER_PSTATE_FIXED_FREQ_PLL_RECLOCK, 0,
     false},
    {},
};

static const struct feat_t t6030_features[] = {
    {"cpu-apsc", CLUSTER_PSTATE, CLUSTER_PSTATE_M2_APSC_DIS, 0, CLUSTER_PSTATE_APSC_BUSY, false},
""")
edit("src/cpufreq.c",
"""        case T6030 ... T6034:
            return t6030_features;
        default:
""",
"""        case T6030 ... T6034:
            return t6030_features;
        case T6040:
            return t6040_features;
        default:
""")

print("J614s m1n1 v1.9.9 patch set applied")
