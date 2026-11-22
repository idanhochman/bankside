#!/usr/bin/env python3
"""Worked cases for pcu_datapath (src/pcu_datapath/doc/README.md), cycle by cycle.

A cycle-level, bit-level model of pcu_datapath as [DP-4] to [DP-17] state it:
the S2/S3, S3/S4 and S4/S5 registers and their valid bits, the S2 read-port
use, the SRF broadcast, ReLU, the 16 lanes of multiply and add, the MAC
accumulator read through grf_b's port 2, the S5 write ports and bank_wr_*,
and the busy term. Around it, the parts of top the cases need:

  pcu_regfile  the four GRF/SRF instances with their N_RD, combinational
               write-through reads and the write at the edge ([RF-7], [RF-9]);
  pcu_ctrl     a stand-in for S1 without JUMPs: one slot per cycle with
               trig_valid = 1 and rst_n = 1, NOP slots and EXIT issued as
               DEC_NOP, the trigger's row and column in the issue bundle, the
               bank read request ([CTRL-5], [CTRL-11], [CTRL-12]);
  the v1 bank  a read sampled at the end of S1 and returned in S2, a store
               written at the end of S5, the store applied first on a shared
               edge ([TOP-IF-2], [TOP-IF-3]).

fp16_mul and fp16_add don't have their docs yet (#33, #34). Their stand-ins
compute in double precision and round once to binary16 with struct, which is
correctly rounded with ties to even ([TOP-FP-2]); a NaN result is 0x7E00
([TOP-FP-6]). pcu_decode doesn't have its doc yet either (#31): words are
assembled and checked by the top spec's own check_isa.py, and the decoded
instruction is the word's yaml fields.

What it prints and checks:
  1. Cases A to F of the doc, each a table that must appear in the doc word
     for word, with the options of "Choices weighed" where a case shows them.
  2. Figure 1 (img/dp_gemv.wave.json) against the model of case A, cell by
     cell.
  3. Case A against the top spec's module_trace.py (the same GEMV program):
     the same bank write, cycle, column and 16 lanes.
  4. Every legal operand combination of the yaml (MOV with R = 0 and 1):
     at most one use of each read port, the port counts against
     regfile_ports.py, and 20 random runs of each against in-order execution,
     all 16 lanes, with random values in the fields the datapath ignores.
  5. ReLU and the bit copy on all 65536 lane patterns through MOV(RELU), MOV
     and FILL, against fp_relu_nan.py's relu_bankside.
  6. Random programs: (a) legal programs keeping [TOP-HAZ-3] and [TOP-HAZ-6],
     random bubbles, against in-order execution, all lanes and every bank
     column; (b) the top spec's hazard_trace.py programs (legal ones only),
     legal or not under [TOP-HAZ-3], against its pipeline model, lane 0;
     (c) random resets: busy and the valid bits against [TOP-IF-7] term 1,
     at most one write per cycle.

Run from the repo root:
    .venv/bin/python src/pcu_datapath/doc/examples/dp_trace.py
Exits non-zero if a check fails or a table differs from the doc.
"""
import contextlib
import io
import json
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "README.md"
WAVE = HERE.parent / "img" / "dp_gemv.wave.json"
TOPX = HERE.parents[2] / "top" / "doc" / "examples"
GUIDE = HERE.parents[2] / "top" / "doc" / "programmers_guide.md"
SPEC = DOC.read_text()
failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def load(name, argv=()):
    """Run one of the top spec's example scripts quietly; return its globals.
    Its own checks must pass (exit code 0)."""
    path = TOPX / name
    g = {"__name__": "__main__", "__file__": str(path)}
    out, old = io.StringIO(), sys.argv
    sys.argv = [str(path), *argv]
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(path.read_text(), str(path), "exec"), g)
    except SystemExit as e:
        if e.code not in (0, None):
            print(out.getvalue())
            sys.exit(f"FAIL {name} exited with {e.code}")
    finally:
        sys.argv = old
    return g


isa = load("check_isa.py")
assemble, legal, get, decode_text = isa["assemble"], isa["legal"], isa["get"], isa["decode"]
INS, CODE2OP, BANKS, OPS, combos = isa["INS"], isa["CODE2OP"], isa["BANKS"], isa["OPS"], isa["combos"]
OPC = {v["opcode"]: k for k, v in INS.items()}
LANES = isa["isa"]["lanes"]
WRITERS = ("MOV", "FILL", "ADD", "MUL", "MAD", "MAC")        # [DP-13]
FILES = ("grf_a", "grf_b", "srf_m", "srf_a")
CODE_FILE = {"GRF_A": "grf_a", "GRF_B": "grf_b", "SRF_M": "srf_m", "SRF_A": "srf_a"}
N_RD = {"grf_a": 2, "grf_b": 3, "srf_m": 1, "srf_a": 1}       # [TOP-HIER-4]

# ---------------------------------------------------------------- FP16 --------------
def b2f(b):
    return struct.unpack("<e", struct.pack("<H", b))[0]


def f2b(x):
    if x != x:
        return 0x7E00
    try:
        return struct.unpack("<H", struct.pack("<e", x))[0]
    except OverflowError:                       # rounds to +-Inf under RNE
        return 0xFC00 if x < 0 else 0x7C00


def is_nan(b):
    return (b & 0x7FFF) > 0x7C00


def fmul(a, b):                                 # stand-in for fp16_mul (#33)
    if is_nan(a) or is_nan(b):
        return 0x7E00
    return f2b(b2f(a) * b2f(b))                 # exact in double, one rounding


def fadd(a, b):                                 # stand-in for fp16_add (#34)
    if is_nan(a) or is_nan(b):
        return 0x7E00
    return f2b(b2f(a) + b2f(b))


def relu(b):                                    # [TOP-FP-8]: the sign bit alone
    return 0x0000 if b & 0x8000 else b


def bcast(s):                                   # [TOP-ISA-11]
    return (s,) * LANES


def vec(f, *xs):
    return tuple(f(*t) for t in zip(*xs))


def lbl(b):
    """A lane value as the doc writes it: the FP16 value if it is a plain
    number, the bits otherwise."""
    v = b2f(b)
    if is_nan(b) or v in (float("inf"), float("-inf")) or b == 0x8000:
        return f"0x{b:04X}"
    return repr(v)


# -------------------------------------------------------- the decoded word ----------
def dec(w):
    """The decoded instruction as [DP-6] lists what pcu_datapath reads from
    iss_instr: the opcode and the yaml fields of its format. pcu_decode (#31)
    names and encodes them; here they are the word's bits."""
    mn = OPC.get(w >> 28, "reserved")
    d = {"op": mn, "word": w}
    if mn in ("MOV", "FILL"):
        f = "data"
        d.update(dst=CODE2OP.get(get(w, f, "dst")), src0=CODE2OP.get(get(w, f, "src0")),
                 src1=None, relu=get(w, f, "relu"), dst_idx=get(w, f, "dst_idx"),
                 src0_idx=get(w, f, "src0_idx"), src1_idx=None)
    elif mn in ("ADD", "MUL", "MAD", "MAC"):
        f = "alu"
        d.update(dst=CODE2OP.get(get(w, f, "dst")), src0=CODE2OP.get(get(w, f, "src0")),
                 src1=CODE2OP.get(get(w, f, "src1")), relu=0, dst_idx=get(w, f, "dst_idx"),
                 src0_idx=get(w, f, "src0_idx"), src1_idx=get(w, f, "src1_idx"))
    return d


