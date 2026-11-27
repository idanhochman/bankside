"""Toy example: exact subnormal sums, no flush to zero ([FADD-4], [FADD-7]).

Worked cases 22, 23, 24, 25, 26 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_subnormals(dut):
    await run_cases(dut, [22, 23, 24, 25, 26])
