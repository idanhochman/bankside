#!/usr/bin/env python3
"""Worked cases and exhaustive checks for pcu_decode (src/pcu_decode/doc/README.md).

A bit-level model of pcu_decode as [DEC-3] to [DEC-14] state it, written
from the doc and bankside_isa.yaml. It is checked against the top spec's own
assembler, decoder and legality check (src/top/doc/examples/check_isa.py,
which reads the same yaml and checks it against the programmer's guide),
which the model does not use:

  1. Every word class: all 2^18 values of the fields that decide legality
     (opcode, DST, SRC0, SRC1, SRC2, A, R), index fields and unused bits 0.
     `illegal` must equal [TOP-ISA-2] without the JUMP range check (reserved
     opcode, or check_isa.legal(word) is false); `bank_rd`/`bank_sel` must
     be the bank source of a legal word; the decoded fields of every legal
     word must match check_isa.decode(word); and the word assembled back
     from that text must decode to the same output ([DEC-13]).
  2. Every legal operand combination with every value of the three index
     fields (512 each), checked against check_isa.decode ([TOP-ISA-9],
     [TOP-ISA-20]).
  3. The bits no field of the word's format names: every value of them on
     every legal combination (data 8 bits, ALU 5 bits); every IMM0 x IMM1
     and every unused-bit value of NOP, JUMP and EXIT ([TOP-ISA-25]); and
     200000 random 32-bit words (seed 31), against check_isa.
  4. The rules one by one: DEC_NOP ([DEC-14]), MAC's SRC2 ([DEC-8]), MAD's
     SRC2 ([TOP-ISA-23]), the MAC/MAD source pairs ([TOP-ISA-22]), one bank
     source at most ([TOP-ARCH-7]), what pcu_ctrl and pcu_datapath need
     (CTRL-15, DP-6).
  5. The tables of the doc (worked words, class counts, the choices), each
     of which must appear in the doc word for word, and the bitfield
     img/dec_instr_t.reg.json against the layout of [DEC-11].

Run from the repo root:
    .venv/bin/python src/pcu_decode/doc/examples/dec_check.py
Exits non-zero if a check fails or a table differs from the doc.
"""
import contextlib
import functools
import io
import json
import random
import re
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "README.md"
REG = HERE.parent / "img" / "dec_instr_t.reg.json"
TOPX = HERE.parents[2] / "top" / "doc" / "examples"
SPEC = DOC.read_text()
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def done(group):
    if failures:
        print(f"FAIL {group}")
        for f in failures[:40]:
            print("   ", f)
        if len(failures) > 40:
            print(f"    ... {len(failures) - 40} more")
        sys.exit(1)
    print(f"ok   {group}")


