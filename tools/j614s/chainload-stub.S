/* SPDX-License-Identifier: MIT */
/* Same copy/jump sequence as m1n1 v1.9.9 proxyclient/tools/chainload.py. */
.text
.global _start
_start:
1:
    ldp x4, x5, [x1], #16
    stp x4, x5, [x2]
    dc cvau, x2
    ic ivau, x2
    add x2, x2, #16
    sub x3, x3, #16
    cbnz x3, 1b
    ldr x1, entry
    br x1
    .balign 8
entry:
    .quad 0
