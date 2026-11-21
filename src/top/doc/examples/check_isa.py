#!/usr/bin/env python3
"""Consistency checks for the top spec (src/top/doc/).

Checks, in order:
  1. bankside_isa.yaml parses, and every format's fields fit in 32 bits
     without overlapping.
  2. The programmer's guide format table matches the yaml bit for bit.
  3. The opcode and operand-code tables match the yaml.
  4. The legal-combination counts, computed from the yaml, match the guide.
  5. The guide's assembler examples assemble from the yaml encoding, decode
     back to the same text, and are legal; the [TOP-ISA-22] and [TOP-ISA-23]
     cases; every instruction word the guide writes out encodes as written.
  6. Requirement IDs: each is defined (in bold) exactly once, and every
     reference points to a defined ID.
  7. Every relative Markdown link resolves, including #anchors.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/check_isa.py
Exits non-zero on the first failing group; prints what it checked.
"""
import itertools
import re
import sys
from pathlib import Path

import yaml

DOC = Path(__file__).resolve().parent.parent
TOP = DOC.parent
YAML = DOC / "bankside_isa.yaml"
GUIDE = DOC / "programmers_guide.md"

isa = yaml.safe_load(YAML.read_text())
FMTS = isa["formats"]
OPS = isa["operands"]
INS = isa["instructions"]
CODE2OP = {v["code"]: k for k, v in OPS.items()}
BANKS = {k for k, v in OPS.items() if v["kind"] == "bank"}
SRFS = {k for k, v in OPS.items() if v["kind"] == "srf"}

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def done(group):
    if failures:
        print(f"FAIL {group}")
        for f in failures:
            print("   ", f)
        sys.exit(1)
    print(f"ok   {group}")


# 1. yaml shape ---------------------------------------------------------------
for fname, fmt in FMTS.items():
    owner = {}
    for field, (msb, lsb) in fmt["fields"].items():
        check(31 >= msb >= lsb >= 0, f"{fname}.{field} range [{msb},{lsb}]")
        for b in range(lsb, msb + 1):
            check(b not in owner, f"{fname}: bit {b} in {owner.get(b)} and {field}")
            owner[b] = field
done("1 yaml parses; fields fit in 32 bits and don't overlap")

# 2. format table vs yaml -------------------------------------------------------
NAME = {"OPCODE": "opcode", "DST": "dst", "SRC0": "src0", "SRC1": "src1",
        "SRC2": "src2", "R": "relu", "A": "aam", "DST#": "dst_idx",
        "SRC0#": "src0_idx", "SRC1#": "src1_idx", "IMM0": "imm0",
        "IMM1": "imm1", "–": None}
guide = GUIDE.read_text()
rows = [l for l in guide.splitlines() if l.startswith("| Bits") or
        re.match(r"\| \*\*(Control|Data|ALU)\*\*", l)]
cols = [c.strip() for c in rows[0].strip("|").split("|")][1:]
spans = []
for c in cols:
    hi, _, lo = c.partition("–")
    spans.append((int(hi), int(lo or hi)))
for row in rows[1:]:
    cells = [c.strip() for c in row.strip("|").split("|")]
    fname = cells[0].strip("*").lower()
    table_bits = {}
    for (hi, lo), cell in zip(spans, cells[1:]):
        for b in range(lo, hi + 1):
            table_bits[b] = NAME[cell]
    yaml_bits = {b: None for b in range(32)}
    for field, (msb, lsb) in FMTS[fname]["fields"].items():
        for b in range(lsb, msb + 1):
            yaml_bits[b] = field
    for b in range(32):
        check(table_bits[b] == yaml_bits[b],
              f"{fname} bit {b}: table {table_bits[b]} yaml {yaml_bits[b]}")
done("2 guide format table == yaml formats (all 32 bits, 3 formats)")

