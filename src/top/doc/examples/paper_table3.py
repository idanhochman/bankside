#!/usr/bin/env python3
"""Read the instruction format (Table III) out of the ISCA 2021 paper's PDF
and compare it with bankside_isa.yaml.

The paper is not in the repo (it is an IEEE Xplore download). Pass the path
to your copy:

    python3 src/top/doc/examples/paper_table3.py <paper.pdf>

Needs pypdf (the repo's .venv doesn't have it; a system python3 with pypdf
and PyYAML works). The text of Table III loses its column positions when
extracted as plain text, so this script reads the page's content stream
instead: the table's cell borders are vertical line segments, the bit
numbers 31..0 sit in the header row, and each field label sits inside its
cell. A field's bit range is the set of header columns its cell spans.

It also prints the Table II rows as text, and the Section III-C sentences on
MAC's SRC2 and MAD's SRC2 index, for the record.

Exits non-zero if a field in the paper and the yaml disagree, other than the
one difference the programmer's guide documents (data format bits 2-0).
"""
import re
import sys
from pathlib import Path

import pypdf
import yaml
from pypdf.generic import ContentStream

YAML = Path(__file__).resolve().parent.parent / "bankside_isa.yaml"
PAGE = 5            # Table II and Table III are on page 5 (paper p. 47)

NAME = {"OPCODE": "opcode", "DST": "dst", "SRC0": "src0", "SRC1": "src1",
        "SRC2": "src2", "R": "relu", "A": "aam", "DST#": "dst_idx",
        "SRC0#": "src0_idx", "SRC1#": "src1_idx", "IMM0": "imm0",
        "IMM1": "imm1", "U": None}
# Documented in programmers_guide.md (Instruction formats): the paper labels
# data-format bits 2-0 SRC1#; bankside leaves them unused (MOV and FILL have
# no SRC1), which the hardware treats the same way (ignored).
KNOWN = {("data", 2), ("data", 1), ("data", 0)}


def mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def page_items(reader, n):
    """Text runs (x, y, s) and vertical segments (x, y0, y1), page coords."""
    page = reader.pages[n - 1]
    cs = ContentStream(page.get_contents(), reader)
    ident = [1, 0, 0, 1, 0, 0]
    cm, stack, tm, tlm, lead = ident[:], [], ident[:], ident[:], 0.0
    texts, segs, cur = [], [], None
    for ops, op in cs.operations:
        op = op.decode() if isinstance(op, bytes) else op
        if op == "q":
            stack.append(cm[:])
        elif op == "Q":
            cm = stack.pop()
        elif op == "cm":
            cm = mul([float(x) for x in ops], cm)
        elif op == "BT":
            tm = tlm = ident[:]
        elif op == "Tm":
            tm = tlm = [float(x) for x in ops]
        elif op in ("Td", "TD"):
            if op == "TD":
                lead = -float(ops[1])
            tlm = mul([1, 0, 0, 1, float(ops[0]), float(ops[1])], tlm)
            tm = tlm[:]
        elif op == "TL":
            lead = float(ops[0])
        elif op == "T*":
            tlm = mul([1, 0, 0, 1, 0, -lead], tlm)
            tm = tlm[:]
        elif op in ("Tj", "TJ"):
            arg = ops[-1]
            s = "".join(a for a in arg if isinstance(a, str)) if op == "TJ" else str(arg)
            m = mul(tm, cm)
            texts.append((m[4], m[5], s))
        elif op in ("m", "l"):
            p = mul([1, 0, 0, 1, float(ops[0]), float(ops[1])], cm)
            if op == "l" and cur and abs(cur[0] - p[4]) < 0.05:
                segs.append((cur[0], min(cur[1], p[5]), max(cur[1], p[5])))
            cur = (p[4], p[5])
    return texts, segs


reader = pypdf.PdfReader(sys.argv[1])
texts, segs = page_items(reader, PAGE)

# Locate Table III: its title, then the row labels below it.
title_y = next(y for x, y, s in texts if s.replace(" ", "").startswith("TABLEIII"))
rows = {s: y for x, y, s in texts if s in ("Control", "Data", "ALU") and y < title_y}
head_y = next(y for x, y, s in texts if s == "31" and title_y > y > rows["Control"])


def borders(y):
    """x of every vertical segment that crosses height y, sorted."""
    return sorted({round(x, 1) for x, y0, y1 in segs if y0 < y + 1 < y1 or y0 < y < y1})


def cells(y):
    xs = borders(y)
    out = []
    for lo, hi in zip(xs, xs[1:]):
        label = " ".join(s for x, ty, s in texts
                         if lo < x < hi and abs(ty - y) < 3).replace(" ", "")
        out.append((lo, hi, label))
    return out


header = [c for c in cells(head_y) if c[2].isdigit()]
assert [int(c[2]) for c in header] == list(range(31, -1, -1)), header
bit_at = [(lo, hi, int(b)) for lo, hi, b in header]


def span(lo, hi):
    bits = [b for blo, bhi, b in bit_at if blo >= lo - 0.2 and bhi <= hi + 0.2]
    return max(bits), min(bits)


isa = yaml.safe_load(YAML.read_text())
bad = 0
print(f"Table III, page {PAGE}: header columns at x = {bit_at[0][0]} .. {bit_at[-1][1]}")
for row, fmt in (("Control", "control"), ("Data", "data"), ("ALU", "alu")):
    paper = {}
    fields = []
    for lo, hi, label in cells(rows[row]):
        if label == row:
            continue
        msb, lsb = span(lo, hi)
        fields.append(f"{label} {msb}-{lsb}" if msb != lsb else f"{label} {msb}")
        for b in range(lsb, msb + 1):
            paper[b] = NAME[label]
    ours = {b: None for b in range(32)}
    for f, (msb, lsb) in isa["formats"][fmt]["fields"].items():
        for b in range(lsb, msb + 1):
            ours[b] = f
    print(f"  {row:7} paper: " + ", ".join(fields))
    for b in range(32):
        if paper.get(b) != ours[b]:
            tag = "known" if (fmt, b) in KNOWN else "MISMATCH"
            bad += tag == "MISMATCH"
            print(f"          bit {b:2}: paper {paper.get(b)}, yaml {ours[b]}  [{tag}]")
print("result: " + ("yaml matches Table III" if not bad else f"{bad} mismatched bits")
      + " (apart from the known data-format bits 2-0)")

# Table II, as text, for the record.
plain = reader.pages[PAGE - 1].extract_text()
t2 = plain[plain.index("TABLE II:"):plain.index("returns zero")]
print("\nTable II (plain text, columns: op, SRC0, SRC1, DST, # of combinations):")
for line in t2.splitlines():
    print("  " + line)

# Section III-C (page 6): the sentences on MAC's SRC2 and MAD's SRC2 index.
p6 = re.sub(r"\s+", " ", reader.pages[PAGE].extract_text())
m = re.search(r"MAC performs.*?respectively\)\.", p6)
print("\nSection III-C, page 6:\n  " + m.group(0))
sys.exit(1 if bad else 0)