DEC_NOP = dec(0x00000000)                       # [CTRL-12]


# --------------------------------------------------------------- [DP-7] --------------
def s2_ports(d):
    """[DP-7]: where each S2 operand of an entry comes from.
    Returns {operand: ("bank",) or (file, port, index)} for operands a, b, c."""
    def src(field, code, idx):
        if code in BANKS:
            return ("bank",)
        f = CODE_FILE[code]
        port = 1 if field == "src1" and f in ("grf_a", "grf_b") else 0
        return (f, port, idx)
    out = {}
    if d["op"] not in WRITERS:
        return out
    out["a"] = src("src0", d["src0"], d["src0_idx"])
    if d["op"] in ("ADD", "MUL", "MAD", "MAC"):
        out["b"] = src("src1", d["src1"], d["src1_idx"])
    if d["op"] == "MAD":
        out["c"] = ("srf_a", 0, d["src1_idx"])  # [TOP-ISA-20]: SRF_A[SRC1#]
    return out


# ------------------------------------------------------------- pcu_regfile ----------
class Regfile:
    """[RF-7] to [RF-9]: combinational write-through reads, write at the edge."""

    def __init__(self, mem):
        self.mem, self.wr = list(mem), (0, 0, None)

    def drive(self, en, idx, data):
        self.wr = (en, idx, data)

    def read(self, idx, through=True):
        en, wi, wd = self.wr
        if en and wi == idx and through:
            return wd, True
        return self.mem[idx], False

    def edge(self):
        en, wi, wd = self.wr
        if en:
            self.mem[wi] = wd


# ------------------------------------------------------------- the datapath ---------
def power_up_s5():
    return dict(grf_a_wr_en=0, grf_b_wr_en=0, srf_m_wr_en=0, srf_a_wr_en=0, bank_wr_en=0)


class Datapath:
    """pcu_datapath. Registers named as in [DP-4]; data fields as in its table.
    Options (Choices weighed): units = pass carried values through the FP16
    units (x * 1.0 in S3, x + (+0) in S4); gate_reset = gate the S5 write with
    rst_n; shared_port = ANEMOS's GRF_B port sharing (port 1 index ORed with
    the accumulator index, the accumulator read through port 1)."""

    def __init__(self, units=False, gate_reset=False, shared_port=False):
        self.units, self.gate_reset, self.shared_port = units, gate_reset, shared_port
        self.rng = random.Random(7)            # values for don't-care fields
        # state after a reset edge ([DP-4] reset values); data fields don't-care
        self.s3_valid = self.s4_valid = self.s5_valid = 0
        self.s3 = self.s4 = None
        self.s5 = dict(power_up_s5(), wr_idx=0, wr_data=bcast(0), bank_wr_sel=0,
                       bank_wr_row=0, bank_wr_col=0)

    # [DP-15]
    def busy(self):
        return self.s3_valid | self.s4_valid | self.s5_valid

    # [DP-13], [DP-14]: every S5 output is a bit of the S4/S5 register
    def s5_outputs(self):
        s = self.s5
        out = {}
        for f in FILES:
            out[f + "_wr_en"] = s[f + "_wr_en"]
            out[f + "_wr_idx"] = s["wr_idx"]
            out[f + "_wr_data"] = s["wr_data"] if f.startswith("grf") else s["wr_data"][0]
        for k in ("bank_wr_en", "bank_wr_sel", "bank_wr_row", "bank_wr_col"):
            out[k] = s[k]
        out["bank_wr_data"] = s["wr_data"]
        return out

    # [DP-7], [DP-11]: the read indices, combinational from iss_instr and S3/S4
    def rd_idx(self, iss, rng):
        idx = {f: [rng.randrange(8) for _ in range(N_RD[f])] for f in FILES}   # don't-care
        used = {}
        if iss["valid"]:
            for op, u in s2_ports(iss["instr"]).items():
                if u[0] != "bank":
                    f, p, i = u
                    assert (f, p) not in used, ("port used twice", iss["instr"], f, p)
                    used[(f, p)] = op
                    idx[f][p] = i
        if self.s4_valid and self.s4["instr"]["op"] == "MAC":
            idx["grf_b"][2] = self.s4["instr"]["dst_idx"]
            used[("grf_b", 2)] = "acc"
        if self.shared_port and self.s4_valid and self.s4["instr"]["op"] == "MAC":
            s2i = idx["grf_b"][1] if ("grf_b", 1) in used else 0
            idx["grf_b"][1] = s2i | self.s4["instr"]["dst_idx"]
        return idx, used

    def step(self, iss, rd, bank_rd_data, rst_n):
        """Compute the next state from this cycle's inputs; apply at the edge."""
        n3 = n4 = None
        # S2 -> S2/S3 [DP-8], [DP-9]
        if iss["valid"]:
            d = iss["instr"]
            vals = {}
            for op, u in s2_ports(d).items():
                if u[0] == "bank":
                    vals[op] = bank_rd_data
                else:
                    f, p, _ = u
                    v = rd[f][p]
                    vals[op] = v if f.startswith("grf") else (v if op == "c" else bcast(v))
            a = vals.get("a")
            if d["op"] == "MOV" and d["relu"]:
                a = vec(relu, a)
            n3 = dict(instr=d, a=a, b=vals.get("b"), c=vals.get("c"),
                      row=iss["row"], col=iss["col"])
        # S3 -> S3/S4 [DP-10], [DP-12]
        if self.s3_valid:
            s, op = self.s3, self.s3["instr"]["op"]
            if op in ("MUL", "MAD", "MAC"):
                x = vec(fmul, s["a"], s["b"])
            elif s["a"] is not None and self.units:
                x = vec(fmul, s["a"], bcast(0x3C00))
            else:
                x = s["a"]
            y = s["b"] if op == "ADD" else bcast(s["c"]) if op == "MAD" else None
            if op == "ADD" and self.units:
                y = vec(fmul, y, bcast(0x3C00))
            n4 = dict(instr=s["instr"], x=x, y=y, row=s["row"], col=s["col"])
        # S4 -> S4/S5 [DP-11], [DP-12], [DP-13], [DP-14]
        g = self.rng.randrange
        n5 = dict(power_up_s5(), wr_idx=g(8), wr_data=tuple(g(0x10000) for _ in range(LANES)),
                  bank_wr_sel=g(2), bank_wr_row=g(4), bank_wr_col=g(32))   # don't-care
        if self.s4_valid:
            s, d = self.s4, self.s4["instr"]
            op = d["op"]
            if op in ("ADD", "MAD"):
                r = vec(fadd, s["x"], s["y"])
            elif op == "MAC":
                acc = rd["grf_b"][1] if self.shared_port else rd["grf_b"][2]
                r = vec(fadd, acc, s["x"])
            elif s["x"] is not None and self.units:
                r = vec(fadd, s["x"], bcast(0x0000))
            else:
                r = s["x"]
            if op in WRITERS:
                if d["dst"] in CODE_FILE:
                    n5[CODE_FILE[d["dst"]] + "_wr_en"] = 1
                    n5["wr_idx"] = d["dst_idx"]
                elif d["dst"] in BANKS:
                    n5["bank_wr_en"] = 1
                    n5["bank_wr_sel"] = 0 if d["dst"] == "EVEN_BANK" else 1
                    n5["bank_wr_row"], n5["bank_wr_col"] = s["row"], s["col"]
                n5["wr_data"] = r
        return (n3, n4, n5)

    def edge(self, nxt, iss_valid, rst_n):
        n3, n4, n5 = nxt
        if not rst_n:                           # [DP-5]: reset wins
            self.s3_valid = self.s4_valid = self.s5_valid = 0
            self.s5.update(power_up_s5())
            return
        self.s5_valid, self.s4_valid, self.s3_valid = self.s4_valid, self.s3_valid, iss_valid
        self.s3, self.s4 = n3, n4
        self.s5 = n5


