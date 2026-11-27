"""Toy example: subnormal operands and results, and underflow to signed zero ([FMUL-4], [FMUL-6], [FMUL-7]).

Worked cases 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_subnormals(dut):
    await run_cases(dut, [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29], swapped=True)