def load(name):
    """Run one of the top spec's example scripts quietly; return its globals."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            return runpy.run_path(str(TOPX / name))
    except SystemExit as e:
        print(out.getvalue())
        sys.exit(f"FAIL {name} exited with {e.code}")


isa = load("check_isa.py")              # parses bankside_isa.yaml and checks it
ref_assemble, ref_decode, ref_legal = isa["assemble"], isa["decode"], isa["legal"]
put = isa["put"]
# check_isa's legal() rebuilds a legal set on every call; cache it (same result).
ref_legal.__globals__["combos"] = functools.lru_cache(None)(ref_legal.__globals__["combos"])

YAML_INS, YAML_FMTS, YAML_OPS = isa["INS"], isa["FMTS"], isa["OPS"]
CODE = {k: v["code"] for k, v in YAML_OPS.items()}          # GRF_A -> 0 ...
NAME = {v: k for k, v in CODE.items()}                       # 0 -> GRF_A ...
BANK_CODES = {v["code"] for v in YAML_OPS.values() if v["kind"] == "bank"}
OPC = {v["opcode"]: k for k, v in YAML_INS.items()}           # 0 -> NOP ...

# ---------------------------------------------------------------------------
# The model of this doc. It reads the word only through the yaml's field
# positions ([DEC-4]) and the yaml's legal lists ([DEC-5] to [DEC-7]).
# ---------------------------------------------------------------------------
# [DEC-12] dec_op_e
DEC_OP = {"NONE": 0, "MOV": 1, "FILL": 2, "ADD": 3, "MUL": 4, "MAD": 5, "MAC": 6}
DEC_OP_NAME = {v: k for k, v in DEC_OP.items()}
# [DEC-11] dec_instr_t, most significant field first
LAYOUT = [("op", 3), ("dst", 3), ("src0", 3), ("src1", 3),
          ("dst_idx", 3), ("src0_idx", 3), ("src1_idx", 3), ("relu", 1)]
WIDTH = sum(w for _, w in LAYOUT)
FIELDS = [n for n, _ in LAYOUT]
DEC_NOP = dict.fromkeys(FIELDS, 0)                             # [DEC-14]


def pack(d):
    v = 0
    for name, w in LAYOUT:
        assert 0 <= d[name] < (1 << w), (name, d[name])
        v = (v << w) | d[name]
    return v


def field(w, fmt, name):
    msb, lsb = YAML_FMTS[fmt]["fields"][name]
    return (w >> lsb) & ((1 << (msb - lsb + 1)) - 1)


def entry_ok(mn, entry, f):
    """One yaml `legal` entry: each named field holds a listed operand, and
    the instruction's constraints hold on its sources."""
    for k, allowed in entry.items():
        if NAME.get(f[k]) not in allowed:
            return False
    srcs = [f[k] for k in ("src0", "src1") if k in entry]
    cons = YAML_INS[mn].get("constraints", [])
    if "one_bank_operand" in cons and sum(s in BANK_CODES for s in srcs) > 1:
        return False
    if "one_read_per_srf" in cons:
        for s in (CODE["SRF_M"], CODE["SRF_A"]):
            if srcs.count(s) > 1:
                return False
    return True


def model(w):
    """pcu_decode: (illegal, bank_rd, bank_sel, dec_instr) for one word."""
    mn = OPC.get(field(w, "control", "opcode"))
    if mn is None:                                   # reserved opcode [DEC-5]
        return 1, 0, 0, dict(DEC_NOP)
    ins = YAML_INS[mn]
    fmt = ins["format"]
    if fmt == "control":                             # [DEC-6]: never illegal
        return 0, 0, 0, dict(DEC_NOP)
    f = {k: field(w, fmt, k) for k in YAML_FMTS[fmt]["fields"]}
    ok = not (fmt == "alu" and f["aam"])             # [DEC-5]: A = 1
    ok = ok and any(entry_ok(mn, e, f) for e in ins["legal"])
    if not ok:                                       # [DEC-9]
        return 1, 0, 0, dict(DEC_NOP)
    alu = fmt == "alu"
    is_bank = lambda c: c in BANK_CODES
    d = {
        "op": DEC_OP[mn],
        "dst": f["dst"],
        "src0": f["src0"],
        "src1": f["src1"] if alu else 0,
        "dst_idx": 0 if is_bank(f["dst"]) else f["dst_idx"],
        "src0_idx": 0 if is_bank(f["src0"]) else f["src0_idx"],
        "src1_idx": (f["src1_idx"] if alu and (not is_bank(f["src1"]) or mn == "MAD")
                     else 0),
        "relu": f["relu"] if mn == "MOV" else 0,
    }
    banks = [c for c in ([f["src0"]] + ([f["src1"]] if alu else [])) if is_bank(c)]
    bank_rd = 1 if banks else 0                      # [DEC-10]
    bank_sel = 1 if banks and banks[0] == CODE["ODD_BANK"] else 0
    return 0, bank_rd, bank_sel, d


# ---------------------------------------------------------------------------
# The reference: check_isa.py's functions, plus the yaml facts they don't print.
# ---------------------------------------------------------------------------
def ref_illegal(w):
    """[TOP-ISA-2] for the word alone: legal(w) with pc=None treats every
    JUMP as legal, exactly the flag CTRL-15 asks for."""
    if (w >> 28) not in OPC:
        return 1
    return 0 if ref_legal(w) else 1


