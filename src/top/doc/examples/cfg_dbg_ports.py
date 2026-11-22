#!/usr/bin/env python3
"""The configuration and debug ports over every select and index value.

Backs "Configuration and debug ports" in ../interfaces.md ([TOP-IF-9] to
[TOP-IF-12]) and the top glue of ../hierarchy.md ([TOP-HIER-6],
[TOP-HIER-7]). The model is the glue plus five pcu_regfile instances:

  write-port select  a configuration write reaches a file only if it is
                     allowed by [TOP-IF-8] (busy = 0, trig_valid = 0), the
                     select names a file and the index is below its depth;
                     the file keeps only its low data bits ([TOP-IF-10]).
  debug read select  dbg_rd_data is the selected entry, zero-extended, or 0
                     for an unused select or an out-of-range index
                     ([TOP-IF-11]); write-through like every read port of
                     pcu_regfile ([TOP-IF-12], [TOP-HIER-4]).

  1. The select table of interfaces.md matches the yaml operand codes and
     sizes.
  2. Every (select, index) pair, 8 x 32, written and read back.
  3. Where the out-of-range options of #15 differ: ignore/0 (chosen) against
     taking the index modulo the depth.
  4. Where the same-cycle options for the debug read differ: write-through
     (chosen) against the stored value only; with the [TOP-IF-8] gate.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/cfg_dbg_ports.py
Exits non-zero if any check fails.
"""
import re
import sys
from pathlib import Path

import yaml

DOC = Path(__file__).resolve().parent.parent
isa = yaml.safe_load((DOC / "bankside_isa.yaml").read_text())
failures = []

# 1. The select table ---------------------------------------------------------------
# | 0 | GRF_A | 8 (0–7) | 255:0 |      | 4, 5, 6 | none | – | – |
FILES = {}
for line in (DOC / "interfaces.md").read_text().splitlines():
    m = re.match(r"^\s*\| (\d(?:, \d)*) \| ([A-Z][A-Z_]*|none) \| (?:(\d+) \(0–(\d+)\)|–) \| (?:(\d+):0|–) \|", line)
    if m:
        codes = [int(c) for c in m.group(1).split(", ")]
        if m.group(2) != "none":
            depth, top, msb = int(m.group(3)), int(m.group(4)), int(m.group(5))
            assert len(codes) == 1 and top == depth - 1, line
            FILES[codes[0]] = (m.group(2), depth, msb + 1)
        else:
            for c in codes:
                FILES[c] = None
print("1. Select table ([TOP-IF-9]) from interfaces.md")
for code in range(8):
    f = FILES.get(code, "missing")
    print(f"   {code}: " + (f"{f[0]}, {f[1]} entries x {f[2]} bits" if f else "none" if f is None else f))
    if f == "missing":
        failures.append(f"select {code} not in the table")
for code, f in FILES.items():
    if f and f[0] in isa["operands"]:
        op = isa["operands"][f[0]]
        if (op["code"], op["entries"], op["width"]) != (code, f[1], f[2]):
            failures.append(f"{f[0]}: table {code, f[1], f[2]}, yaml {op['code'], op['entries'], op['width']}")
    elif f and f[0] != "CRF":
        failures.append(f"{f[0]} is not a yaml operand")
if FILES.get(7) != ("CRF", 32, 32):
    failures.append(f"CRF row {FILES.get(7)}")
named = {f[0] for f in FILES.values() if f}
if named != {"GRF_A", "GRF_B", "SRF_M", "SRF_A", "CRF"}:
    failures.append(f"files named {named}")
print("   codes 0-3 equal the yaml operand codes, entries and widths; 7 is the CRF (32 x 32)\n")


# The model --------------------------------------------------------------------------
def fresh():
    """Each file's entries hold distinct known values."""
    return {code: [code << 8 | i for i in range(f[1])]
            for code, f in FILES.items() if f}


def cfg_target(en, sel, idx, busy=0, trig=0, modulo=False):
    """(file code, entry) a configuration write reaches, or None."""
    f = FILES.get(sel)
    if not en or busy or trig or not f:              # [TOP-IF-8], unused select
        return None
    if idx >= f[1]:
        return (sel, idx % f[1]) if modulo else None  # option (b) / chosen (a)
    return (sel, idx)


def dbg_read(regs, sel, idx, wr=None, write_through=True, modulo=False):
    """dbg_rd_data. wr = (file code, entry, value) written this cycle, after
    the glue's gating."""
    f = FILES.get(sel)
    if not f:
        return 0
    if idx >= f[1]:
        if not modulo:
            return 0
        idx %= f[1]
    if write_through and wr and wr[:2] == (sel, idx):
        return wr[2]
    return regs[sel][idx]        # zero-extended: the entry has f[2] bits


def clock(regs, wr):
    if wr:
        regs[wr[0]][wr[1]] = wr[2]


ALL = (1 << 256) - 1

