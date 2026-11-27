"""Toy example: rounding decided by the sticky bit and wide alignments ([FADD-7]).

Worked cases 6, 7, 12, 20, 21 of src/fp16_add/doc/README.md, each also with a and b swapped
([FADD-10]). Expected s: the spec's s column. Review page: ../../../fp16_add.md.
"""

import cocotb

from fadd_toy import run_cases


@cocotb.test()
async def example_sticky(dut):
    await run_cases(dut, [6, 7, 12, 20, 21])