def ref_fields(w):
    """The decoded fields, parsed from check_isa.decode's text, for a legal
    data or ALU word. A bank operand has no index in the text: 0 ([DEC-13])."""
    text = ref_decode(w)
    mn, _, rest = text.partition(" ")
    relu = mn == "MOV(RELU)"
    mn = "MOV" if relu else mn
    ops = [a.strip() for a in rest.split(",")]
    parsed = []
    for a in ops:
        m = re.fullmatch(r"(\w+)(?:\[(\d)\])?", a)
        parsed.append((m.group(1), int(m.group(2)) if m.group(2) else 0))
    d = dict(DEC_NOP, op=DEC_OP[mn], relu=int(relu))
    d["dst"], d["dst_idx"] = CODE[parsed[0][0]], parsed[0][1]
    d["src0"], d["src0_idx"] = CODE[parsed[1][0]], parsed[1][1]
    if len(parsed) > 2:
        d["src1"], d["src1_idx"] = CODE[parsed[2][0]], parsed[2][1]
    if mn == "MAD":                       # SRF_A[j] with j = SRC1# [TOP-ISA-20]
        check(parsed[3][0] == "SRF_A", f"MAD addend {text}")
        d["src1_idx"] = parsed[3][1]
    return text, d


def ref_bank(w, illegal):
    mn = OPC.get(w >> 28)
    if illegal or YAML_INS[mn]["format"] == "control":
        return 0, 0
    fmt = YAML_INS[mn]["format"]
    srcs = [field(w, fmt, "src0")] + ([field(w, fmt, "src1")] if fmt == "alu" else [])
    banks = [c for c in srcs if c in BANK_CODES]
    return (1, int(banks[0] == CODE["ODD_BANK"])) if banks else (0, 0)


def compare(w, where):
    """Model vs reference for one word. Returns the model's output."""
    out = model(w)
    ill, brd, bsel, d = out
    want_ill = ref_illegal(w)
    check(ill == want_ill, f"{where} 0x{w:08X}: illegal {ill}, ref {want_ill}")
    check((brd, bsel) == ref_bank(w, want_ill),
          f"{where} 0x{w:08X}: bank {brd},{bsel}, ref {ref_bank(w, want_ill)}")
    mn = OPC.get(w >> 28)
    if not want_ill and mn and YAML_INS[mn]["format"] != "control":
        text, want = ref_fields(w)
        check(d == want, f"{where} 0x{w:08X} {text}: {d} != {want}")
        back = model(ref_assemble(text))
        check(back == out, f"{where} 0x{w:08X} {text}: assembled back decodes differently")
    else:
        check(d == DEC_NOP, f"{where} 0x{w:08X}: not DEC_NOP")
    return out


def word(opcode, dst=0, src0=0, src1=0, src2=0, aam=0, relu=0):
    """A word from the class fields at their yaml positions, everything else 0."""
    w = opcode << 28
    w = put(w, "alu", "dst", dst)
    w = put(w, "alu", "src0", src0)
    w = put(w, "alu", "src1", src1)
    w = put(w, "alu", "src2", src2)
    w = put(w, "alu", "aam", aam)
    w = put(w, "data", "relu", relu)
    return w


# 1. every word class ------------------------------------------------------------
REASONS = ["reserved opcode", "A = 1", "reserved code in a checked field",
           "MAD SRC2 not SRF_A", "combination not listed"]


def reason(w):
    """Why an illegal word is illegal: the first reason that applies."""
    mn = OPC.get(w >> 28)
    if mn is None:
        return REASONS[0]
    fmt = YAML_INS[mn]["format"]
    if fmt == "alu" and field(w, fmt, "aam"):
        return REASONS[1]
    checked = set().union(*(set(e) for e in YAML_INS[mn]["legal"]))
    if any(field(w, fmt, k) not in NAME for k in checked):
        return REASONS[2]
    if mn == "MAD" and field(w, fmt, "src2") != CODE["SRF_A"]:
        return REASONS[3]
    return REASONS[4]