# ------------------------------------------------------- pcu_ctrl stand-in ---------
class Ctrl:
    """S1 without JUMPs: [CTRL-5], [CTRL-9] (NOP, EXIT, OP), [CTRL-11], [CTRL-12]."""

    def __init__(self, words):
        self.words, self.pc, self.nop = words, 0, 0
        self.iss = dict(valid=0, instr=DEC_NOP, row=0, col=0)

    def s1(self, trig, rst_n, row, col):
        slot = bool(trig and rst_n)
        w = self.words[self.pc] if self.pc < len(self.words) else 0x20000000
        d = dec(w)
        if self.nop:
            kind = "NOPSLOT"
        elif not legal(w):
            kind = "ILL"
        else:
            kind = {"NOP": "NOP", "EXIT": "EXIT"}.get(d["op"], "OP")
        bank = None
        if slot and kind == "OP":
            srcs = [d["src0"]] + ([d["src1"]] if d["src1"] else [])
            b = [s for s in srcs if s in BANKS]
            if b:
                bank = (b[0], row, col)
        self.nxt = (slot, kind, d, w, row, col)
        return bank, (self.pc, kind, d)

    def edge(self, rst_n):
        slot, kind, d, w, row, col = self.nxt
        if not rst_n:
            self.pc, self.nop = 0, 0
            self.iss = dict(valid=0, instr=DEC_NOP, row=0, col=0)
            return
        if not slot:
            self.iss = dict(valid=0, instr=None, row=None, col=None)   # don't-care
            return
        self.iss = dict(valid=1, instr=d if kind == "OP" else DEC_NOP, row=row, col=col)
        if kind == "NOPSLOT":
            self.nop -= 1
            self.pc += self.nop == 0
        elif kind == "NOP":
            n = max(get(w, "control", "imm0"), 1)
            self.nop = n - 1
            self.pc += n == 1
        elif kind == "EXIT":
            self.pc = 0
        else:
            self.pc += 1


# ------------------------------------------------------------------ top -------------
def rand_lane(rng):
    return rng.choice([rng.randrange(0x10000), rng.randrange(0x10000), 0x0000, 0x8000,
                       0x7C00, 0xFC00, 0x7E00, 0x7C01, 0xFE01, 0x0001, 0x8001, 0x3C00,
                       0xBC00, 0x7BFF, 0x0400])


def run(words, triggers, regs, bank, rst=None, rows=None, rng=None, dp=None, log=None, cols=None):
    """Run a program. triggers[t-1], rst[t-1]: trig_valid and rst_n of cycle t;
    the trigger of cycle t has row rows(t) (default 0) and column t.
    regs: {file: list of entries}; bank: {(bank, row, col): 16 lanes}.
    Returns the final register files and bank, and a per-cycle trace."""
    rng = rng or random.Random(1)
    rows = rows or (lambda t: 0)
    cols = cols or (lambda t: t)
    rf = {f: Regfile(regs[f]) for f in FILES}
    bank = dict(bank)
    dp = dp or Datapath()
    ctrl = Ctrl(words)
    bank_q = tuple(rng.randrange(0x10000) for _ in range(LANES))   # don't-care
    trace = []
    n = len(triggers)
    for t in range(1, n + 6):
        trig = triggers[t - 1] if t <= n else 0
        rst_n = rst[t - 1] if rst and t <= len(rst) else 1
        row, col = rows(t), cols(t)
        out = dp.s5_outputs()
        for f in FILES:
            rf[f].drive(out[f + "_wr_en"], out[f + "_wr_idx"], out[f + "_wr_data"])
        iss = ctrl.iss
        req, s1 = ctrl.s1(trig, rst_n, row, col)
        idx, used = dp.rd_idx(iss, rng)
        rd, through = {}, {}
        for f in FILES:
            rd[f], through[f] = zip(*(rf[f].read(i) for i in idx[f])) if idx[f] else ((), ())
        nxt = dp.step(iss, rd, bank_q, rst_n)
        trace.append(dict(t=t, trig=trig, rst_n=rst_n, s1=s1 if trig else None, iss=dict(iss),
                          s3_valid=dp.s3_valid, s4_valid=dp.s4_valid, s5_valid=dp.s5_valid,
                          s3=dp.s3, s4=dp.s4, out=out, idx=idx, used=used, rd=rd,
                          through=through, busy=dp.busy(), req=req))
        # the clock edge: the bank applies a store first, then samples a read
        if out["bank_wr_en"]:
            key = ("EVEN_BANK" if out["bank_wr_sel"] == 0 else "ODD_BANK",
                   out["bank_wr_row"], out["bank_wr_col"])
            bank[key] = out["bank_wr_data"]
        if req:
            bank_q = bank.get(req, tuple(rng.randrange(0x10000) for _ in range(LANES)))
            bank[req] = bank_q
        else:
            bank_q = tuple(rng.randrange(0x10000) for _ in range(LANES))
        for f in FILES:
            rf[f].edge()
        dp.edge(nxt, iss["valid"] and rst_n, rst_n)
        ctrl.edge(rst_n)
    return {f: rf[f].mem for f in FILES}, bank, trace


def schedule(words, triggers, rows=None, cols=None):
    """Slot-level: the (row, col) of each instruction's trigger, in order."""
    rows = rows or (lambda t: 0)
    cols = cols or (lambda t: t)
    cyc = iter([t for t, v in enumerate(triggers, 1) if v])
    out = []
    for w in words:
        d = dec(w)
        if d["op"] == "EXIT":
            break
        if d["op"] == "NOP":
            for _ in range(max(get(w, "control", "imm0"), 1)):
                next(cyc)
            continue
        t = next(cyc)
        out.append((d, rows(t), cols(t)))
    return out


def in_order(words, triggers, regs, bank, rows=None, cols=None):
    """In-order ISA execution, one instruction at a time, bit level: what the
    program means ([TOP-ISA-11], [TOP-ISA-15] to [TOP-ISA-21], [TOP-ISA-29],
    [TOP-ISA-30], [TOP-FP-3], [TOP-FP-8], [TOP-FP-9]). Written without ports
    or stages."""
    R = {f: list(regs[f]) for f in FILES}
    B = dict(bank)
    for d, row, col in schedule(words, triggers, rows, cols):
        def val(code, idx):
            if code in BANKS:
                return B[(code, row, col)]
            v = R[CODE_FILE[code]][idx]
            return bcast(v) if code.startswith("SRF") else v
        op = d["op"]
        a = val(d["src0"], d["src0_idx"])
        if op == "MOV":
            r = vec(relu, a) if d["relu"] else a
        elif op == "FILL":
            r = a
        else:
            b = val(d["src1"], d["src1_idx"])
            p = vec(fmul, a, b)
            if op == "ADD":
                r = vec(fadd, a, b)
            elif op == "MUL":
                r = p
            elif op == "MAD":
                r = vec(fadd, p, bcast(R["srf_a"][d["src1_idx"]]))
            else:
                r = vec(fadd, R["grf_b"][d["dst_idx"]], p)
        if d["dst"] in BANKS:
            B[(d["dst"], row, col)] = r
        elif d["dst"].startswith("SRF"):
            R[CODE_FILE[d["dst"]]][d["dst_idx"]] = r[0]
        else:
            R[CODE_FILE[d["dst"]]][d["dst_idx"]] = r
    return R, B


