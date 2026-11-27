"""Designer's sanity sweep, not verification: the RTL against NumPy float16.

The spec ("NumPy as a reference: double rounding", [FADD-7]) proves NumPy's
float16 sum a valid oracle for every non-NaN result, and every NaN result is
0x7E00 ([FADD-8]). This sweep checks both, and [FADD-10], on:
  - every a (all 65536 patterns) against each of 12 chosen b, in both orders;
  - every a against -a (x + (-x), [FADD-6]);
  - 200000 random pairs from the seed: a third uniform over all 2^32, a third
    finite non-zero, a third with a subnormal a.
Each pair is applied as (a, b) and as (b, a); both must equal the reference.
DV's sweeps (src/fp16_add/dv/) are the real check. Run with --no-waves.
"""

import random
import warnings

import cocotb
import numpy as np
from cocotb.triggers import Timer

FIXED_B = [0x0000, 0x8000, 0x3C00, 0xBC00, 0x0001, 0x8001,
           0x03FF, 0x0400, 0x7BFF, 0xFBFF, 0x7C00, 0xFC00]


def finite_nonzero(rng):
    while True:
        x = rng.getrandbits(16)
        if (x & 0x7FFF) != 0 and (x & 0x7C00) != 0x7C00:
            return x


def pairs(rng):
    for b in FIXED_B:
        for a in range(1 << 16):
            yield a, b
    for a in range(1 << 16):
        yield a, a ^ 0x8000
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
    a_l, b_l, s_l, t_l = [], [], [], []
    for a, b in pairs(rng):
        dut.a.value = a
        dut.b.value = b
        await Timer(1, unit="ns")
        s_l.append(int(dut.s.value))
        dut.a.value = b
        dut.b.value = a
        await Timer(1, unit="ns")
        t_l.append(int(dut.s.value))
        a_l.append(a)
        b_l.append(b)
    a_v = np.array(a_l, dtype=np.uint16)
    b_v = np.array(b_l, dtype=np.uint16)
    s_v = np.array(s_l, dtype=np.uint16)
    t_v = np.array(t_l, dtype=np.uint16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                # overflow and invalid are expected
        ref = (a_v.view(np.float16) + b_v.view(np.float16)).view(np.uint16)
    ref_nan = ((ref & 0x7C00) == 0x7C00) & ((ref & 0x03FF) != 0)
    want = np.where(ref_nan, np.uint16(0x7E00), ref)
    bad = np.nonzero((s_v != want) | (t_v != want))[0]
    for i in bad[:20]:
        dut._log.error("a=0x%04X b=0x%04X s=0x%04X swapped=0x%04X want=0x%04X",
                       a_l[i], b_l[i], s_l[i], t_l[i], want[i])
    neg_zero = int(((s_v == 0x8000)).sum())
    dut._log.info("%d pairs x 2 orders, %d NaN results, %d -0 results, %d mismatches (numpy %s)",
                  len(s_l), int(ref_nan.sum()), neg_zero, len(bad), np.__version__)
    assert len(bad) == 0
