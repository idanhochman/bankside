"""Toy example: exact ties round to the even significand, normal and at a binade edge ([FADD-7]).

Worked cases 4, 5, 8, 9, 10, 11 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_ties(dut):
    await run_cases(dut, [4, 5, 8, 9, 10, 11])
