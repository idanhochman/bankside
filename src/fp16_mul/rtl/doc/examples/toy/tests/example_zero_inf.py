"""Toy example: signed zeros and infinities, and zero x Inf = 0x7E00 ([FMUL-5], [FMUL-6], [FMUL-8]).

Worked cases 30, 31, 32, 33, 34, 35, 36, 37, 38 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_zero_inf(dut):
    await run_cases(dut, [30, 31, 32, 33, 34, 35, 36, 37, 38], swapped=True)
