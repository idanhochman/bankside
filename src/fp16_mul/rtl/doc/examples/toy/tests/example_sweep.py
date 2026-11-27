"""Designer's sanity sweep, not verification: the RTL against NumPy float16.

The spec ([FMUL-7], "How the cases are checked") says NumPy's float16 product
is a valid oracle for every non-NaN result, and that every NaN result is
0x7E00 ([FMUL-8]). This sweep checks both on:
  - every a (all 65536 patterns) against each of 8 chosen b, in both orders;
  - 200000 random pairs from the seed: a third uniform over all 2^32, a third
    finite non-zero, a third with a subnormal a.
DV's sweeps (src/fp16_mul/dv/) are the real check. Run with --no-waves.
"""

import random
import warnings

import cocotb
import numpy as np
from cocotb.triggers import Timer

FIXED_B = [0x3C00, 0x3800, 0x3C01, 0x0001, 0x03FF, 0x7BFF, 0x0400, 0xBE00]


def finite_nonzero(rng):
    while True:
        x = rng.getrandbits(16)
        if (x & 0x7FFF) != 0 and (x & 0x7C00) != 0x7C00:
            return x


def pairs(rng):
    for b in FIXED_B:
        for a in range(1 << 16):
            yield a, b
            yield b, a
    for i in range(200000):
        k = i % 3
        if k == 0:
            yield rng.getrandbits(16), rng.getrandbits(16)
        elif k == 1:
            yield finite_nonzero(rng), finite_nonzero(rng)
        else:
            yield (rng.getrandbits(1) << 15) | rng.randint(1, 0x3FF), finite_nonzero(rng)


@cocotb.test()
async def example_sweep(dut):
    rng = random                                      # seeded by opendv
    a_l, b_l, p_l = [], [], []
    for a, b in pairs(rng):
        dut.a.value = a
        dut.b.value = b
        await Timer(1, unit="ns")
        a_l.append(a)
        b_l.append(b)
        p_l.append(int(dut.p.value))
    a_v = np.array(a_l, dtype=np.uint16)
    b_v = np.array(b_l, dtype=np.uint16)
    p_v = np.array(p_l, dtype=np.uint16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                # overflow and invalid are expected
        ref = (a_v.view(np.float16) * b_v.view(np.float16)).view(np.uint16)
    ref_nan = ((ref & 0x7C00) == 0x7C00) & ((ref & 0x03FF) != 0)
    bad_nan = ref_nan & (p_v != 0x7E00)
    bad_val = ~ref_nan & (p_v != ref)
    bad = np.nonzero(bad_nan | bad_val)[0]
    for i in bad[:20]:
        dut._log.error("a=0x%04X b=0x%04X p=0x%04X numpy=0x%04X", a_l[i], b_l[i], p_l[i], ref[i])
    dut._log.info("%d pairs, %d NaN results, %d mismatches (numpy %s)",
                  len(p_l), int(ref_nan.sum()), len(bad), np.__version__)
    assert len(bad) == 0
