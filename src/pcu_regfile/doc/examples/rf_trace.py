#!/usr/bin/env python3
"""Worked cases for pcu_regfile, checked against a cycle model of ../README.md.

The model is the module's behaviour as its doc states it:
  storage    DEPTH entries of WIDTH bits, no reset, a power-up value per
             entry drawn from a seed ([RF-6], [TOP-ARCH-9])
  write      at the rising clk edge that ends a cycle with wr_en = 1,
             entry[wr_idx] <- wr_data ([RF-7])
  read       every functional port p and the debug port, combinational:
             wr_data if wr_en = 1 and wr_idx equals the port's index,
             else the stored entry ([RF-8], [RF-9], [RF-10])
It can also run option (b) of the doc, "stored value only" (no
write-through), to show where the two differ.

  1. The timing diagram img/rf_port_timing.wave.json: its inputs are fed to
     the model, and every output and storage row is compared, cycle by cycle.
  2. Write-through on every read port of a grf_b-shaped instance (3 ports +
     debug), one port at a time and all at once; wr_en = 0 shows nothing.
  3. An entry never written: the same bits on every port and every cycle
     until it is written, and different bits under another seed.
  4. The five instances: IDX_W = clog2(DEPTH), every index value names an
     entry, and an exhaustive write / read-back through every port.
  5. The packed port layout of [RF-4], with one grf_b example.
  6. grf_b's ports in cycles 5 to 7 of the GEMV case of
     ../../../top/doc/hierarchy.md: the accumulator bypass [TOP-HIER-5].

Run from the repo root:
    .venv/bin/python src/pcu_regfile/doc/examples/rf_trace.py
Exits non-zero if any check fails.
"""
import json
import random
import sys
from pathlib import Path

import yaml

DOC = Path(__file__).resolve().parent.parent
TOP_DOC = DOC.parent.parent / "top" / "doc"
failures = []


def check(cond, what):
    if not cond:
        failures.append(what)
        print(f"  FAIL: {what}")


def clog2(n):
    return (n - 1).bit_length()


class RegFile:
    """One pcu_regfile instance. write_through=False is option (b)."""

    def __init__(self, depth, width, n_rd, seed, write_through=True):
        self.depth, self.width, self.n_rd = depth, width, n_rd
        self.idx_w = clog2(depth)
        rng = random.Random(seed)
        self.entry = [rng.getrandbits(width) for _ in range(depth)]
        self.wt = write_through

    def read(self, idx, wr_en, wr_idx, wr_data):
        assert 0 <= idx < (1 << self.idx_w)
        if self.wt and wr_en and wr_idx == idx:
            return wr_data
        return self.entry[idx]

    def cycle(self, wr_en, wr_idx, wr_data, rd_idx, dbg_idx):
        """Outputs of one cycle, then the edge that ends it."""
        rd = [self.read(i, wr_en, wr_idx, wr_data) for i in rd_idx]
        dbg = self.read(dbg_idx, wr_en, wr_idx, wr_data)
        if wr_en:
            self.entry[wr_idx] = wr_data & ((1 << self.width) - 1)
        return rd, dbg


def h(v, width=16):
    return f"0x{v:0{(width + 3) // 4}X}"


# 1. The timing diagram -------------------------------------------------------
print("1. Timing diagram img/rf_port_timing.wave.json (srf_m shape: 8 x 16, N_RD = 1)")


def expand(sig, n):
    """Per-cycle values of one WaveDrom row: None for x, ints/strings else."""
    out, data, cur = [], list(sig.get("data", [])), None
    for ch in sig["wave"]:
        if ch == ".":
            pass
        elif ch == "x":
            cur = None
        elif ch in "01":
            cur = int(ch)
        elif ch == "=":
            cur = data.pop(0)
        elif ch == "p":
            cur = "clk"
        else:
            raise ValueError(f"unexpected wave char {ch!r} in {sig['name']}")
        out.append(cur)
    assert len(out) == n and not data, sig["name"]
    return out


wave = json.loads((DOC / "img" / "rf_port_timing.wave.json").read_text())
rows = {s["name"]: s for s in wave["signal"] if s}
n = len(rows["clk"]["wave"])
w = {name: expand(s, n) for name, s in rows.items()}
for name in ("wr_idx", "wr_data", "rd_idx[0]", "dbg_idx"):
    w[name] = [None if v is None else int(v, 0) for v in w[name]]

