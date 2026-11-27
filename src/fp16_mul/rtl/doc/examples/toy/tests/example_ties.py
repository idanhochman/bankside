"""Toy example: ties round to the even significand, normal and subnormal ([FMUL-7]).

Worked cases 5, 6, 11, 17, 18, 21, 23 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_ties(dut):
    await run_cases(dut, [5, 6, 11, 17, 18, 21, 23], swapped=True)
