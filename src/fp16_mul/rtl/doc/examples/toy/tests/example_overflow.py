"""Toy example: the largest finite value and overflow to signed Inf, no saturation ([FMUL-7]).

Worked cases 9, 10, 11, 12, 13, 14 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_overflow(dut):
    await run_cases(dut, [9, 10, 11, 12, 13, 14], swapped=True)