for wt, label in ((True, "write-through (chosen)"), (False, "(b) stored value only")):
    rf = RegFile(8, 16, 1, seed=1, write_through=wt)
    sym = {"P1": rf.entry[1], "P2": rf.entry[2]}

    def val(v):
        if isinstance(v, str):
            return sym[v] if v in sym else int(v, 0)
        return v

    print(f"   {label}; power-up P1 = {h(sym['P1'])}, P2 = {h(sym['P2'])}")
    print("   cyc wr_en wr_idx wr_data | rd_idx[0] rd_data[0] | dbg_idx dbg_data | entry[1] entry[2] (after the edge)")
    diffs = []
    for c in range(n):
        en = w["wr_en"][c]
        rd, dbg = rf.cycle(en, w["wr_idx"][c], w["wr_data"][c] or 0,
                           [w["rd_idx[0]"][c]], w["dbg_idx"][c])
        exp_rd, exp_dbg = val(w["rd_data[0]"][c]), val(w["dbg_data"][c])
        nxt = c + 1 if c + 1 < n else c
        exp_e1 = val(w["entry[1] (internal)"][nxt]) if c + 1 < n else None
        exp_e2 = val(w["entry[2] (internal)"][nxt]) if c + 1 < n else None
        print(f"   {c:>3} {en:>5} {str(w['wr_idx'][c] if w['wr_idx'][c] is not None else '-'):>6} "
              f"{h(w['wr_data'][c]) if w['wr_data'][c] is not None else '-':>7} | "
              f"{w['rd_idx[0]'][c]:>9} {h(rd[0]):>10} | {w['dbg_idx'][c]:>7} {h(dbg):>8} | "
              f"{h(rf.entry[1]):>8} {h(rf.entry[2]):>8}")
        if wt:
            check(rd[0] == exp_rd, f"diagram cycle {c}: rd_data[0] {h(rd[0])} != {h(exp_rd)}")
            check(dbg == exp_dbg, f"diagram cycle {c}: dbg_data {h(dbg)} != {h(exp_dbg)}")
            if exp_e1 is not None:
                check(rf.entry[1] == exp_e1, f"diagram: entry[1] after cycle {c}")
                check(rf.entry[2] == exp_e2, f"diagram: entry[2] after cycle {c}")
        else:
            if rd[0] != exp_rd or dbg != exp_dbg:
                diffs.append(c)
    if not wt:
        print(f"   (b) differs from the diagram in cycles {diffs}")
        check(diffs == [1, 3, 5], "option (b) should differ exactly in the write-through cycles 1, 3, 5")

# 2. Write-through on every read port ----------------------------------------
print("\n2. Write-through on every read port (grf_b shape: 8 x 256, N_RD = 3, + debug)")
ports = ["rd_data[0]", "rd_data[1]", "rd_data[2]", "dbg_data"]
V = int("A5" * 32, 16)  # 256-bit value written
for target in range(4):
    rf = RegFile(8, 256, 3, seed=2)
    old5, old4 = rf.entry[5], rf.entry[4]
    idx = [5 if p == target else 4 for p in range(4)]
    rd, dbg = rf.cycle(1, 5, V, idx[:3], idx[3])
    got = rd + [dbg]
    ok = all(got[p] == (V if p == target else old4) for p in range(4))
    print(f"   {ports[target]:<10} reads entry 5 while it is written: "
          f"{'new value' if got[target] == V else 'OLD value'}; other ports read entry 4: "
          f"{'stored' if all(got[p] == old4 for p in range(4) if p != target) else 'WRONG'}")
    check(ok, f"write-through on {ports[target]}")
    check(rf.entry[5] == V and old5 != V, f"entry 5 written at the edge ({ports[target]})")
rf = RegFile(8, 256, 3, seed=2)
rd, dbg = rf.cycle(1, 5, V, [5, 5, 5], 5)
print(f"   all four ports read entry 5 while it is written: {'all new' if rd + [dbg] == [V] * 4 else 'WRONG'}")
check(rd + [dbg] == [V] * 4, "all ports at once")
rf = RegFile(8, 256, 3, seed=2)
old5 = rf.entry[5]
rd, dbg = rf.cycle(0, 5, V, [5, 5, 5], 5)
print(f"   wr_en = 0, wr_idx = 5: all four ports read the stored entry 5: "
      f"{'yes' if rd + [dbg] == [old5] * 4 else 'NO'}; entry 5 unchanged: {'yes' if rf.entry[5] == old5 else 'NO'}")
check(rd + [dbg] == [old5] * 4 and rf.entry[5] == old5, "wr_en = 0 shows and writes nothing")

# 3. Never written ------------------------------------------------------------
print("\n3. An entry never written (srf_m shape, entry 6)")
rf = RegFile(8, 16, 1, seed=3)
p6 = rf.entry[6]
seen = []
for c in range(5):
    rd, dbg = rf.cycle(1, c % 6, 0x1111 * (c + 1), [6], 6)  # writes entries 0-4, never 6
    seen += [rd[0], dbg]
