"""Shared harness for the fp16_mul toy examples (designer's, not DV's).

The expected values come from the spec alone: the worked-case table of
src/fp16_mul/doc/README.md, read from the file itself so the examples can't
drift from it. Each example drives a, b, holds them STEP_NS, and checks p.
"""

import pathlib
import re

from cocotb.triggers import Timer
from cocotb.utils import get_sim_time

STEP_NS = 10          # how long each pair is held, for readable waveforms
SETTLE_NS = 1         # p is checked this long after the inputs change

SPEC = pathlib.Path(__file__).resolve().parents[5] / "doc" / "README.md"

_ROW = re.compile(r"^\| (\d+) \| 0x([0-9A-F]{4}) \| 0x([0-9A-F]{4}) \|(.*)$")


def worked_cases():
    """The spec's worked cases: {number: (a, b, p, rule text)}."""
    cases = {}
    in_table = False
    for line in SPEC.read_text().splitlines():
        if line.startswith("### Worked cases"):
            in_table = True
        elif in_table and line.startswith("### "):
            break
        elif in_table:
            m = _ROW.match(line)
            if m:
                cells = [c.strip() for c in m.group(4).split("|")]
                # cells: values, exact product, p, rule, NumPy, ANEMOS, ''
                p = int(cells[2], 16)
                cases[int(m.group(1))] = (int(m.group(2), 16), int(m.group(3), 16), p, cells[3])
    assert len(cases) == 43, f"expected 43 worked cases in {SPEC}, found {len(cases)}"
    return cases


async def apply(dut, a, b):
    """Drive one pair, wait for p to settle, return p; hold for STEP_NS."""
    dut.a.value = a
    dut.b.value = b
    await Timer(SETTLE_NS, unit="ns")
    p = int(dut.p.value)
    await Timer(STEP_NS - SETTLE_NS, unit="ns")
    return p


async def run_cases(dut, numbers, swapped=False):
    """Apply the listed worked cases in order as (a, b), then, if swapped, as (b, a).

    Logs one line per pair, with the time it was applied (for the review page's
    waveform markers), and fails at the end if any p differs from the spec.
    """
    cases = worked_cases()
    await Timer(STEP_NS, unit="ns")       # idle step, so the first change is visible
    bad = []
    for swap in ([False, True] if swapped else [False]):
        for n in numbers:
            a, b, want, rule = cases[n]
            if swap:
                a, b = b, a
            start = get_sim_time("ns")
            got = await apply(dut, a, b)
            ok = got == want
            dut._log.info("t=%4dns #%-2d a=0x%04X b=0x%04X p=0x%04X spec=0x%04X %s %s",
                          start, n, a, b, got, want, "ok " if ok else "BAD", rule)
            if not ok:
                bad.append((n, swap))
    assert not bad, f"p differs from the spec on worked cases (number, swapped): {bad}"
