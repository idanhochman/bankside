"""Toy example: the double-rounding rows: the single rounding the spec asks for ([FADD-7]).

Double-rounding rows D1 to D6 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_double_rounding(dut):
    await run_cases(dut, ['D1', 'D2', 'D3', 'D4', 'D5', 'D6'])