# 2. Every select and index ------------------------------------------------------------
print("2. Every (cfg_wr_sel, cfg_wr_idx) written with cfg_wr_data = all ones, then read back")
print("   sel  file    writes taking effect   entries changed   dbg_rd_data for idx >= depth   high bits read")
for sel in range(8):
    took, changed, oob, high = [], 0, set(), set()
    for idx in range(32):
        regs = fresh()
        before = {c: list(v) for c, v in regs.items()}
        t = cfg_target(1, sel, idx)
        if t:
            f = FILES[sel]
            clock(regs, (t[0], t[1], ALL & ((1 << f[2]) - 1)))   # low data bits only [TOP-IF-10]
            took.append(idx)
        changed += sum(a != b for c in regs for a, b in zip(regs[c], before[c]))
        v = dbg_read(regs, sel, idx)
        f = FILES.get(sel)
        if not f or idx >= f[1]:
            oob.add(v)
        else:
            high.add(v >> f[2])
            if v != ALL & ((1 << f[2]) - 1):
                failures.append(f"read back sel {sel} idx {idx}")
    f = FILES.get(sel)
    rng = f"{took[0]}-{took[-1]}" if took else "none"
    print(f"   {sel}    {f[0] if f else 'none':6}  {rng:22} {changed:15}   "
          f"{'0' if oob == {0} else oob if oob else '(none)':30} {'0' if high <= {0} else high if high else '-'}")
    exp = list(range(f[1])) if f else []
    if took != exp or changed != len(exp) or not oob <= {0} or not high <= {0}:
        failures.append(f"select {sel}")
print("   (entries changed counts, over all 32 writes, the entries that differ afterwards in any file)")

# The single cases of the interfaces.md worked-case table.
regs = fresh()
t = cfg_target(1, 5, 2)
r5 = dbg_read(regs, 5, 2)
print(f"   cfg_wr_sel = 5, idx 2: write reaches {t}; dbg_rd_sel = 5 reads {r5:#x}")
t = cfg_target(1, 2, 3)
clock(regs, (*t, ALL & 0xFFFF))
v = dbg_read(regs, 2, 3)
print(f"   cfg_wr_sel = 2, idx 3, data all ones: SRF_M[3] = {regs[2][3]:#06x};"
      f" dbg_rd_data bits 15:0 = {v & 0xFFFF:#06x}, bits 255:16 = {v >> 16:#x}\n")
if t != (2, 3) or v != 0xFFFF or r5 != 0:
    failures.append("single cases")

# 3. Out-of-range options ---------------------------------------------------------------
print("3. Where the out-of-range options differ: the host writes GRF_A index 9 (meant 1, a host bug)")
for name, mod in (("(a) ignored, reads 0 (chosen)", False), ("(b) index modulo depth", True)):
    regs = fresh()
    old = regs[0][1]
    clock(regs, (lambda t: t and (*t, 0xABCD))(cfg_target(1, 0, 9, modulo=mod)))
    r9 = dbg_read(regs, 0, 9, modulo=mod)
    print(f"   {name:31} GRF_A[1] {old:#06x} -> {regs[0][1]:#06x}; dbg_rd_idx = 9 reads {r9:#06x}")
    if not mod and (regs[0][1] != old or r9 != 0):
        failures.append("option (a)")
    if mod and regs[0][1] == old:
        failures.append("option (b)")
print("   Under (b) the bug overwrites GRF_A[1] and a check that reads index 9 back passes;")
print("   under (a) GRF_A[1] is untouched and the read-back of index 9 gives 0, so the test sees it.\n")

# 4. Same-cycle debug read -------------------------------------------------------------
print("4. Debug read of GRF_B[0] in the cycle of a write to it (GRF_B[0] holds 0x0100 before)")
cases = [
    ("S5 write of 0x7777 (a running program)", lambda: (1, 0, 0x7777)),
    ("configuration write of 0x5555, busy = 0, trig_valid = 0", lambda: (lambda t: t and (*t, 0x5555))(cfg_target(1, 1, 0))),
    ("configuration write of 0x5555, busy = 1 ([TOP-IF-8]: ignored)", lambda: (lambda t: t and (*t, 0x5555))(cfg_target(1, 1, 0, busy=1))),
]
print(f"   {'write in cycle t':60} {'(a) write-through, chosen':>27} {'(b) stored only':>17}   cycle t+1, both")
for title, wr in cases:
    got = []
    for wt in (True, False):
        regs = fresh()
        w = wr()
        same = dbg_read(regs, 1, 0, w, write_through=wt)
        clock(regs, w)
        nxt = dbg_read(regs, 1, 0, None, write_through=wt)
        got.append((same, nxt))
    print(f"   {title:60} {got[0][0]:#27x} {got[1][0]:#17x}   {got[0][1]:#x}")
    if got[0][1] != got[1][1]:
        failures.append(f"{title}: cycle t+1 differs")
if [c for c in cases] and dbg_read(fresh(), 1, 0, (1, 0, 0x7777)) != 0x7777:
    failures.append("write-through")
if dbg_read(fresh(), 1, 0, cases[2][1]()) != 0x0100:
    failures.append("an ignored configuration write must not show through")
print("   The options differ only in the cycle of the write; from t+1 on both show the stored value.")

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all checks pass")
