"""Toy example: every NaN result is 0x7E00, whatever the NaN operand ([FMUL-8], [FMUL-10]).

Worked cases 39, 40, 41, 42, 43 of src/fp16_mul/doc/README.md, each also with a and b swapped
([FMUL-10]). Expected p: the spec's p column. Review page: ../../../fp16_mul.md.
"""

import cocotb

from fmul_toy import run_cases


@cocotb.test()
async def example_nan(dut):
    await run_cases(dut, [39, 40, 41, 42, 43], swapped=True)
