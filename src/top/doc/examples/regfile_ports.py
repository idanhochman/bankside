#!/usr/bin/env python3
"""Read ports each register file needs, computed from bankside_isa.yaml.

Backs the pcu_regfile instance table in ../hierarchy.md ([TOP-HIER-4]).

For every legal operand combination of every instruction (the yaml `legal`
lists and constraints, the same expansion as check_isa.py), count how many
entries of each register file the instruction reads in S2 (its sources) and
in S4 (the MAC accumulator, GRF_B[DST#], [TOP-HAZ-2]). Different
instructions sit in S2 and S4 in the same cycle, so a file needs
max(S2 reads) + max(S4 reads) ports. The script checks the result against the
read-port column of the register-file table in theory_of_operation.md.

It also shows the two alternatives named for R1 and R11 (issues #6 and #8):
removing the same-file source pairs from MAC/MAD, or GRF_B as a MAC
multiplier source, doesn't change GRF_B's count, because ADD and MUL with
two GRF_B sources can be in S2 while a MAC is in S4.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/regfile_ports.py
Exits non-zero if the counts disagree with the theory-of-operation table.
"""
import itertools
import re
import sys
from pathlib import Path

import yaml

DOC = Path(__file__).resolve().parent.parent
isa = yaml.safe_load((DOC / "bankside_isa.yaml").read_text())
OPS, INS = isa["operands"], isa["instructions"]
BANKS = {k for k, v in OPS.items() if v["kind"] == "bank"}
SRFS = {k for k, v in OPS.items() if v["kind"] == "srf"}
FILES = [k for k, v in OPS.items() if v["kind"] in ("grf", "srf")]


def combos(name, drop=lambda c: False):
    """Legal operand combinations of one instruction, as dicts."""
    ins = INS[name]
    out = []
    for entry in ins.get("legal", []):
        keys = sorted(entry)
        for vals in itertools.product(*(entry[k] for k in keys)):
            c = dict(zip(keys, vals))
            srcs = [c[k] for k in ("src0", "src1") if k in c]
            if "one_bank_operand" in ins.get("constraints", []):
                if sum(s in BANKS for s in srcs) > 1:
                    continue
            if "one_read_per_srf" in ins.get("constraints", []):
                if any(srcs.count(s) > 1 for s in SRFS):
                    continue
            if not drop(c):
                out.append(c)
    return out


def reads(name, c):
    """(S2 reads, S4 reads) per register file for one combination."""
    s2 = {f: 0 for f in FILES}
    s4 = {f: 0 for f in FILES}
    for k in ("src0", "src1", "src2"):
        if c.get(k) in s2:
            s2[c[k]] += 1
    if name == "MAC":
        s4["GRF_B"] += 1          # the accumulator, read in S4
    return s2, s4


def ports(drop=lambda name, c: False):
    s2max = {f: 0 for f in FILES}
    s4max = {f: 0 for f in FILES}
    witness = {}
    for name in INS:
        for c in combos(name, lambda c, n=name: drop(n, c)):
            s2, s4 = reads(name, c)
            for f in FILES:
                if s2[f] > s2max[f]:
                    s2max[f] = s2[f]
                    witness[f] = (name, c)
                s4max[f] = max(s4max[f], s4[f])
    return s2max, s4max, witness


def show(title, s2max, s4max, witness=None):
    print(title)
    print(f"  {'file':6} {'S2':>3} {'S4':>3} {'ports':>5}  S2 peak reached by")
    for f in FILES:
        w = ""
        if witness and f in witness:
            n, c = witness[f]
            w = f"{n} " + ", ".join(f"{k}={c[k]}" for k in ("dst", "src0", "src1", "src2") if k in c)
        print(f"  {f:6} {s2max[f]:3} {s4max[f]:3} {s2max[f] + s4max[f]:5}  {w}".rstrip())


s2max, s4max, witness = ports()
show("Read ports from the yaml legal lists (S2 sources + S4 accumulator):", s2max, s4max, witness)

# The table in theory_of_operation.md, e.g. "| GRF_B | 8 × 256-bit | 2 (S2) + 1 (S4, accumulator) |"
table = {}
for line in (DOC / "theory_of_operation.md").read_text().splitlines():
    m = re.match(r"\| (GRF_A|GRF_B|SRF_M|SRF_A) \| [^|]+\| ([^|]+)\|", line)
    if m:
        table[m.group(1)] = sum(int(n) for n in re.findall(r"(\d+) \(", m.group(2)))
bad = [f for f in FILES if table.get(f) != s2max[f] + s4max[f]]
for f in FILES:
    print(f"  {f:6} theory_of_operation.md: {table.get(f)}  yaml: {s2max[f] + s4max[f]}")
if bad:
    print(f"FAIL read ports disagree for {bad}")
    sys.exit(1)
print("ok   read-port counts from the yaml == theory_of_operation.md register-file table\n")

# Alternatives, to show where they would and wouldn't change the count.
same_pair = lambda n, c: n in ("MAC", "MAD") and c.get("src0") == c.get("src1") and c.get("src0", "").startswith("GRF")
a2, a4, _ = ports(same_pair)
show("R1 alternative: MAC/MAD without (GRF_A, GRF_A) and (GRF_B, GRF_B):", a2, a4)
no_grfb_mac = lambda n, c: n == "MAC" and "GRF_B" in (c.get("src0"), c.get("src1"))
b2, b4, bw = ports(no_grfb_mac)
show("R11 alternative: no GRF_B as a MAC multiplier source:", b2, b4, bw)
print("  GRF_B still needs", b2["GRF_B"] + b4["GRF_B"], "ports: an ADD or MUL with two GRF_B sources in S2")
print("  and a MAC reading its accumulator in S4 can be in the pipeline in the same cycle.")
