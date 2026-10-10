#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply after patch-v1.9.9-j614s.py; mirror tested host NVMe handoff."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'src/payload.c'
text = path.read_text()
old = '#include "mitigations.h"\n'
assert text.count(old) == 1
text = text.replace(old, old + '#include "nvme.h"\n')
old = '    if (kernel && fdt) {\n        cpufreq_init();'
assert text.count(old) == 1
text = text.replace(old, '''    if (kernel && fdt) {
        int node = fdt_node_offset_by_compatible(fdt, -1, "apple,t8132-nvme-ans2");
        int len = 0;
        const char *status = node < 0 ? NULL : fdt_getprop(fdt, node, "status", &len);
        if (chip_id == T6040 && node >= 0 &&
            (!status || !strcmp(status, "okay") || !strcmp(status, "ok"))) {
            printf("J614S_SSD_PAYLOAD: initializing and shutting down ANS\\n");
            if (!nvme_init()) {
                printf("NVMe handoff failed; staying in proxy mode\\n");
                return -1;
            }
            nvme_shutdown();
        }
        cpufreq_init();''')
path.write_text(text)