# 3. opcode / operand tables ------------------------------------------------------
sec = guide.split("## Opcodes and operand codes")[1].split("##")[0]
for line in sec.splitlines():
    m = re.match(r"\| (\d+) \| (\w+) \| (\w+) \| \| ([\d, ]*) \| (\w*) \|", line)
    if m:
        op, name, fmt, code, opnd = m.groups()
        check(INS[name]["opcode"] == int(op), f"opcode {name}")
        check(INS[name]["format"] == fmt.lower(), f"format {name}")
        if code.strip().isdigit():
            check(OPS[opnd]["code"] == int(code), f"operand {opnd}")
used = {v["opcode"] for v in INS.values()}
check(sorted(set(range(16)) - used) == [3, 6, 7, 12, 13, 14, 15], "reserved opcodes")
check(sorted(set(range(8)) - set(CODE2OP)) == [6, 7], "reserved operand codes")
done("3 opcode and operand-code tables == yaml; reserved sets match")


# 4. legal-combination counts -------------------------------------------------------
def combos(name):
    ins = INS[name]
    out = set()
    for entry in ins["legal"]:
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
            out.add(tuple(sorted(c.items())))
    return out


lc = guide.split("### Legal combinations compared with the paper")[1].split("##")[0]
for line in lc.splitlines():
    m = re.match(r"\| (MUL|ADD|MAC|MAD|MOV|FILL) \| (\d+)", line)
    if m:
        n = len(combos(m.group(1)))
        print(f"       {m.group(1):4} yaml {n:3}  guide {m.group(2)}")
        check(n == int(m.group(2)), f"count {m.group(1)}: yaml {n}, guide {m.group(2)}")

# [TOP-ISA-22]: MAC and MAD take exactly MUL's 16 source pairs.
def src_pairs(name):
    return {(dict(c)["src0"], dict(c)["src1"]) for c in combos(name)}


for op in ("MAC", "MAD"):
    check(src_pairs(op) == src_pairs("MUL"), f"ISA-22: {op} source pairs != MUL's")
print(f"       MAC, MAD source pairs == MUL's: {len(src_pairs('MUL'))} [TOP-ISA-22]")
# [TOP-ISA-23]: MAD's SRC2 is SRF_A in every legal combination.
check({dict(c)["src2"] for c in combos("MAD")} == {"SRF_A"}, "ISA-23: MAD src2")
print("       MAD src2 in every legal combination: SRF_A [TOP-ISA-23]")
done("4 legal-combination counts from the yaml == guide table")


# 5. assemble / decode --------------------------------------------------------------
def put(word, fmt, field, val):
    msb, lsb = FMTS[fmt]["fields"][field]
    assert 0 <= val < (1 << (msb - lsb + 1)), (field, val)
    return word | (val << lsb)


def get(word, fmt, field):
    msb, lsb = FMTS[fmt]["fields"][field]
    return (word >> lsb) & ((1 << (msb - lsb + 1)) - 1)


def opnd(tok):
    m = re.fullmatch(r"(\w+)(?:\[(\d)\])?", tok.strip())
    return m.group(1), int(m.group(2)) if m.group(2) else 0


def assemble(line):
    line = line.split(";")[0].strip()
    mn, _, rest = line.partition(" ")
    relu = mn == "MOV(RELU)"
    mn = "MOV" if relu else mn
    ins = INS[mn]
    fmt = ins["format"]
    w = put(0, fmt, "opcode", ins["opcode"])
    args = [a.strip() for a in rest.split(",")] if rest else []
    if fmt == "control":
        if mn == "NOP":
            w = put(w, fmt, "imm0", int(args[0]))
        if mn == "JUMP":
            w = put(w, fmt, "imm0", -int(args[0]))
            w = put(w, fmt, "imm1", int(args[1]))
        return w
    fields = ["dst", "src0", "src1", "src2"]
    for f, a in zip(fields, args):
        name, idx = opnd(a)
        w = put(w, fmt, f, OPS[name]["code"])
        if f == "src2":           # MAD: the SRF_A index lives in src1_idx
            if CODE2OP[get(w, fmt, "src1")] in BANKS:
                w = put(w, fmt, "src1_idx", idx)
            else:
                assert idx == get(w, fmt, "src1_idx"), f"[TOP-ISA-20] {line}"
        elif name not in BANKS:   # [TOP-ISA-9]: banks have no index
            w = put(w, fmt, f + "_idx", idx)
    if relu:
        w = put(w, fmt, "relu", 1)
    return w


