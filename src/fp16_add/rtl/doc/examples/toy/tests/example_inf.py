"""Toy example: Inf operands, and +Inf + (-Inf) = 0x7E00 ([FADD-5], [FADD-8]).

Worked cases 37 to 43 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_inf(dut):
    await run_cases(dut, [37, 38, 39, 40, 41, 42, 43])