def rand_regs(rng):
    return {f: [tuple(rand_lane(rng) for _ in range(LANES)) if f.startswith("grf")
                else rand_lane(rng) for _ in range(8)] for f in FILES}


def table(head, rows):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def in_doc(name, text):
    print(text)
    check(text in SPEC, f"{name}: the table above appears in the doc word for word")
    print()


def h(v):
    return f"0x{v:04X}"


ODD, EVEN = "ODD_BANK", "EVEN_BANK"
f = lambda x: f2b(x)

# ======================================================================= 1. cases ====
print("1. Cases A to F\n")

# ---- Case A: the GEMV pattern at the datapath's ports ([TOP-HIER-5], [DP-5], [DP-11],
# [DP-13], [DP-14], [DP-15]); the program and data of module_trace.py.
GEMV = ["MOV GRF_B[0], ODD_BANK", "MAC GRF_B[0], EVEN_BANK, SRF_M[0]",
        "MAC GRF_B[0], ODD_BANK, SRF_M[1]", "NOP 2", "MOV ODD_BANK, GRF_B[0]", "EXIT"]
mt = load("module_trace.py")
def gemv_state():
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    regs["grf_b"] = [bcast(f(-1.0))] + [bcast(0)] * 7            # from an earlier run
    regs["srf_m"] = [f(mt["SRF_M"][0]), f(mt["SRF_M"][1])] + [0] * 6
    bank = {(k[0], 0, k[1]): tuple(f(x) for x in v) for k, v in mt["bank_init"]().items()}
    return regs, bank
regs, bank = gemv_state()
words = [assemble(x) for x in GEMV]
fr, fb, tr = run(words, [1] * 7, regs, bank)
NAMES = {0: "MOV GRF_B[0], ODD_BANK", 1: "MAC GRF_B[0], EVEN_BANK, SRF_M[0]",
         2: "MAC GRF_B[0], ODD_BANK, SRF_M[1]", 4: "MOV ODD_BANK, GRF_B[0]"}
def iss_lbl(c):
    i = c["iss"]
    if not i["valid"]:
        return "0"
    if i["instr"] is DEC_NOP:
        return "1, `DEC_NOP`"
    return "1, " + decode_text(i["instr"]["word"])
rows = []
for c in tr[:12]:
    o = c["out"]
    acc = (f"[{c['idx']['grf_b'][2]}] = {lbl(c['rd']['grf_b'][2][0])}"
           + (" (write-through)" if c["through"]["grf_b"][2] else "")) if ("grf_b", 2) in c["used"] else "–"
    s2 = []
    for (fl, p), op in sorted(c["used"].items()):
        if p == 2 and fl == "grf_b":
            continue
        s2.append(f"`{fl}` {p} [{c['idx'][fl][p]}] = {lbl(c['rd'][fl][p][0] if fl.startswith('grf') else c['rd'][fl][p])}"
                  + (" (write-through)" if c["through"][fl][p] else ""))
    if c["iss"]["valid"] and any(u == ("bank",) for u in s2_ports(c["iss"]["instr"]).values()):
        s2.insert(0, "`bank_rd_data` = …")
    wr = (f"[{o['grf_b_wr_idx']}] ← {lbl(o['grf_b_wr_data'][0])}" if o["grf_b_wr_en"] else "0")
    bw = (f"1, {'ODD' if o['bank_wr_sel'] else 'EVEN'}, row {o['bank_wr_row']}, col {o['bank_wr_col']}, "
          f"{lbl(o['bank_wr_data'][0])}" if o["bank_wr_en"] else "0")
    rows.append((c["t"], iss_lbl(c), "; ".join(s2) or "–",
                 f"{c['s3_valid']} {c['s4_valid']} {c['s5_valid']}", acc, wr, bw, c["busy"]))
# bank_rd_data values (lane 0) are filled in from the bank, for the table
for r_, c in zip(range(len(rows)), tr):
    if "`bank_rd_data` = …" in rows[r_][2]:
        src = c["iss"]["instr"]["src0"]
        v = bank[(src, 0, c["t"] - 1)][0]
        rows[r_] = rows[r_][:2] + (rows[r_][2].replace("…", lbl(v)),) + rows[r_][3:]
in_doc("Case A", table(["Cycle", "`iss_valid`, `iss_instr`", "S2 reads (lane 0)",
                        "`s3_valid` `s4_valid` `s5_valid`", "`grf_b` port 2 (S4, lane 0)",
                        "`grf_b_wr_*` (lane 0)", "`bank_wr_*` (lane 0)", "`busy`"], rows))
want = fb[(ODD, 0, 6)]
ref_r, ref_b = in_order(words, [1] * 7, regs, bank)
check(ref_b[(ODD, 0, 6)] == want and fr["grf_b"][0] == ref_r["grf_b"][0],
      "Case A: bank write ODD col 6 and GRF_B[0] equal in-order execution, all 16 lanes")
stores = [(c["t"], c["out"]["bank_wr_col"], c["out"]["bank_wr_data"]) for c in tr if c["out"]["bank_wr_en"]]
mw, _ = mt["run"](True, False)
check(len(stores) == 1 and len(mw) == 1 and stores[0][0] == mw[0][0] and stores[0][1] == mw[0][2]
      and [b2f(x) for x in stores[0][2]] == list(mw[0][3]),
      f"Case A == module_trace.py (a): one store, cycle {mw[0][0]}, ODD col {mw[0][2]}, 16 lanes "
      f"{[b2f(x) for x in stores[0][2]][:4]}...")
GEMV_TRACE = tr

# ---- Case B: grf_b's three read ports in one cycle ([DP-7], [DP-11], [TOP-ARCH-10]) --
B_PROG = ["MOV GRF_B[1], SRF_M[1]", "MAC GRF_B[4], GRF_A[1], SRF_M[0]", "NOP 1",
          "ADD GRF_A[0], GRF_B[1], GRF_B[2]", "EXIT"]
def b_state():
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    regs["grf_b"] = [bcast(0), bcast(f(0.25)), bcast(f(0.5)), bcast(0), bcast(f(1.0)),
                     bcast(0), bcast(f(-3.0)), bcast(0)]
    regs["grf_a"] = [bcast(0), bcast(f(2.0))] + [bcast(0)] * 6
    regs["srf_m"] = [f(0.5), f(4.0)] + [0] * 6
    return regs
words = [assemble(x) for x in B_PROG]
res = {}
for name, dpo in (("chosen", Datapath()), ("shared", Datapath(shared_port=True))):
    fr, _, tr = run(words, [1] * 5, b_state(), {}, dp=dpo)
    res[name] = (fr, tr)
