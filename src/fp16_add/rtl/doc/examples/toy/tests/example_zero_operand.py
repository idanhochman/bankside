"""Toy example: a zero operand returns the other operand bit for bit ([FADD-5]).

Worked cases 34, 35, 36 of src/fp16_add/doc/README.md, then six pairs whose s
is read off [FADD-5]'s table ("zero" row, "subnormal or normal" column: `b`,
bit for bit): each sign of zero with the largest finite, the largest and the
middle subnormal, and the smallest normal. Each pair also runs with a and b
swapped ([FADD-10]). Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases

RULE = "[FADD-5]: zero + x = x, bit for bit"
EXTRA = [
    ("z1", 0x0000, 0x7BFF, 0x7BFF, RULE),
    ("z2", 0x8000, 0xFBFF, 0xFBFF, RULE),
    ("z3", 0x0000, 0x83FF, 0x83FF, RULE),
    ("z4", 0x8000, 0x03FF, 0x03FF, RULE),
    ("z5", 0x8000, 0x0200, 0x0200, RULE),
    ("z6", 0x0000, 0x8400, 0x8400, RULE),
]


@cocotb.test()
async def example_zero_operand(dut):
    await run_cases(dut, [34, 35, 36], extra=EXTRA)
