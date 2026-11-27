"""Toy example: every NaN result is 0x7E00, whatever the NaN operand ([FADD-8], [FADD-10]).

Worked cases 44 to 49 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_nan(dut):
    await run_cases(dut, [44, 45, 46, 47, 48, 49])