ref_r, _ = in_order(words, [1] * 5, b_state(), {})
c5 = res["chosen"][1][4]
c5s = res["shared"][1][4]
def port_cells(c):
    return [f"[{c['idx']['grf_b'][p]}] = {lbl(c['rd']['grf_b'][p][0])}"
            + (" (write-through)" if c["through"]["grf_b"][p] else "") for p in range(3)]
o = c5["out"]
rows = [("chosen: three ports", *port_cells(c5), f"[{o['grf_b_wr_idx']}] ← {lbl(o['grf_b_wr_data'][0])}",
         lbl(res["chosen"][0]["grf_b"][4][0]), lbl(res["chosen"][0]["grf_a"][0][0])),
        ("ANEMOS's sharing: port 1 at 2 OR 4, accumulator through port 1",
         *port_cells(c5s)[:2], "not used", f"[{o['grf_b_wr_idx']}] ← {lbl(o['grf_b_wr_data'][0])}",
         lbl(res["shared"][0]["grf_b"][4][0]), lbl(res["shared"][0]["grf_a"][0][0])),
        ("in-order execution", "–", "–", "–", "–", lbl(ref_r["grf_b"][4][0]), lbl(ref_r["grf_a"][0][0]))]
in_doc("Case B", table(["Cycle 5", "`grf_b` port 0 (ADD src0)", "`grf_b` port 1 (ADD src1)",
                        "`grf_b` port 2 (MAC accumulator)", "`grf_b_wr_*` (MOV, S5)",
                        "GRF_B[4] after", "GRF_A[0] after"], rows))
check(res["chosen"][0]["grf_b"] == ref_r["grf_b"] and res["chosen"][0]["grf_a"] == ref_r["grf_a"],
      "Case B: chosen == in-order, all lanes")
check(res["shared"][0]["grf_a"][0] != ref_r["grf_a"][0] and res["shared"][0]["grf_b"][4] != ref_r["grf_b"][4],
      "Case B: ANEMOS's port sharing differs from in-order on both results")
check(c5["s3_valid"] == 1 and c5["s4_valid"] == 1 and c5["s5_valid"] == 1 and c5["iss"]["valid"] == 1,
      "Case B: cycle 5 has the ADD in S2, the NOP slot in S3, the MAC in S4, the MOV in S5")

# ---- Case C: MOV lanes, broadcast and ReLU on every pair ([DP-8], [DP-9], [DP-13]) ---
GA1 = [0xBC00, 0x4000, 0x8000, 0xFC01, 0x7C01, 0xFE00, 0x7E00, 0x8001] + [0x3C00 + l for l in range(8)]
def c_state():
    regs = {f_: [bcast(0x1111)] * 8 if f_.startswith("grf") else [0x1111] * 8 for f_ in FILES}
    regs["grf_a"] = [bcast(0x1111), tuple(GA1)] + [bcast(0x1111)] * 6
    regs["srf_m"] = [0xC000] + [0x1111] * 7
    return regs
C_CASES = [("MOV SRF_M[2], GRF_A[1]", "srf_m", 2),
           ("MOV(RELU) SRF_M[2], GRF_A[1]", "srf_m", 2),
           ("MOV GRF_B[0], SRF_M[0]", "grf_b", 0),
           ("MOV(RELU) GRF_B[0], SRF_M[0]", "grf_b", 0),
           ("MOV SRF_A[3], SRF_M[0]", "srf_a", 3),
           ("MOV(RELU) SRF_A[3], SRF_M[0]", "srf_a", 3),
           ("MOV GRF_B[2], GRF_A[1]", "grf_b", 2),
           ("MOV(RELU) GRF_B[2], GRF_A[1]", "grf_b", 2),
           ("MOV(RELU) EVEN_BANK, GRF_A[1]", "bank", None),
           ("FILL EVEN_BANK, GRF_A[1]", "bank", None),
           ("FILL EVEN_BANK, GRF_A[1] with R = 1", "bank", None)]
rows = []
for text_, where, idx in C_CASES:
    w = assemble(text_.replace(" with R = 1", ""))
    if "with R = 1" in text_:
        w |= 1 << 12                            # FILL ignores R [TOP-ISA-16]
    check(legal(w), f"Case C: {text_} is legal")
    fr, fb, tr = run([w, assemble("EXIT")], [1, 1], c_state(), {})
    ref_r, ref_b = in_order([w, assemble("EXIT")], [1, 1], c_state(), {})
    if where == "bank":
        got = fb[(EVEN, 0, 1)]
        ok = got == ref_b[(EVEN, 0, 1)]
    else:
        got = fr[where][idx]
        ok = got == ref_r[where][idx]
    check(ok, f"Case C: {text_} == in-order")
    if isinstance(got, tuple):
        shown = " ".join(h(x) for x in got[:8]) if len(set(got)) > 1 else f"{h(got[0])} in all 16 lanes"
    else:
        shown = h(got)
    dst = {"srf_m": f"SRF_M[{idx}]", "srf_a": f"SRF_A[{idx}]", "grf_b": f"GRF_B[{idx}]",
           "bank": "the EVEN_BANK column, lanes 0 to 7"}[where]
    if where.startswith("grf") and len(set(got)) > 1:
        dst += ", lanes 0 to 7"
    rows.append((f"`{text_}`", f"`0x{w:08X}`", dst, shown))
in_doc("Case C", table(["Instruction", "Word", "Written", "Value"], rows))
for wd in ("0x44000210", "0x44001210", "0x42801000", "0x48001010"):
    check(wd in GUIDE.read_text() and f"`{wd}`" in SPEC, f"Case C: word {wd} is in the guide's MOV table and here")

# ---- Case D: values carried bit for bit ([DP-12]) ------------------------------------
def d_state():
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    regs["grf_a"] = [bcast(0), (0xBC00, 0x7C01, 0x8000, 0x3C00) + (0x3C00,) * 12,
                     (0x0000, 0x3C00, 0x3C00, 0x8000) + (0x3C00,) * 12] + [bcast(0)] * 5
    return regs
D_CASES = [("MUL GRF_A[0], GRF_A[1], GRF_A[2]", "grf_a", 0, "a × b in S3, then carried through S4"),
           ("MOV GRF_B[0], GRF_A[1]", "grf_b", 0, "carried through S3 and S4"),
           ("ADD GRF_A[0], GRF_A[1], GRF_A[2]", "grf_a", 0, "carried through S3, then a + b in S4")]
rows = []
for text_, fl, idx, how in D_CASES:
    w = assemble(text_)
    out = {}
    for name, dpo in (("chosen", Datapath()), ("units", Datapath(units=True))):
        fr, _, _ = run([w, assemble("EXIT")], [1, 1], d_state(), {}, dp=dpo)
        out[name] = fr[fl][idx]
    ref_r, _ = in_order([w, assemble("EXIT")], [1, 1], d_state(), {})
    check(out["chosen"] == ref_r[fl][idx], f"Case D: {text_} == in-order (chosen)")
    a, b = d_state()["grf_a"][1], d_state()["grf_a"][2]
    for l in range(4):
        ins = h(a[l]) if text_.startswith("MOV") else f"{h(a[l])}, {h(b[l])}"
        rows.append((f"`{text_}`" if l == 0 else "", how if l == 0 else "", l, ins,
                     h(out["chosen"][l]), h(out["units"][l]),
                     "same" if out["chosen"][l] == out["units"][l] else "**differs**"))