def decode(w):
    op = w >> 28
    mn = next(k for k, v in INS.items() if v["opcode"] == op)
    ins = INS[mn]
    fmt = ins["format"]
    if mn == "NOP":
        return f"NOP {get(w, fmt, 'imm0')}"
    if mn == "JUMP":
        return f"JUMP -{get(w, fmt, 'imm0')}, {get(w, fmt, 'imm1')}"
    if mn == "EXIT":
        return "EXIT"
    fields = ["dst", "src0"] + (["src1"] if fmt == "alu" else [])
    if mn == "MAD":
        fields.append("src2")
    parts = []
    for f in fields:
        name = CODE2OP.get(get(w, fmt, f), "reserved")
        idx_field = "src1_idx" if f == "src2" else f + "_idx"
        parts.append(name if name in BANKS else f"{name}[{get(w, fmt, idx_field)}]")
    if mn == "MOV" and get(w, fmt, "relu"):
        mn = "MOV(RELU)"
    return f"{mn} " + ", ".join(parts)


def legal(w):
    mn = decode(w).split()[0].replace("(RELU)", "")
    fmt = INS[mn]["format"]
    if fmt == "control":
        return True
    keys = ["dst", "src0"] + (["src1"] if fmt == "alu" else [])
    if mn == "MAD":
        keys.append("src2")
    if fmt == "alu" and get(w, fmt, "aam"):
        return False
    c = tuple(sorted((k, CODE2OP.get(get(w, fmt, k), "reserved")) for k in keys))
    return c in combos(mn)


def norm(s):
    return re.sub(r"\s+", " ", s.split(";")[0]).strip()


blocks = re.findall(r"```\n(.*?)```", guide, re.S)
programs = [b for b in blocks if re.search(r"^(PC \d+\s+)?(NOP|MOV|MAC|JUMP)", b, re.M)]
n = 0
for prog in programs:
    for line in prog.splitlines():
        line = re.sub(r"^PC \d+\s+", "", line.strip())
        if not norm(line):
            continue
        line = norm(line).replace("n-1", "3")   # the ReLU kernel with n = 4
        w = assemble(line)
        back = decode(w)
        check(norm(back) == norm(line), f"roundtrip {line!r} -> {back!r}")
        check(legal(w), f"illegal: {line}")
        print(f"       0x{w:08X}  {line}")
        n += 1
# The worked cases of [TOP-ISA-20]: a bank src1 carries j in SRC1#.
w = assemble("MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]")
check(get(w, "alu", "src1_idx") == 5, "ISA-20 bank src1 index")
print(f"       0x{w:08X}  MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]  (SRC1# = 5)")
try:
    assemble("MAD GRF_A[0], GRF_B[1], SRF_M[2], SRF_A[3]")
    check(False, "ISA-20: j != src1 index was accepted")
except AssertionError:
    print("       rejected  MAD GRF_A[0], GRF_B[1], SRF_M[2], SRF_A[3]  (j != SRC1#)")
# [TOP-ISA-10]: ADD with a reserved code in SRC2 is still legal.
w = put(assemble("ADD GRF_A[2], EVEN_BANK, SRF_A[0]"), "alu", "src2", 7)
check(legal(w), "ISA-10: reserved SRC2 made ADD illegal")
print(f"       0x{w:08X}  ADD GRF_A[2], EVEN_BANK, SRF_A[0] with SRC2 = 7: legal")
# [TOP-ISA-23]: a MAD whose SRC2 isn't SRF_A is illegal, whatever it holds.
base = assemble("MAD GRF_A[0], ODD_BANK, SRF_M[2], SRF_A[2]")
for code in range(8):
    w = (base & ~(7 << 16)) | (code << 16)
    check(legal(w) == (code == OPS["SRF_A"]["code"]), f"ISA-23: SRC2 = {code}")
