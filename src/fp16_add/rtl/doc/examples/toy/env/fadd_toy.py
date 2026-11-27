"""Shared harness for the fp16_add toy examples (designer's, not DV's).

The expected values come from the spec alone: the worked-case table and the
double-rounding table of src/fp16_add/doc/README.md, read from the file itself
so the examples can't drift from it. Each example drives a, b, holds them
STEP_NS, and checks s.
"""

import pathlib
import re

from cocotb.triggers import Timer
from cocotb.utils import get_sim_time

STEP_NS = 10          # how long each pair is held, for readable waveforms
SETTLE_NS = 1         # s is checked this long after the inputs change

SPEC = pathlib.Path(__file__).resolve().parents[5] / "doc" / "README.md"

_ROW = re.compile(r"^\| (D?\d+) \| 0x([0-9A-F]{4}) \| 0x([0-9A-F]{4}) \|(.*)$")


def _table(heading, count):
    """Rows of the spec table under `heading`: {id: (a, b, s, note)}."""
    cases = {}
    in_table = False
    for line in SPEC.read_text().splitlines():
        if line.startswith(heading):
            in_table = True
        elif in_table and line.startswith("### "):
            break
        elif in_table:
            m = _ROW.match(line)
            if m:
                cells = [c.strip() for c in m.group(4).split("|")]
                # worked cases: values, exact sum, s, rule, NumPy, ANEMOS, ''
                # double rounding: exact sum, float32 sum, s, 12 bits, what, ''
                key = m.group(1)
                key = int(key) if key.isdigit() else key
                note = cells[3] if isinstance(key, int) else cells[4]
                cases[key] = (int(m.group(2), 16), int(m.group(3), 16), int(cells[2], 16), note)
    assert len(cases) == count, f"expected {count} rows under '{heading}' in {SPEC}, found {len(cases)}"
    return cases


def spec_cases():
    """The worked cases (1 to 49) and the double-rounding rows (D1 to D6)."""
    cases = _table("### Worked cases", 49)
    cases.update(_table("### NumPy as a reference", 6))
    return cases


async def apply(dut, a, b):
    """Drive one pair, wait for s to settle, return s; hold for STEP_NS."""
    dut.a.value = a
    dut.b.value = b
    await Timer(SETTLE_NS, unit="ns")
    s = int(dut.s.value)
    await Timer(STEP_NS - SETTLE_NS, unit="ns")
    return s


async def run_cases(dut, ids, swapped=True, extra=()):
    """Apply the listed spec rows in order as (a, b), then, if swapped, as (b, a).

    `extra` is a list of (label, a, b, s) pairs whose s the caller derives
    from a spec rule; they run after the rows, in each pass. Logs one line per
    pair with the time it was applied (for the review page's waveform
    markers), and fails at the end if any s differs from the spec.
    """
    cases = spec_cases()
    pairs = [(f"#{i}", *cases[i]) for i in ids] + [(lab, a, b, s, rule) for lab, a, b, s, rule in extra]
    await Timer(STEP_NS, unit="ns")       # idle step, so the first change is visible
    bad = []
    for swap in ([False, True] if swapped else [False]):
        for label, a, b, want, rule in pairs:
            if swap:
                a, b = b, a
            start = get_sim_time("ns")
            got = await apply(dut, a, b)
            ok = got == want
            dut._log.info("t=%4dns %-4s a=0x%04X b=0x%04X s=0x%04X spec=0x%04X %s %s",
                          start, label, a, b, got, want, "ok " if ok else "BAD", rule)
            if not ok:
                bad.append((label, swap))
    assert not bad, f"s differs from the spec on (case, swapped): {bad}"