in_doc("Case D", table(["Instruction", "Path", "Lane", "Inputs", "Chosen: carried as bits",
                        "Through the units: x × 1.0 in S3, x + (+0) in S4", ""], rows))
check(any("**differs**" in r for r in rows), "Case D: the two options differ on some lane")

# ---- Case E: reset while entries are in flight ([DP-5]) ------------------------------
E_PROG = ["MOV GRF_A[1], SRF_M[1]", "MOV GRF_A[2], SRF_M[1]", "MOV EVEN_BANK, GRF_A[3]", "EXIT"]
def e_state():
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    regs["grf_a"] = [bcast(0), bcast(f(0.5)), bcast(f(0.25)), bcast(f(1.5))] + [bcast(0)] * 4
    regs["srf_m"] = [0, f(2.0)] + [0] * 6
    return regs, {(EVEN, 0, 3): bcast(f(0.75))}
words = [assemble(x) for x in E_PROG]
# Option (b) needs rst_n inside s5_outputs; run it with a small wrapper.
def run_gated(words, triggers, regs, bank, rst):
    dpo = Datapath()
    cyc = {"t": 0}
    orig = dpo.s5_outputs
    def s5o():
        cyc["t"] += 1
        o = orig()
        r = rst[cyc["t"] - 1] if cyc["t"] <= len(rst) else 1
        for k in list(o):
            if k.endswith("_wr_en"):
                o[k] &= r
        return o
    dpo.s5_outputs = s5o
    return run(words, triggers, regs, bank, rst=rst, dp=dpo)
rst = [1, 1, 1, 1, 0, 1, 1]
regs, bank = e_state()
fr_c, fb_c, tr_c = run(words, [1, 1, 1, 1], regs, bank, rst=rst)
regs, bank = e_state()
fr_g, fb_g, tr_g = run_gated(words, [1, 1, 1, 1], regs, bank, rst)
rows = []
for c, g in zip(tr_c[:7], tr_g[:7]):
    o, og = c["out"], g["out"]
    def wrs(o):
        return "; ".join(f"`{fl}` [{o[fl + '_wr_idx']}] ← {lbl(o[fl + '_wr_data'][0] if fl.startswith('grf') else o[fl + '_wr_data'])}"
                         for fl in FILES if o[fl + "_wr_en"]) or "–"
    rows.append((c["t"], c["rst_n"], c["trig"], iss_lbl(c),
                 f"{c['s3_valid']} {c['s4_valid']} {c['s5_valid']}", wrs(o), c["busy"], wrs(og)))
in_doc("Case E", table(["Cycle", "`rst_n`", "`trig_valid`", "`iss_valid`, `iss_instr`",
                        "`s3_valid` `s4_valid` `s5_valid`", "S5 write ports (chosen)", "`busy`",
                        "S5 write ports, gated by `rst_n`"], rows))
regs, _ = e_state()
check(fr_c["grf_a"][1] == bcast(f(2.0)) and fr_c["grf_a"][2] == regs["grf_a"][2]
      and fb_c[(EVEN, 0, 3)] == bcast(f(0.75)),
      "Case E (chosen): the entry in S5 in the reset cycle writes GRF_A[1]; the MOV in S4 and the store in S3 are removed")
check(fr_g["grf_a"][1] == regs["grf_a"][1], "Case E (gated): GRF_A[1] keeps 0.5")
check([c["busy"] for c in tr_c[:7]] == [0, 0, 1, 1, 1, 0, 0], "Case E: busy (dp's term) 0 0 1 1 1 0 0")

# ---- Case F: which port reads what ([DP-7]) ------------------------------------------
F_CASES = ["MOV GRF_A[3], EVEN_BANK", "MOV SRF_A[1], GRF_B[6]", "ADD GRF_A[2], EVEN_BANK, SRF_A[0]",
           "ADD GRF_B[1], SRF_A[4], GRF_A[7]", "MUL GRF_B[3], GRF_A[1], SRF_M[4]",
           "MAD GRF_A[0], ODD_BANK, SRF_M[2], SRF_A[2]", "MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]",
           "MAC GRF_B[3], GRF_B[1], GRF_B[2]"]
COLS = [("grf_a", 0), ("grf_a", 1), ("grf_b", 0), ("grf_b", 1), ("srf_m", 0), ("srf_a", 0)]
rows = []
for text_ in F_CASES:
    w = assemble(text_)
    check(legal(w), f"Case F: {text_} is legal")
    d = dec(w)
    u = s2_ports(d)
    cells = []
    for fl, p in COLS:
        hit = [k for k, v in u.items() if v[:2] == (fl, p)]
        cells.append(f"{hit[0]}: [{u[hit[0]][2]}]" if hit else "")
    cells.append(", ".join(k for k, v in u.items() if v == ("bank",)))
    cells.append(f"acc: [{d['dst_idx']}]" if d["op"] == "MAC" else "")
    rows.append((f"`{text_}`", f"`0x{w:08X}`", *cells))
in_doc("Case F", table(["Instruction", "Word", "`grf_a` 0", "`grf_a` 1", "`grf_b` 0", "`grf_b` 1",
                        "`srf_m` 0", "`srf_a` 0", "`bank_rd_data`", "`grf_b` 2 (S4)"], rows))

# =============================================================== 2. Figure 1 =========
print("2. Figure 1 against case A, cell by cell")
wave = json.loads(WAVE.read_text())


def expand(sig):
    """The value of each cycle of a WaveDrom row, as text: 'x', '0', '1', a data label."""
    vals, data, cur = [], list(sig.get("data", [])), None
    for ch in sig["wave"]:
        if ch == ".":
            vals.append(cur)
            continue
        if ch in "=23456789":
            cur = data.pop(0)
        elif ch == "p":
            cur = "clk"
        else:
            cur = ch
        vals.append(cur)
    return vals


def model_cell(c, name):
    o, s4 = c["out"], c["s4"]
    if name == "iss_valid":
        return str(c["iss"]["valid"])
    if name == "iss_instr":
        i = c["iss"]
        if not i["valid"]:
            return "x"
        return "DEC_NOP" if i["instr"] is DEC_NOP else decode_text(i["instr"]["word"]).split()[0]
    if name in ("s3_valid", "s4_valid", "s5_valid", "busy"):
        return str(c[name])
    if name == "grf_b_rd_idx[2]":
        return str(c["idx"]["grf_b"][2]) if ("grf_b", 2) in c["used"] else "x"
    if name == "grf_b_rd_data[2]":                 # lane 0
        return lbl(c["rd"]["grf_b"][2][0]) if ("grf_b", 2) in c["used"] else "x"
    if name in ("grf_b_wr_en", "bank_wr_en"):
        return str(o[name])
    if name == "grf_b_wr_idx":
        return str(o[name]) if o["grf_b_wr_en"] else "x"
    if name == "grf_b_wr_data":                 # lane 0
        return lbl(o["grf_b_wr_data"][0]) if o["grf_b_wr_en"] else "x"
    if name == "bank_wr_col":
        return str(o[name]) if o["bank_wr_en"] else "x"
    if name == "bank_wr_data":                 # lane 0
        return lbl(o["bank_wr_data"][0]) if o["bank_wr_en"] else "x"
    if name == "trig_valid":
        return str(c["trig"])
    raise KeyError(name)


