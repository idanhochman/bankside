"""Toy example: exact zero sums are +0, except (-0) + (-0) = -0 ([FADD-6]).

Worked cases 27 to 33 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_signed_zeros(dut):
    await run_cases(dut, [27, 28, 29, 30, 31, 32, 33])
