"""Toy example: exact sums: a carry, the sign of the larger operand, cancellation ([FADD-6], [FADD-7]).

Worked cases 1, 2, 3, 13, 14 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_exact(dut):
    await run_cases(dut, [1, 2, 3, 13, 14])