print(f"   seed 3: entry 6 reads {sorted({h(v) for v in seen})} on rd_data[0] and dbg_data over 5 cycles")
check(set(seen) == {p6}, "an unwritten entry reads the same bits everywhere")
rd, dbg = rf.cycle(1, 6, 0x3C00, [6], 6)
rd2, dbg2 = rf.cycle(0, 0, 0, [6], 6)
print(f"   written with 0x3C00 in cycle 5: reads {h(rd[0])} in cycle 5 (write-through), {h(rd2[0])} in cycle 6")
check(rd[0] == dbg == rd2[0] == dbg2 == 0x3C00, "after the first write")
other = RegFile(8, 16, 1, seed=4).entry[6]
print(f"   seed 4: entry 6 powers up as {h(other)} (seed 3: {h(p6)})")
check(other != p6, "another seed gives another power-up value (for these seeds)")

# 4. The five instances ---------------------------------------------------------
print("\n4. The five instances: IDX_W = clog2(DEPTH), every index names an entry")
isa = yaml.safe_load((TOP_DOC / "bankside_isa.yaml").read_text())["operands"]
inst = [  # (instance, yaml operand or None, DEPTH, WIDTH, N_RD)
    ("crf", None, 32, 32, 2),   # CRF size: theory_of_operation.md register-file table; N_RD 2 from pcu_ctrl's doc (#27)
    ("grf_a", "GRF_A", 8, 256, 2),
    ("grf_b", "GRF_B", 8, 256, 3),
    ("srf_m", "SRF_M", 8, 16, 1),
    ("srf_a", "SRF_A", 8, 16, 1),
]
print("   instance  DEPTH WIDTH N_RD IDX_W  2**IDX_W==DEPTH  write/read-back of every index on every port")
for name, op, depth, width, n_rd in inst:
    if op:
        check((isa[op]["entries"], isa[op]["width"]) == (depth, width), f"{name} size vs yaml")
    rf = RegFile(depth, width, n_rd, seed=5)
    ok = (1 << rf.idx_w) == depth
    rng = random.Random(name)
    good = True
    for i in range(1 << rf.idx_w):
        v = rng.getrandbits(width)
        rd, dbg = rf.cycle(1, i, v, [i] * n_rd, i)        # write-through
        good &= rd == [v] * n_rd and dbg == v
        rd, dbg = rf.cycle(0, 0, 0, [i] * n_rd, i)        # stored
        good &= rd == [v] * n_rd and dbg == v
    print(f"   {name:<8} {depth:>6} {width:>5} {n_rd:>4} {rf.idx_w:>5}  {str(ok):<16} {'ok' if good else 'FAIL'}")
    check(ok and good, f"{name}: index width and read-back")

# 5. Packed port layout -----------------------------------------------------------
print("\n5. Packed layout of rd_idx and rd_data (grf_b: N_RD = 3, IDX_W = 3, WIDTH = 256)")
idx = [5, 0, 3]
flat = sum(i << (p * 3) for p, i in enumerate(idx))
print(f"   ports 0, 1, 2 read entries {idx}: rd_idx = 0x{flat:03X} (9 bits, port p in [3p+2:3p])")
check(flat == 0x0C5, "rd_idx packing example")
print("   rd_data is 768 bits; port p's entry is rd_data[256p+255:256p]")

# 6. GEMV accumulator bypass on grf_b's ports ---------------------------------------
print("\n6. grf_b ports in cycles 5-7 of the GEMV case (hierarchy.md); lane 0, FP16")
gemv = [  # cycle, wr (en, idx, data), rd_idx [p0, p1, p2], port that matters, expected
    (5, (1, 0, 0x3800), [0, 0, 0], 2, 0x3800),   # S5 PC0 writes 0.5; S4 PC1 reads acc on port 2
    (6, (1, 0, 0x3C00), [0, 0, 0], 2, 0x3C00),   # S5 PC1 writes 1.0; S4 PC2 reads acc on port 2
    (7, (1, 0, 0x4700), [0, 0, 0], 0, 0x4700),   # S5 PC2 writes 7.0; S2 PC4 reads on port 0
]
for wt, label in ((True, "write-through (chosen)"), (False, "(b) stored value only")):
    rf = RegFile(8, 256, 3, seed=6, write_through=wt)
    rf.entry[0] = 0xBC00  # -1.0 from an earlier run, lane 0 (hierarchy.md)
    out = []
    for cyc, (en, wi, wd), ridx, port, exp in gemv:
        rd, _ = rf.cycle(en, wi, wd, ridx, 0)
        out.append(f"c{cyc} port {port} = {h(rd[port])}")
        if wt:
            check(rd[port] == exp, f"GEMV cycle {cyc} port {port}")
    print(f"   {label:<24} " + ", ".join(out))
print("   0x3800 = 0.5, 0x3C00 = 1.0, 0x4700 = 7.0, 0xBC00 = -1.0. Under (b) each read is one write late,")
print("   which is the in-order mismatch of hierarchy.md's option (c).")

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all checks passed")