per_op = {op: {"classes": 0, "legal": 0, "combos": set(), **{r: 0 for r in REASONS}}
          for op in range(16)}
legal_reps = []                     # one word per legal (combination, R, ignored SRC2)
n = 0
for op in range(16):
    for dst in range(8):
        for src0 in range(8):
            for src1 in range(8):
                for src2 in range(8):
                    for aam in range(2):
                        for relu in range(2):
                            w = word(op, dst, src0, src1, src2, aam, relu)
                            ill = compare(w, "class")[0]
                            s = per_op[op]
                            s["classes"] += 1
                            n += 1
                            if ill:
                                s[reason(w)] += 1
                                continue
                            s["legal"] += 1
                            mn = OPC[op]
                            fmt = YAML_INS[mn]["format"]
                            if fmt == "control":
                                continue
                            keys = sorted(set().union(*(set(e) for e in YAML_INS[mn]["legal"])))
                            s["combos"].add(tuple(field(w, fmt, k) for k in keys))
                            # Representatives for groups 2 and 3: the bits a format
                            # leaves unused are swept there, so keep them 0 here.
                            if fmt == "data" and (src1 or src2 or aam):
                                continue
                            if fmt == "alu" and relu:
                                continue
                            legal_reps.append(w)
done(f"1 {n} word classes (opcode, DST, SRC0, SRC1, SRC2, A, R): illegal, bank read "
     f"and fields == check_isa; every legal word assembles back to the same decode")

# 2. index fields -------------------------------------------------------------------
n = 0
for w0 in legal_reps:
    fmt = YAML_INS[OPC[w0 >> 28]]["format"]
    for di in range(8):
        for s0 in range(8):
            for s1 in (range(8) if fmt == "alu" else (0,)):
                w = put(put(w0, fmt, "dst_idx", di), fmt, "src0_idx", s0)
                if fmt == "alu":
                    w = put(w, fmt, "src1_idx", s1)
                compare(w, "index")
                n += 1
done(f"2 {len(legal_reps)} legal combinations x every index value: {n} words == check_isa")

# 3. bits no field names ----------------------------------------------------------
def unused_bits(fmt):
    used = set()
    for msb, lsb in YAML_FMTS[fmt]["fields"].values():
        used |= set(range(lsb, msb + 1))
    return sorted(set(range(32)) - used)


SPARE = {"data": [b for b in unused_bits("data") if b not in range(15, 22)],  # 21-15: swept in 1
         "alu": [b for b in unused_bits("alu") if b != 12]}                  # 12: swept in 1
n = 0
for w0 in legal_reps:
    fmt = YAML_INS[OPC[w0 >> 28]]["format"]
    base = model(w0)
    bits = SPARE[fmt]
    for v in range(1 << len(bits)):
        w = w0
        for i, b in enumerate(bits):
            if v >> i & 1:
                w |= 1 << b
        check(model(w) == base, f"spare bits 0x{w:08X}")
        n += 1
for w0 in legal_reps[::7]:          # and the reference agrees, on a seventh of them
    fmt = YAML_INS[OPC[w0 >> 28]]["format"]
    compare(w0 | sum(1 << b for b in SPARE[fmt]), "spare")
nc = 0
for mn in ("NOP", "JUMP", "EXIT"):
    op = YAML_INS[mn]["opcode"]
    for imm0 in range(256):
        for imm1 in range(2048):
            w = put(put(op << 28, "control", "imm0", imm0), "control", "imm1", imm1)
            check(model(w) == (0, 0, 0, DEC_NOP), f"control 0x{w:08X}")
            nc += 1
        compare(put(op << 28, "control", "imm0", imm0) | 0x7FF, "control")
    for v in range(1 << 9):                       # bits 27-19: unused in control
        compare((op << 28) | (v << 19), "control")
        nc += 1
rng = random.Random(31)
for _ in range(200000):
    compare(rng.getrandbits(32), "random")
done(f"3 unused bits: {n} words on the legal combinations (data bits {SPARE['data']}, "
     f"ALU bits {SPARE['alu']}); {nc} NOP/JUMP/EXIT words; 200000 random words")