rows_ = [s for s in wave["signal"] if isinstance(s, dict) and s.get("name")]
for g in wave["signal"]:
    if isinstance(g, list):
        rows_ += [s for s in g[1:] if isinstance(s, dict) and s.get("name")]
start = wave["head"]["tick"]
cells = bad = 0
for s in rows_:
    if s["name"] == "clk":
        continue
    for k, v in enumerate(expand(s)):
        c = GEMV_TRACE[start + k - 1]
        m = model_cell(c, s["name"].replace(" (internal)", ""))
        cells += 1
        if m != v:
            bad += 1
            print(f"     {s['name']} cycle {start + k}: diagram {v}, model {m}")
check(bad == 0, f"Figure 1: {cells} cells equal the model")
lens = {len(s["wave"]) for s in rows_}
check(len(lens) == 1, f"Figure 1: every wave string has the same length {lens}")
print()

# ============================================ 3./4. every legal combination =========
print("3. Every legal operand combination of the yaml")
rp = load("regfile_ports.py")
s2max, s4max, _ = rp["ports"]()
rng = random.Random(32)
need = {fl: 0 for fl in FILES}
runs = ok = 0
n_combos = 0
for mn in WRITERS:
    for c in sorted(combos(mn)):
        c = dict(c)
        for r_ in ((0, 1) if mn == "MOV" else (0,)):
            n_combos += 1
            for rep in range(20):
                # build the word from the combination, random indices, random ignored fields
                fmt = INS[mn]["format"]
                w = isa["put"](0, fmt, "opcode", INS[mn]["opcode"])
                for k, v in c.items():
                    w = isa["put"](w, fmt, k, OPS[v]["code"])
                for k in ("dst", "src0", "src1"):
                    if k in c or (k == "src1" and fmt == "alu"):
                        w = isa["put"](w, fmt, k + "_idx", rng.randrange(8))
                if fmt == "alu" and mn != "MAD":
                    w = isa["put"](w, fmt, "src2", rng.randrange(8))       # [TOP-ISA-10]
                if mn == "MOV" and r_:
                    w = isa["put"](w, fmt, "relu", 1)
                if mn == "FILL" and rng.random() < 0.5:
                    w = isa["put"](w, fmt, "relu", 1)                     # [TOP-ISA-16]
                assert legal(w), hex(w)
                d = dec(w)
                if rep == 0:
                    u = s2_ports(d)
                    per = {fl: {v[1] for v in u.values() if v[0] == fl} for fl in FILES}
                    pairs = [v[:2] for v in u.values() if v[0] != "bank"]
                    check(len(pairs) == len(set(pairs)), f"{decode_text(w)}: no port used twice") if len(pairs) != len(set(pairs)) else None
                    for fl in FILES:
                        need[fl] = max(need[fl], len(per[fl]) + (1 if fl == "grf_b" and mn == "MAC" else 0))
                regs = rand_regs(rng)
                bank = {(b, 0, 1): tuple(rand_lane(rng) for _ in range(LANES)) for b in BANKS}
                prog = [w, assemble("EXIT")]
                fr, fb, _ = run(prog, [1, 1], regs, bank, rng=rng)
                rr, rb = in_order(prog, [1, 1], regs, bank)
                runs += 1
                ok += fr == rr and fb == rb
check(n_combos == 164, f"{n_combos} combinations (MOV 20 pairs x R, FILL 4, ADD 40, MUL 32, MAD 32, MAC 16)")
check(ok == runs, f"{runs} runs, 20 per combination, equal to in-order execution, all lanes: {ok}")
want_ports = {CODE_FILE[k]: s2max[k] + s4max[k] for k in CODE_FILE}
check(need == want_ports == N_RD, f"ports needed by [DP-7] {need} == regfile_ports.py {want_ports} == N_RD {N_RD}")
print()

# ===================================================== 5. ReLU and bit copy =========
print("4. ReLU and the bit copy on all 65536 lane patterns")
fp = load("fp_relu_nan.py")
relu_ref = fp["relu_bankside"]
mism = {"MOV(RELU)": 0, "MOV": 0, "FILL": 0}
for base in range(0, 0x10000, LANES):
    lanes = tuple(range(base, base + LANES))
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    regs["grf_a"] = [bcast(0), lanes] + [bcast(0)] * 6
    for text_, fn in (("MOV(RELU) GRF_B[0], GRF_A[1]", relu_ref), ("MOV GRF_B[0], GRF_A[1]", lambda x: x)):
        fr, _, _ = run([assemble(text_), assemble("EXIT")], [1, 1], regs, {})
        mism[text_.split()[0]] += sum(fr["grf_b"][0][l] != fn(lanes[l]) for l in range(LANES))
    fr, fb, _ = run([assemble("FILL EVEN_BANK, GRF_A[1]") | (1 << 12), assemble("EXIT")], [1, 1], regs, {})
    mism["FILL"] += sum(fb[(EVEN, 0, 1)][l] != lanes[l] for l in range(LANES))
check(all(v == 0 for v in mism.values()),
      f"MOV(RELU) == fp_relu_nan.relu_bankside, MOV R=0 and FILL (R bit set) copy bits: mismatches {mism}")
print()

# ===================================================== 6. random programs ===========
print("5. Random programs")
ALL = [(mn, dict(c)) for mn in WRITERS for c in sorted(combos(mn))]   # sorted: combos() is a set


def random_word(rng, nidx):
    mn, c = rng.choice(ALL)
    fmt = INS[mn]["format"]
    w = isa["put"](0, fmt, "opcode", INS[mn]["opcode"])
    for k, v in c.items():
        w = isa["put"](w, fmt, k, OPS[v]["code"])
    for k in ("dst", "src0") + (("src1",) if fmt == "alu" else ()):
        w = isa["put"](w, fmt, k + "_idx", rng.randrange(nidx))
    if mn == "MAC":
        w = isa["put"](w, fmt, "src2", 1)
    if mn == "MOV" and rng.random() < 0.3:
        w = isa["put"](w, fmt, "relu", 1)
    return w


BANK_ALL = [(mn, c) for mn, c in ALL if any(v in BANKS for v in c.values())]


def random_bank_word(rng):
    """A legal word with a bank operand (a load, a store or a bank source)."""
    while True:
        w = random_word(rng, 3)
        d = dec(w)
        if d["dst"] in BANKS or d["src0"] in BANKS or d["src1"] in BANKS:
            return w


def reads_writes(d, row, col):
    """Entries an instruction reads in S2 (sources, the MAD addend) and the one it writes."""
    rd = []
    for op, u in s2_ports(d).items():
        if u == ("bank",):
            rd.append((d["src0"] if op == "a" else d["src1"], row, col))
        else:
            rd.append((u[0], u[2]))
    if d["dst"] in BANKS:
        wr = (d["dst"], row, col)
    else:
        wr = (CODE_FILE[d["dst"]], d["dst_idx"])
    return rd, wr