print(f"       MAD ... SRF_M[2], <SRC2 = 0..7>: legal only for {OPS['SRF_A']['code']} (SRF_A)")
# [TOP-ISA-22]: the same-file pairs are legal for MAC and MAD.
for line in ("MAC GRF_B[0], GRF_A[1], GRF_A[2]", "MAC GRF_B[0], GRF_B[1], GRF_B[2]",
             "MAD GRF_A[0], GRF_A[1], GRF_A[2], SRF_A[2]"):
    w = assemble(line)
    check(legal(w), f"ISA-22: {line} illegal")
    print(f"       0x{w:08X}  {line}: legal")
# Every `instruction` | `0xWORD` row in a guide table encodes as written, and
# the bankside column says "illegal" exactly when the word is illegal.
for m in re.finditer(r"^\| `([^`]+)` \| `0x([0-9A-F]{8})` \| ([^|]*)\|", guide, re.M):
    line, word, what = m.group(1), int(m.group(2), 16), m.group(3)
    w = assemble(line)
    check(w == word, f"table word {line}: 0x{word:08X}, assembles to 0x{w:08X}")
    check(legal(w) == (not what.strip().startswith("illegal")), f"table legality {line}")
    print(f"       0x{w:08X}  {line}: {'legal' if legal(w) else 'illegal'} (guide table)")
# ... and so does every "`instruction` (`0xWORD`)" in the guide's prose.
for m in re.finditer(r"`([A-Z]+ [^`]+)` \(`0x([0-9A-F]{8})`\)", guide):
    w = assemble(m.group(1))
    check(w == int(m.group(2), 16), f"prose word {m.group(1)}: 0x{m.group(2)}, assembles to 0x{w:08X}")
    print(f"       0x{w:08X}  {m.group(1)} (guide prose)")
done(f"5 {n} example lines assemble, decode back and are legal")

# 6. requirement IDs ------------------------------------------------------------------
ID = r"TOP-[A-Z]+-\d+"
defs, refs = {}, set()
docs = sorted(DOC.glob("*.md"))
for p in docs:
    text = p.read_text()
    for m in re.finditer(rf"\*\*\[({ID})\]\*\*", text):
        defs.setdefault(m.group(1), []).append(p.name)
    refs |= set(re.findall(rf"\[({ID})\]", text))
refs |= set(re.findall(rf"\[({ID})\]", YAML.read_text()))
for i, where in defs.items():
    check(len(where) == 1, f"{i} defined {len(where)} times: {where}")
for i in sorted(refs - set(defs)):
    check(False, f"{i} referenced but never defined")
plain = re.sub(r"`[^`]*`", "", "".join(p.read_text() for p in docs))
for m in re.findall(r"\[(?:ARCH|ISA|FP|PIPE|HAZ|IF)-\d+\]", plain):
    check(False, f"unprefixed ID left: {m}")
key = lambda s: (s.split("-")[1], int(s.split("-")[2]))
by_area = {}
for i in sorted(defs, key=key):
    by_area.setdefault(i.split("-")[1], []).append(int(i.split("-")[2]))
for a, ns in by_area.items():
    print(f"       {a:4} {ns}")
done(f"6 {len(defs)} IDs, each defined once; all references defined")


# 7. links ---------------------------------------------------------------------------
def slugs(path):
    out = set()
    for h in re.findall(r"^#+ (.*)$", path.read_text(), re.M):
        s = re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
        out.add(s)
    return out


n = 0
for p in docs + [TOP / "dv" / "README.md", TOP / "README.md"]:
    for target in re.findall(r"\]\(([^)]+)\)", p.read_text()):
        if re.match(r"https?:", target):
            continue
        file, _, anchor = target.partition("#")
        dest = (p.parent / file).resolve() if file else p
        check(dest.exists(), f"{p.name}: {target} missing")
        if anchor and dest.exists() and dest.suffix == ".md":
            check(anchor in slugs(dest), f"{p.name}: anchor {target}")
        n += 1
done(f"7 {n} relative links resolve")