# 4. the rules one by one ------------------------------------------------------------
# [DEC-14]: DEC_NOP is the decode of 0x00000000, packs to 0, and is the output
# exactly when op = NONE, that is for every control word and every illegal word.
check(model(0) == (0, 0, 0, DEC_NOP) and pack(DEC_NOP) == 0, "DEC_NOP")
check(WIDTH == 22, f"$bits(dec_instr_t) = {WIDTH}")
# [DEC-8], [TOP-ISA-10]: MAC's SRC2 changes nothing; MAD's is legal only as SRF_A.
mac = ref_assemble("MAC GRF_B[0], EVEN_BANK, SRF_M[0]")
outs = {repr(model(put(mac & ~(7 << 16), "alu", "src2", c))) for c in range(8)}
check(len(outs) == 1 and model(mac)[0] == 0, "MAC SRC2")
mad = ref_assemble("MAD GRF_A[0], ODD_BANK, SRF_M[2], SRF_A[2]")
check([model(put(mad & ~(7 << 16), "alu", "src2", c))[0] for c in range(8)]
      == [int(c != CODE["SRF_A"]) for c in range(8)], "MAD SRC2")
# [TOP-ISA-22]: MAC and MAD take MUL's 16 source pairs (from the class sweep).
def pairs(mn):
    keys = sorted(set().union(*(set(e) for e in YAML_INS[mn]["legal"])))
    return {(c[keys.index("src0")], c[keys.index("src1")]) for c in per_op[YAML_INS[mn]["opcode"]]["combos"]}


check(pairs("MAC") == pairs("MUL") == pairs("MAD") and len(pairs("MUL")) == 16, "ISA-22")
# [TOP-ARCH-7], [DEC-10]: a legal word has at most one bank source; a bank
# destination is never a read.
for w in legal_reps:
    ill, brd, bsel, d = model(w)
    srcs = [d["src0"]] + ([d["src1"]] if d["op"] >= DEC_OP["ADD"] else [])
    check(sum(s in BANK_CODES for s in srcs) == brd, f"bank count 0x{w:08X}")
    # DP-6: every legal word gives an operation pcu_datapath runs.
    check(d["op"] != DEC_OP["NONE"], f"legal word with op NONE 0x{w:08X}")
done("4 DEC_NOP; MAC SRC2 ignored (8 values, one output); MAD SRC2 legal only as SRF_A; "
     "MAC/MAD/MUL source pairs equal (16); at most one bank source")

# 5. the tables of the doc ------------------------------------------------------------
def opnd(c, used=True):
    return f"{NAME[c]}" if used else "0"


def row_fields(d):
    if d == DEC_NOP:
        return "NONE | 0 | 0 | 0 | 0, 0, 0 | 0"
    op = DEC_OP_NAME[d["op"]]
    alu = op in ("ADD", "MUL", "MAD", "MAC")
    return (f"{op} | {NAME[d['dst']]} | {NAME[d['src0']]} | "
            f"{NAME[d['src1']] if alu else '0'} | "
            f"{d['dst_idx']}, {d['src0_idx']}, {d['src1_idx']} | {d['relu']}")


def mod(text, *edits, raw=None):
    """A worked word: assembled from text, with fields then set by hand."""
    w = raw if raw is not None else ref_assemble(text)
    for fmt, f, v in edits:
        msb, lsb = YAML_FMTS[fmt]["fields"][f]
        w = (w & ~(((1 << (msb - lsb + 1)) - 1) << lsb)) | (v << lsb)
    return w


def bit(*bits):
    return sum(1 << b for b in bits)