def keeps_rules(words, triggers, rows, cols):
    """[TOP-HAZ-3] (3 slots, GRF/SRF sources) and [TOP-HAZ-6] (4 slots, bank columns)."""
    cyc = [t for t, v in enumerate(triggers, 1) if v]
    slot, items = 0, []
    for w in words:
        d = dec(w)
        if d["op"] == "EXIT":
            break
        n = max(get(w, "control", "imm0"), 1) if d["op"] == "NOP" else 1
        if d["op"] != "NOP":
            t = cyc[slot]
            items.append((slot, *reads_writes(d, rows(t), cols(t))))
        slot += n
    for j, (sj, rj, _) in enumerate(items):
        for si, _, wi in items[:j]:
            if wi in rj and sj - si < (4 if wi[0] in BANKS else 3):
                return False
    return True


rng = random.Random(320)
rows = lambda t: (t // 6) % 2
cols = lambda t: t % 2                       # two columns, so stores and loads meet
legal_n = legal_ok = bank_meet = 0
writes_per_cycle_ok = True
for _ in range(3000):
    # The triggers first; then the program, built slot by slot: before each
    # instruction, NOP 1 slots are added until it keeps [TOP-HAZ-3] and
    # [TOP-HAZ-6] against every instruction before it, at its own address.
    trig = [rng.choice([1, 1, 1, 0]) for _ in range(80)]
    trig[0] = 1
    cyc = [t for t, v in enumerate(trig, 1) if v]
    words, items, slot = [], [], 0
    for _ in range(rng.randint(2, 10)):
        if rng.random() < 0.15:
            n = max(rng.randint(0, 3), 1)
            words.append(assemble(f"NOP {n}"))
            slot += n
            continue
        w = random_word(rng, 3) if rng.random() < 0.5 else random_bank_word(rng)
        d = dec(w)
        while True:
            t = cyc[slot]
            rd, wr = reads_writes(d, rows(t), cols(t))
            if not any(wi in rd and slot - si < (4 if wi[0] in BANKS else 3) for si, _, wi in items):
                break
            words.append(assemble("NOP 1"))
            slot += 1
        items.append((slot, rd, wr))
        words.append(w)
        slot += 1
    words.append(assemble("EXIT"))
    trig = trig[: cyc[slot]]                 # EXIT's slot is the last trigger
    regs = rand_regs(rng)
    bank = {(b, r, c_): tuple(rand_lane(rng) for _ in range(LANES))
            for b in BANKS for r in (0, 1) for c_ in range(2)}
    fr, fb, tr = run(words, trig, regs, bank, rows=rows, rng=rng, cols=cols)
    for c in tr:
        o = c["out"]
        if sum(o[k] for k in o if k.endswith("_wr_en")) > 1:
            writes_per_cycle_ok = False
    assert keeps_rules(words, trig, rows, cols)
    legal_n += 1
    rr, rb = in_order(words, trig, regs, bank, rows=rows, cols=cols)
    legal_ok += fr == rr and all(fb[k] == rb[k] for k in rb)
    bank_meet += any(wi[0] in BANKS and wi in rj for i, (_, _, wi) in enumerate(items) for _, rj, _ in items[i + 1:])
check(legal_ok == legal_n, f"(a) {legal_n} random legal programs keeping [TOP-HAZ-3] and [TOP-HAZ-6] "
      f"({bank_meet} with a bank store and a later read of its column), bubbles, rows 0/1, columns 0/1: "
      f"registers and bank columns == in-order, all lanes: {legal_ok}")
check(writes_per_cycle_ok, "(a) at most one write enable per cycle ([TOP-PIPE-1])")

# (b) against hazard_trace.py's pipeline model, lane 0, legal words only, any distance.
ht = load("hazard_trace.py")
rng = random.Random(8)
n_b = same_b = broken_b = 0
for _ in range(4000):
    prog = ht["random_program"](rng, rng.randint(2, 8))
    init = {e: rng.choice(ht["VALUES"]) for e in ht["ENTRIES"]}
    trig = [rng.choice([1, 1, 1, 0]) for _ in range(60)]
    trig[0] = 1
    need_ = sum(max(i[1], 1) if i[0] == "NOP" else 1 for i in prog)
    if sum(trig) < need_:
        trig += [1] * need_
    texts = [f"NOP {i[1]}" if i[0] == "NOP" else f"{i[0]} {i[1]}, " + ", ".join(i[2]) for i in prog]
    words = [assemble(x) for x in texts]
    if not all(legal(w) for w in words):
        continue
    # cut the triggers after the program's last slot (the pipeline model issues nothing more)
    k, cnt = 0, 0
    while cnt < need_:
        cnt += trig[k]
        k += 1
    trig = trig[:k]
    regs = {f_: [bcast(0)] * 8 if f_.startswith("grf") else [0] * 8 for f_ in FILES}
    for e, v in init.items():
        fl, i = CODE_FILE[e.split("[")[0]], int(e[-2])
        regs[fl][i] = bcast(f(v)) if fl.startswith("grf") else f(v)
    fr, _, _ = run(words, trig, regs, {})
    hr = ht["pipeline"](prog, init, trig, True)[0]
    n_b += 1
    broken_b += bool(ht["haz3_ok"](prog))
    same_b += all(b2f(fr[CODE_FILE[e.split("[")[0]]][int(e[-2])][0] if e.startswith("GRF")
                      else fr[CODE_FILE[e.split("[")[0]]][int(e[-2])]) == hr[e] for e in ht["ENTRIES"])
check(same_b == n_b, f"(b) {n_b} legal hazard_trace.py programs ({broken_b} of them break [TOP-HAZ-3]), "
      f"random bubbles: every register, lane 0, == hazard_trace.pipeline(): {same_b}")

# (c) resets: busy and the valid bits against [TOP-IF-7] term 1 (S3 to S5).
rng = random.Random(33)
cyc_n = cyc_ok = 0
for _ in range(500):
    words = [random_word(rng, 8) if rng.random() < 0.7 else assemble(f"NOP {rng.randint(0, 3)}")
             for _ in range(rng.randint(2, 10))] + [assemble("EXIT")]
    trig = [rng.choice([1, 1, 0]) for _ in range(30)]
    rst = [0 if rng.random() < 0.08 else 1 for _ in range(36)]
    _, _, tr = run(words, trig, rand_regs(rng), {}, rst=rst, rng=rng)
    for c in tr:
        t = c["t"]
        def entry_in(stage_lag):
            s = t - stage_lag                    # issue cycle of the entry in that stage
            if s < 1 or s > len(trig) or not trig[s - 1]:
                return 0
            return int(all(rst[u - 1] for u in range(s, t)))
        want = [entry_in(2), entry_in(3), entry_in(4)]
        got = [c["s3_valid"], c["s4_valid"], c["s5_valid"]]
        cyc_n += 1
        cyc_ok += got == want and c["busy"] == int(any(want))
check(cyc_ok == cyc_n, f"(c) {cyc_n} cycles with random triggers and resets: s3/s4/s5_valid and busy == "
      f"[TOP-IF-7] term 1 for S3 to S5: {cyc_ok}")

print()
for phrase in (f"checks all {cells} cells", f"execution: {runs} runs", f"come up often. {bank_meet} of them",
               f"the legal ones: {n_b} programs, {broken_b} of them", f"in all {cyc_n}"):
    check(phrase in SPEC, f"the doc says: {phrase!r}")
if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all checks pass")
