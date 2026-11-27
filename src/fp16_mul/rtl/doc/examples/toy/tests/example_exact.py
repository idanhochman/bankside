"""Toy example: exact products, the sign XOR and rounding to nearest ([FMUL-6], [FMUL-7]).

Worked cases 1, 2, 3, 4, 7, 8, 15 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_exact(dut):
    await run_cases(dut, [1, 2, 3, 4, 7, 8, 15], swapped=True)