CASES = [
    ("1", "`NOP 0`", mod("NOP 0"), "[DEC-14]: the word 0, `DEC_NOP`"),
    ("2", "`NOP 5`, IMM1 = 2047", mod("NOP 5", ("control", "imm1", 2047)),
     "[DEC-6]: IMM1 ignored ([TOP-ISA-25])"),
    ("3", "`JUMP -5, 1`", mod("JUMP -5, 1"),
     "[DEC-6]: legal here; out of range at PC 2 to 4, which `pcu_ctrl` checks"),
    ("4", "`JUMP -0, 0` (IMM0 = 0)", mod("JUMP -0, 0"),
     "[DEC-6]: legal here; out of range at every PC ([TOP-ISA-26])"),
    ("5", "`EXIT`, IMM0 = 255, IMM1 = 2047", mod("EXIT", ("control", "imm0", 255),
                                                ("control", "imm1", 2047)),
     "[DEC-6]: IMM0 and IMM1 ignored ([TOP-ISA-25])"),
    ("6", "opcode 3", mod("", raw=0x30000000), "[DEC-5]: reserved opcode"),
    ("7", "opcode 15, every other bit 1", mod("", raw=0xFFFFFFFF), "[DEC-5]: reserved opcode"),
    ("8", "`MOV GRF_A[0], EVEN_BANK`", mod("MOV GRF_A[0], EVEN_BANK"), "[DEC-10]: a bank load"),
    ("9", "`MOV(RELU) GRF_A[3], EVEN_BANK`, SRC0# = 5",
     mod("MOV(RELU) GRF_A[3], EVEN_BANK", ("data", "src0_idx", 5)),
     "[DEC-13]: a bank's index is 0 ([TOP-ISA-9])"),
    ("10", "`MOV ODD_BANK, GRF_B[2]`, DST# = 6",
     mod("MOV ODD_BANK, GRF_B[2]", ("data", "dst_idx", 6)),
     "[DEC-10]: a store is not a read; DST# 0 ([TOP-ISA-9])"),
    ("11", "`MOV SRF_M[2], GRF_A[1]`, bits 15 and 2–0 set",
     mod("MOV SRF_M[2], GRF_A[1]") | bit(15, 2, 1, 0),
     "[DEC-6]: unused bits ([TOP-ISA-1])"),
    ("12", "`FILL GRF_B[4], ODD_BANK`, R = 1",
     mod("FILL GRF_B[4], ODD_BANK", ("data", "relu", 1)),
     "[DEC-13]: R of FILL is 0 ([TOP-ISA-16])"),
    ("13", "`MOV GRF_B[0], EVEN_BANK`", mod("MOV GRF_B[0], EVEN_BANK"),
     "[DEC-7]: a crossed pair ([TOP-ISA-15])"),
    ("14", "`MOV GRF_A[0], GRF_B[0]`, SRC0 = 6",
     mod("MOV GRF_A[0], GRF_B[0]", ("data", "src0", 6)),
     "[DEC-5]: a reserved code in a checked field"),
    ("15", "`MOV GRF_A[0], GRF_B[0]`, SRC1 = 7",
     mod("MOV GRF_A[0], GRF_B[0]", ("alu", "src1", 7)),
     "[DEC-6]: MOV has no SRC1; bits 21–19 unused"),
    ("16", "`ADD GRF_A[2], EVEN_BANK, SRF_A[0]`, SRC2 = 7",
     mod("ADD GRF_A[2], EVEN_BANK, SRF_A[0]", ("alu", "src2", 7)),
     "[DEC-6]: SRC2 ignored, even reserved ([TOP-ISA-10])"),
    ("17", "`ADD GRF_A[0], EVEN_BANK, ODD_BANK`", mod("ADD GRF_A[0], EVEN_BANK, ODD_BANK"),
     "[DEC-7]: two bank sources ([TOP-ARCH-7])"),
    ("18", "`ADD GRF_B[1], SRF_A[0], SRF_A[1]`", mod("ADD GRF_B[1], SRF_A[0], SRF_A[1]"),
     "[DEC-7]: SRF_A read twice"),
    ("19", "`ADD GRF_A[0], GRF_B[1], GRF_B[2]`, bit 12 set",
     mod("ADD GRF_A[0], GRF_B[1], GRF_B[2]") | bit(12),
     "[DEC-13]: bit 12 is unused in the ALU format, `relu` 0"),
    ("20", "`MUL GRF_B[3], GRF_A[1], SRF_M[4]`", mod("MUL GRF_B[3], GRF_A[1], SRF_M[4]"),
     "[DEC-13]: every index used"),
    ("21", "`MUL GRF_B[3], GRF_A[1], SRF_M[4]`, A = 1",
     mod("MUL GRF_B[3], GRF_A[1], SRF_M[4]", ("alu", "aam", 1)), "[DEC-5]: A = 1 in v1"),
    ("22", "`MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]`",
     mod("MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]"),
     "[DEC-13]: MAD keeps SRC1# with a bank SRC1 ([TOP-ISA-20])"),
    ("23", "`MAD GRF_A[0], EVEN_BANK, SRF_M[2], GRF_B[2]`",
     mod("MAD GRF_A[0], EVEN_BANK, SRF_M[2], GRF_B[2]"),
     "[DEC-7]: MAD's SRC2 must be SRF_A ([TOP-ISA-23])"),
    ("24", "`MAC GRF_B[0], EVEN_BANK, SRF_M[0]` (SRC2 = 1, as assembled)",
     mod("MAC GRF_B[0], EVEN_BANK, SRF_M[0]"), "[DEC-8]"),
    ("25", "the same, SRC2 = 0", mod("MAC GRF_B[0], EVEN_BANK, SRF_M[0]", ("alu", "src2", 0)),
     "[DEC-8]: the same output as 24"),
    ("26", "the same, SRC2 = 7", mod("MAC GRF_B[0], EVEN_BANK, SRF_M[0]", ("alu", "src2", 7)),
     "[DEC-8]: the same output as 24"),
    ("27", "`MAC GRF_A[0], GRF_A[1], EVEN_BANK`", mod("MAC GRF_A[0], GRF_A[1], EVEN_BANK"),
     "[DEC-7]: MAC writes GRF_B only ([TOP-ISA-21])"),
    ("28", "`MAC GRF_B[0], GRF_A[1], GRF_A[2]`", mod("MAC GRF_B[0], GRF_A[1], GRF_A[2]"),
     "[DEC-7]: a same-file pair ([TOP-ISA-22])"),
]
lines = ["| # | Word | Instruction | `illegal` | `bank_rd`, `bank_sel` | `op` | `dst` | `src0` "
         "| `src1` | `dst_idx`, `src0_idx`, `src1_idx` | `relu` | `dec_instr` | Shows |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for num, text, w, why in CASES:
    out = compare(w, f"case {num}")
    ill, brd, bsel, d = out
    bank = f"1, {bsel} ({'ODD' if bsel else 'EVEN'})" if brd else "0, 0"
    lines.append(f"| {num} | `0x{w:08X}` | {text} | {ill} | {bank} | {row_fields(d)} "
                 f"| `0x{pack(d):06X}` | {why} |")
CASE_TABLE = "\n".join(lines)
# rows 24 to 26 decode the same
check(model(CASES[23][2]) == model(CASES[24][2]) == model(CASES[25][2]), "cases 24-26")
print(CASE_TABLE)
check(CASE_TABLE in SPEC, "the worked-word table differs from the doc")

# The class-count table.
lines = ["| Opcode | Instruction | Classes | Legal | Legal operand combinations "
         "| Reserved opcode | A = 1 | Reserved code in a checked field "
         "| MAD SRC2 not SRF_A | Combination not listed |",
         "|---|---|---|---|---|---|---|---|---|---|"]
tot = {k: 0 for k in ["classes", "legal", "combos"] + REASONS}
for op in range(16):
    s = per_op[op]
    mn = OPC.get(op, "reserved")
    nc = len(s["combos"]) if mn in ("MOV", "FILL", "ADD", "MUL", "MAD", "MAC") else "–"
    cells = [str(op), mn, str(s["classes"]), str(s["legal"]), str(nc)] + [str(s[r]) for r in REASONS]
    lines.append("| " + " | ".join(cells) + " |")
    for k in ["classes", "legal"] + REASONS:
        tot[k] += s[k]
    if nc != "–":
        tot["combos"] += nc
lines.append("| all | | " + " | ".join(str(tot[k]) for k in ["classes", "legal", "combos"] + REASONS) + " |")
COUNT_TABLE = "\n".join(lines)
print(COUNT_TABLE)
check(COUNT_TABLE in SPEC, "the class-count table differs from the doc")
# The legal-combination counts are the guide's (and VER-5's bins).
guide_counts = {"MOV": 20, "FILL": 4, "ADD": 40, "MUL": 32, "MAD": 32, "MAC": 16}
for mn, c in guide_counts.items():
    check(len(per_op[YAML_INS[mn]["opcode"]]["combos"]) == c, f"combos {mn}")

# Choices weighed: where the options differ, on the words of the case table.
def raw_fields(w):
    """Option (b) of the field choice: the word's fields passed as they are."""
    mn = OPC.get(w >> 28)
    if mn is None or YAML_INS[mn]["format"] == "control" or model(w)[0]:
        return dict(DEC_NOP)
    fmt = YAML_INS[mn]["format"]
    g = lambda k: field(w, fmt, k) if k in YAML_FMTS[fmt]["fields"] else 0
    return {"op": DEC_OP[mn], "dst": g("dst"), "src0": g("src0"), "src1": g("src1"),
            "dst_idx": g("dst_idx"), "src0_idx": g("src0_idx"), "src1_idx": g("src1_idx"),
            "relu": g("relu")}


pairs_same = [("9", "`MOV(RELU) GRF_A[3], EVEN_BANK`", mod("MOV(RELU) GRF_A[3], EVEN_BANK")),
              ("10", "`MOV ODD_BANK, GRF_B[2]`", mod("MOV ODD_BANK, GRF_B[2]")),
              ("12", "`FILL GRF_B[4], ODD_BANK`", mod("FILL GRF_B[4], ODD_BANK"))]
lines = ["| Case | Word with the ignored field set | The assembler's word | (a) canonical: same `dec_instr`? | (b) raw fields: same `dec_instr`? |",
         "|---|---|---|---|---|"]
for num, text, clean in pairs_same:
    w = CASES[int(num) - 1][2]
    a = model(w)[3] == model(clean)[3]
    b = raw_fields(w) == raw_fields(clean)
    lines.append(f"| {num} | `0x{w:08X}` | `0x{clean:08X}` {text} | {'yes' if a else 'no'} "
                 f"(`0x{pack(model(w)[3]):06X}`) | {'yes' if b else 'no'} "
                 f"(`0x{pack(raw_fields(w)):06X}` vs `0x{pack(raw_fields(clean)):06X}`) |")
CHOICE_TABLE = "\n".join(lines)
print(CHOICE_TABLE)
check(CHOICE_TABLE in SPEC, "the choice table differs from the doc")

# The bitfield figure against [DEC-11]: least significant field first.
reg = json.loads(REG.read_text())
got = [(e.get("name"), e["bits"]) for e in reg["reg"]]
check(got == [(n, w) for n, w in reversed(LAYOUT)], f"reg.json {got}")
check(reg["config"]["bits"] == WIDTH, "reg.json width")
# The layout table of [DEC-11] in the doc: name, bits.
msb = WIDTH - 1
for name, w in LAYOUT:
    rng_txt = f"{msb}–{msb - w + 1}" if w > 1 else f"{msb}"
    check(re.search(rf"^ *\| `{name}` \| [^|]+ \| {rng_txt} \|", SPEC, re.M) is not None,
          f"layout row {name} {rng_txt}")
    msb -= w
# The enum table of [DEC-12].
for k, v in DEC_OP.items():
    check(f"| `DEC_OP_{k}` | {v} |" in SPEC, f"enum row DEC_OP_{k}")
for k, v in CODE.items():
    check(f"| `OPND_{k}` | {v} |" in SPEC, f"enum row OPND_{k}")
done("5 worked-word, class-count and choice tables == doc; dec_instr_t.reg.json and "
     "the layout and enum tables == [DEC-11], [DEC-12]")
