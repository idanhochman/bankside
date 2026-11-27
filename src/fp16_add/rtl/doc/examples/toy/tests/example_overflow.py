"""Toy example: overflow to +-Inf by RNE, no saturation ([FADD-6], [FADD-7]).

Worked cases 15, 16, 17, 18, 19 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_overflow(dut):
    await run_cases(dut, [15, 16, 17, 18, 19])
