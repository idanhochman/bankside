#!/usr/bin/env python3
"""Worked cases for pcu_ctrl (src/pcu_ctrl/doc/README.md), cycle by cycle.

A cycle-level model of pcu_ctrl as [CTRL-4] to [CTRL-16] state it: the
state registers, the two CRF read ports and the zero-slot JUMP fetch, the
slot kinds and their next state, err_illegal, the bank read request, the
issue bundle and the busy term. Around it, the parts of top the cases need:
the crf instance (32 x 32, combinational write-through reads, [RF-9]), the
configuration write gate of [TOP-IF-8] for the CRF, and pcu_datapath's S3
to S5 valid bits ([TOP-HIER-8]), so that top's busy can be compared.

pcu_decode doesn't have its doc yet (#31). Its role here is played by the
top spec's own assembler and legality check (src/top/doc/examples/
check_isa.py, which reads bankside_isa.yaml): `illegal` is [TOP-ISA-2]
without the JUMP range check, and the bank read is the bank source of a
legal word.

What it prints and checks:
  1. Cases A to F of the doc, each a table that must appear in the doc word
     for word: the loop fetch (A), the held chained JUMP (B), bubbles, EXIT
     and a CRF write (C), triggers in reset cycles (D), the JUMP range check
     and err_illegal timing (E), and the early-resolution option (F).
  2. Figure 1 (img/ctrl_jump_fetch.wave.json) against the model of case A,
     cell by cell.
  3. The JUMP range check against check_isa.py's legal(word, pc) for every
     PC and IMM0 ([TOP-ISA-26]).
  4. 4000 random programs with random triggers, bubbles and resets: every
     slot against the top spec's slot-level model (loop_trace.py), every
     cycle's busy against the top spec's busy model (busy_trace.py), and the
     CRF reads each slot needs.
  5. ANEMOS's run of the same loop (anemos_ctrl.out, case A): commands per
     JUMP fetch.

Run from the repo root:
    .venv/bin/python src/pcu_ctrl/doc/examples/ctrl_trace.py
Exits non-zero if a check fails or a table differs from the doc.
"""
import contextlib
import io
import json
import random
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "README.md"
WAVE = HERE.parent / "img" / "ctrl_jump_fetch.wave.json"
TOPX = HERE.parents[2] / "top" / "doc" / "examples"
SPEC = DOC.read_text()
failures = []


def load(name):
    """Run one of the top spec's example scripts quietly; return its globals."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            return runpy.run_path(str(TOPX / name))
    except SystemExit as e:
        print(out.getvalue())
        sys.exit(f"FAIL {name} exited with {e.code}")


isa = load("check_isa.py")            # parses bankside_isa.yaml and checks it
assemble, legal, get, decode = isa["assemble"], isa["legal"], isa["get"], isa["decode"]
INS, CODE2OP, BANKS = isa["INS"], isa["CODE2OP"], isa["BANKS"]
OPC = {v["opcode"]: k for k, v in INS.items()}
NOP_OP, JUMP_OP, EXIT_OP = (INS[k]["opcode"] for k in ("NOP", "JUMP", "EXIT"))
ILL_WORD = 0x30000000                  # opcode 3: reserved [TOP-ISA-2]
CRF_N = 32


def opcode(w):
    return get(w, "control", "opcode")


def imm0(w):
    return get(w, "control", "imm0")


def imm1(w):
    return get(w, "control", "imm1")


def dec(w):
    """Stand-in for pcu_decode: (illegal, bank read or None, text)."""
    op = opcode(w)
    if op not in OPC:
        return True, None, "reserved opcode"
    mn = OPC[op]
    fmt = INS[mn]["format"]
    if fmt == "control":
        return False, None, decode(w)          # a JUMP is legal as a word
    if not legal(w):
        return True, None, decode(w)
    srcs = ["src0"] + (["src1"] if fmt == "alu" else [])
    bank = next((CODE2OP[get(w, fmt, f)] for f in srcs if CODE2OP.get(get(w, fmt, f)) in BANKS), None)
    return False, bank, decode(w)


def wname(w):
    if w is None:
        return "–"
    ill, _, text = dec(w)
    return "illegal" if ill and opcode(w) not in OPC else text


class Ctrl:
    """pcu_ctrl, one call of cycle() per clock cycle."""

    def __init__(self, crf):
        self.crf = crf
        self.reset_state()

    def reset_state(self):                     # [CTRL-4] reset values
        self.pc, self.loop_active, self.loop_cnt, self.nop_cnt = 0, 0, 0, 0
        self.err, self.iss_valid, self.iss_instr, self.iss_row, self.iss_col = 0, 0, None, None, None

    def busy(self):                            # [CTRL-13]
        return int(self.iss_valid == 1 or self.nop_cnt != 0 or self.loop_active == 1)

    def comb(self, rst_n, trig_valid, row, col, wr=None):
        """The cycle's combinational outputs and the next state."""
        rd = lambda i: wr[1] if wr and wr[0] == i else self.crf[i]   # write-through
        o = dict(pc=self.pc, busy=self.busy(), err_illegal=self.err,
                 iss_valid=self.iss_valid, loop=(self.loop_active, self.loop_cnt))
        pc = self.pc
        w0 = rd(pc)                                       # [CTRL-6]
        j0 = opcode(w0) == JUMP_OP
        jbad = j0 and (imm0(w0) == 0 or imm0(w0) > pc)     # [TOP-ISA-26]
        a1, w1, loop_next = None, None, (self.loop_active, self.loop_cnt)
        if j0 and not jbad:                               # [CTRL-7]
            i0, i1 = imm0(w0), imm1(w0)
            act, cnt = self.loop_active, self.loop_cnt
            if not act and i1 >= 1:
                taken, loop_next = True, (1, i1 - 1)
            elif not act:
                taken = False                             # [TOP-ISA-13]
            elif cnt != 0:
                taken, loop_next = True, (1, cnt - 1)
            else:
                taken, loop_next = False, (0, cnt)
            a1 = (pc - i0) % CRF_N if taken else (pc + 1) % CRF_N
            w1 = rd(a1)
        o.update(idx0=pc, w0=w0, idx1=a1, w1=w1)
        slot = trig_valid == 1 and rst_n == 1               # [CTRL-5]
        nop_slot = self.nop_cnt != 0
        jres = j0 and not jbad and not nop_slot
        p, w = (a1, w1) if jres else (pc, w0)              # [CTRL-8]
        ill, bank, _ = dec(w)
        kind = None
        if slot:
            if nop_slot:
                kind = "NOPSLOT"
            elif jbad:
                kind = "ILLJ"
            elif jres and opcode(w1) == JUMP_OP:
                kind = "HOLD"
            elif ill:
                kind = "ILL"
            elif opcode(w) == NOP_OP:
                kind = "NOP"
            elif opcode(w) == EXIT_OP:
                kind = "EXIT"
            else:
                kind = "OP"
        o.update(kind=kind, p=p, w=w, jres=jres, a1=a1)
        # [CTRL-11] bank read request
        o["bank_rd_en"] = int(kind == "OP" and bank is not None)
        o["bank_rd_sel"] = (0 if bank == "EVEN_BANK" else 1) if o["bank_rd_en"] else None
        o["bank_rd_row"], o["bank_rd_col"] = (row, col) if o["bank_rd_en"] else (None, None)
        # [CTRL-9] next state
        n = dict(pc=self.pc, loop=(self.loop_active, self.loop_cnt), nop=self.nop_cnt, err=self.err)
        if kind == "NOPSLOT":
            n["nop"] = self.nop_cnt - 1
            if self.nop_cnt == 1:
                n["pc"] = (pc + 1) % CRF_N
        elif kind == "ILLJ":
            n["pc"], n["err"] = (pc + 1) % CRF_N, 1
        elif kind == "HOLD":
            n["pc"], n["loop"] = a1, loop_next
        elif kind is not None:
            if jres:
                n["loop"] = loop_next
            if kind == "ILL":
                n["pc"], n["err"] = (p + 1) % CRF_N, 1
            elif kind == "NOP":
                k = max(imm0(w), 1)                       # [TOP-ISA-12]
                n["nop"], n["pc"] = k - 1, (p + 1) % CRF_N if k == 1 else p
            elif kind == "EXIT":                          # [TOP-ISA-5], wins over the JUMP
                n["pc"], n["loop"] = 0, (0, 0)
            else:
                n["pc"] = (p + 1) % CRF_N
        n["iss_valid"] = int(kind is not None)            # [CTRL-12]
        n["iss_instr"] = (dec(w)[2] if kind == "OP" else "decoded NOP") if kind else None
        n["iss_row"], n["iss_col"] = (row, col) if kind else (None, None)
        if not rst_n:                                     # [CTRL-4], [CTRL-5]: reset wins
            n = dict(pc=0, loop=(0, 0), nop=0, err=0, iss_valid=0, iss_instr=None,
                     iss_row=None, iss_col=None)
        o["next"] = n
        return o

    def edge(self, o):
        n = o["next"]
        self.pc, (self.loop_active, self.loop_cnt), self.nop_cnt, self.err = n["pc"], n["loop"], n["nop"], n["err"]
        self.iss_valid, self.iss_instr, self.iss_row, self.iss_col = (
            n["iss_valid"], n["iss_instr"], n["iss_row"], n["iss_col"])


class Top:
    """The parts of top the cases need: crf with its configuration write
    ([TOP-HIER-6], [TOP-IF-8]), ctrl, and dp's S3 to S5 valid bits."""

    def __init__(self, prog):
        words = [assemble(x) if isinstance(x, str) else x for x in prog]
        self.crf = words + [assemble("NOP 1")] * (CRF_N - len(words))
        self.ctrl = Ctrl(self.crf)
        self.dp_valid = [0, 0, 0]                 # S2/S3, S3/S4, S4/S5

    def busy(self):                               # [TOP-HIER-8]
        return int(self.ctrl.busy() or any(self.dp_valid))

    def cycle(self, rst_n=1, trig=0, row=0, col=0, cfg=None):
        busy = self.busy()
        wr = None
        if cfg and busy == 0 and trig == 0:      # [TOP-IF-8]: a CRF write that counts
            wr = cfg
        o = self.ctrl.comb(rst_n, trig, row, col, wr)
        o["top_busy"], o["cfg"] = busy, ("takes effect" if wr else "ignored") if cfg else "–"
        dpv = [0, 0, 0] if not rst_n else [self.ctrl.iss_valid] + self.dp_valid[:2]
        self.ctrl.edge(o)
        self.dp_valid = dpv
        if wr:
            self.crf[wr[0]] = wr[1]
        o["after"] = dict(pc=self.ctrl.pc, loop=(self.ctrl.loop_active, self.ctrl.loop_cnt),
                          nop=self.ctrl.nop_cnt, err=self.ctrl.err)
        return o


# ---------------------------------------------------------------------------
# Table helpers
def issued(o):
    k = o["kind"]
    if k is None:
        return "–"
    if k == "NOPSLOT":
        return f"PC {o['pc']} NOP slot"
    if k == "ILLJ":
        return f"PC {o['pc']} JUMP, illegal ([TOP-ISA-26])"
    if k == "HOLD":
        return f"`NOP 1`: the JUMP at PC {o['a1']} waits ([TOP-ISA-27])"
    if k == "ILL":
        return f"PC {o['p']} illegal word"
    return f"PC {o['p']} {wname(o['w'])}"


def bank(o):
    if not o["bank_rd_en"]:
        return "0"
    return f"1, {'EVEN' if o['bank_rd_sel'] == 0 else 'ODD'}, col {o['bank_rd_col']}"


def loop_s(lp):
    return f"{lp[0]}, {lp[1]}" if lp[0] else "0, –"


def port(i, w):
    return "–" if i is None else f"{i}: {wname(w)}"


def check_in_doc(name, table):
    if table not in SPEC:
        failures.append(f"{name}: the doc's table differs from the model")


def show(name, title, prog, cycles, head, row):
    print(f"\n{name}: {title}\n")
    for i, x in enumerate(prog):
        w = assemble(x) if isinstance(x, str) else x
        print(f"    PC {i}  0x{w:08X}  {x if isinstance(x, str) else wname(w)}")
    lines = [head, "|" + "---|" * head.count(" | ") + "---|"]
    lines += [row(t, o) for t, o in cycles]
    table = "\n".join(lines)
    print()
    print(table)
    check_in_doc(name, table)
    return table


def run(prog, stim):
    """stim: list of dicts per cycle (rst_n, trig, col, cfg). Cycles from 1."""
    top = Top(prog)
    return top, [(t, top.cycle(**s)) for t, s in enumerate(stim, 1)]


T = lambda c: dict(trig=1, col=c)          # a trigger with column c
B = dict()                                 # a bubble

FETCH_HEAD = ("| Cycle | `trig_valid` | `pc` | port 0: `crf_rd_idx[0]`: word | port 1: `crf_rd_idx[1]`: word"
              " | The slot issues | `bank_rd_en`, sel, col | `loop_active`, `loop_cnt` after | `pc` after |")


def fetch_row(t, o):
    trig = 0 if o["kind"] is None else 1
    return (f"| {t} | {trig} | {o['pc']} | {port(o['idx0'], o['w0'])} | {port(o['idx1'], o['w1'])} | "
            f"{issued(o)} | {bank(o)} | {loop_s(o['after']['loop'])} | {o['after']['pc']} |")


# Case A: the loop of the programmer's guide, one trigger per cycle.
PROG_A = ["MOV GRF_A[0], EVEN_BANK", "JUMP -1, 2", "EXIT"]
topA, cycA = run(PROG_A, [T(1), T(2), T(3), T(4), B, B])
show("Case A", "JUMP -1, 2: the JUMP's next word on port 1, in the same cycle", PROG_A, cycA, FETCH_HEAD, fetch_row)
if [o["kind"] for _, o in cycA[:4]] != ["OP", "OP", "OP", "EXIT"]:
    failures.append("case A: slots")

# Case B: guide case 9, a JUMP right after a JUMP ([TOP-ISA-27]).
PROG_B = ["MOV GRF_A[0], EVEN_BANK", "JUMP -1, 1", "JUMP -2, 0", "EXIT"]
_, cycB = run(PROG_B, [T(1), T(2), T(3), T(4), T(5)])
show("Case B", "a JUMP right after a JUMP: port 1 returns a JUMP", PROG_B, cycB, FETCH_HEAD, fetch_row)
if [o["kind"] for _, o in cycB] != ["OP", "OP", "HOLD", "EXIT", "OP"]:
    failures.append("case B: slots")

# Case C: bubbles inside a loop, EXIT, then a CRF write while idle and the
# next run. Option (b), a read-ahead register loaded at each slot and at
# reset, is shown next to it.
PROG_C = ["MOV GRF_A[0], EVEN_BANK", "JUMP -1, 1", "EXIT"]
NEW0 = assemble("MOV GRF_B[0], ODD_BANK")
stimC = [T(1), B, T(3), B, T(5)] + [B] * 4 + [dict(cfg=(0, NEW0)), T(11)]
topC, cycC = run(PROG_C, stimC)
# option (b): ir holds CRF[pc] as loaded at the end of the last slot (or reset)
ir, crf_b, ir_col = assemble(PROG_C[0]), list(Top(PROG_C).crf), []
for t, o in cycC:
    ir_col.append(ir)
    if o["kind"] is not None:
        ir = crf_b[o["after"]["pc"]]
    if o["cfg"] == "takes effect":
        crf_b[0] = NEW0
C_HEAD = ("| Cycle | `trig_valid` | `pc` | port 0: word | port 1: word | The slot issues | `bank_rd_en`, sel, col"
          " | `busy` (top) | CRF write | (b): word in the read-ahead register |")


def c_row(t, o):
    trig = 0 if o["kind"] is None else 1
    return (f"| {t} | {trig} | {o['pc']} | {wname(o['w0'])} | {wname(o['w1'])} | {issued(o)} | {bank(o)} | "
            f"{o['top_busy']} | {o['cfg']} | {wname(ir_col[t - 1])} |")


show("Case C", "bubbles, EXIT, a CRF write while idle, and the next run", PROG_C, cycC, C_HEAD, c_row)
last = cycC[-1][1]
if not (last["kind"] == "OP" and last["bank_rd_sel"] == 1 and wname(ir_col[-1]) != wname(last["w0"])):
    failures.append("case C: the new CRF[0] isn't fetched, or (b) isn't stale")

# Case D: triggers in reset cycles (#41).
PROG_D = ["MOV GRF_A[0], EVEN_BANK", ILL_WORD, "MOV GRF_B[0], ODD_BANK", "EXIT"]
stimD = [dict(rst_n=0), T(2), T(3), B, dict(rst_n=0, trig=1, col=5), T(6), dict(rst_n=0, trig=1, col=7), B]
topD, cycD = run(PROG_D, stimD)
D_HEAD = ("| Cycle | `rst_n` | `trig_valid` | `pc` | CRF[`pc`] | The slot issues | `bank_rd_en` (chosen)"
          " | `bank_rd_en` under (b) | `err_illegal` | `iss_valid` | `busy` (top) |")


def d_row(t, o):
    s = stimD[t - 1]
    rst, trig = s.get("rst_n", 1), s.get("trig", 0)
    w = o["w0"]
    bk = dec(w)[1]                       # (b): the outputs follow the word, reset or not
    b_en = trig == 1 and o["kind"] is None and rst == 0 and bk is not None
    b = bank(o) if o["bank_rd_en"] else (f"1, {bk.split('_')[0]}, col {s['col']}" if b_en else "0")
    return (f"| {t} | {rst} | {trig} | {o['pc']} | {wname(w)} | {issued(o)} | {bank(o)} | {b} | "
            f"{o['err_illegal']} | {o['iss_valid']} | {o['top_busy']} |")


show("Case D", "triggers in cycles with rst_n = 0", PROG_D, cycD, D_HEAD, d_row)
if any(o["bank_rd_en"] for t, o in cycD if stimD[t - 1].get("rst_n", 1) == 0):
    failures.append("case D: bank_rd_en = 1 in a reset cycle")
if topD.ctrl.err != 0 or cycD[3][1]["err_illegal"] != 1:
    failures.append("case D: err_illegal")

# Case E: the JUMP range check and when err_illegal rises (guide case 7,
# with a bubble after the JUMP).
PROG_E = ["MOV GRF_A[0], EVEN_BANK", "MOV GRF_B[0], ODD_BANK", "JUMP -5, 1", "EXIT"]
_, cycE = run(PROG_E, [T(1), T(2), T(3), B, T(5), T(6)])
E_HEAD = ("| Cycle | `trig_valid` | `pc` | port 0: word | IMM0 > `pc`? | port 1 | The slot issues"
          " | `bank_rd_en` | `err_illegal` | `loop_active` after |")


def e_row(t, o):
    trig = 0 if o["kind"] is None else 1
    w0 = o["w0"]
    cmp = f"{imm0(w0)} > {o['pc']}: {'yes' if imm0(w0) > o['pc'] else 'no'}" if opcode(w0) == JUMP_OP else "–"
    return (f"| {t} | {trig} | {o['pc']} | {wname(w0)} | {cmp} | {port(o['idx1'], o['w1'])} | {issued(o)} | "
            f"{o['bank_rd_en']} | {o['err_illegal']} | {o['after']['loop'][0]} |")


show("Case E", "JUMP -5, 1 at PC 2, and err_illegal", PROG_E, cycE, E_HEAD, e_row)
if [o["err_illegal"] for _, o in cycE] != [0, 0, 0, 1, 1, 1]:
    failures.append("case E: err_illegal timing")


# Case F: option (c) of #27, resolving a JUMP at the end of the slot before
# it, against the chosen fetch. One trigger only, then idle.
def early(prog, stim):
    """Option (c): after each slot, if the next word is a legal JUMP and no
    NOP slots are left, resolve it at once (loop state and PC)."""
    top = Top(prog)
    rows = []
    for t, s in enumerate(stim, 1):
        o = top.cycle(**s)
        c = top.ctrl
        w = c.crf[c.pc]
        if o["kind"] is not None and c.nop_cnt == 0 and opcode(w) == JUMP_OP and 1 <= imm0(w) <= c.pc:
            if not c.loop_active and imm1(w) >= 1:
                c.loop_active, c.loop_cnt, c.pc = 1, imm1(w) - 1, c.pc - imm0(w)
            elif not c.loop_active:
                c.pc += 1
            elif c.loop_cnt:
                c.loop_cnt, c.pc = c.loop_cnt - 1, c.pc - imm0(w)
            else:
                c.loop_active, c.pc = 0, c.pc + 1
        rows.append((t, o, c.pc, c.loop_active, top.busy()))
    return rows


stimF = [T(1)] + [B] * 7
_, cycF = run(PROG_A, stimF)
earlyF = early(PROG_A, stimF)
F_HEAD = ("| Cycle | `trig_valid` | chosen: `pc` after | chosen: `loop_active` after | chosen: `busy` (top)"
          " | (c): `pc` after | (c): `loop_active` after | (c): `busy` (top) |")
lines = [F_HEAD, "|" + "---|" * 8]
for (t, o), (_, _, epc, eact, _) in zip(cycF, earlyF):
    lines.append(f"| {t} | {stimF[t - 1].get('trig', 0)} | {o['after']['pc']} | {o['after']['loop'][0]} | "
                 f"{o['top_busy']} | {epc} | {eact} | ")
# busy is the value during the cycle: take (c)'s from the cycle before's end
ebusy = [0] + [r[4] for r in earlyF[:-1]]
lines = lines[:2] + [l + f"{b} |" for l, b in zip(lines[2:], ebusy)]
tableF = "\n".join(lines)
print("\nCase F: one trigger before a JUMP, chosen fetch against option (c)\n")
print(tableF)
check_in_doc("Case F", tableF)
if cycF[-1][1]["top_busy"] != 0 or ebusy[-1] != 1:
    failures.append("case F: busy")

# ---------------------------------------------------------------------------
# 2. Figure 1 against case A.
fig = json.loads(WAVE.read_text())


def expand(sig):
    vals, data, cur = [], list(sig.get("data", [])), None
    for ch in sig["wave"]:
        if ch == ".":
            pass
        elif ch in "01":
            cur = ch
        elif ch == "x":
            cur = None
        elif ch == "=" or ch.isdigit():
            cur = data.pop(0)
        vals.append(cur)
    return vals


model = {
    "trig_valid": lambda o: "1" if o["kind"] else "0",
    "trig_col": lambda o: str(o["iss_col_in"]) if o["kind"] else None,
    "pc (internal)": lambda o: str(o["pc"]),
    "crf_rd_idx[0]": lambda o: str(o["idx0"]),
    "crf_rd_data[0]": lambda o: wname(o["w0"]).split()[0],
    "crf_rd_idx[1]": lambda o: None if o["idx1"] is None else str(o["idx1"]),
    "crf_rd_data[1]": lambda o: None if o["w1"] is None else wname(o["w1"]).split()[0],
    "bank_rd_en": lambda o: str(o["bank_rd_en"]),
    "bank_rd_col": lambda o: None if not o["bank_rd_en"] else str(o["bank_rd_col"]),
    "loop_active (internal)": lambda o: str(o["loop"][0]),
    "loop_cnt (internal)": lambda o: str(o["loop"][1]) if o["loop"][0] else None,
    "iss_valid": lambda o: str(o["iss_valid"]),
    "busy": lambda o: str(o["busy"]),
}
for t, o in cycA:
    o["iss_col_in"] = t if o["kind"] else None
def flat(items):
    for it in items:
        if isinstance(it, list):          # a group: ["name", signal, ...]
            yield from flat(it[1:])
        elif it and it.get("name") != "clk":
            yield it


n_cells = 0
for sig in flat(fig["signal"]):
    name = sig["name"]
    if name not in model:
        failures.append(f"figure 1: unknown signal {name}")
        continue
    got = expand(sig)
    want = [model[name](o) for _, o in cycA]
    if len(got) != len(want):
        failures.append(f"figure 1: {name} has {len(got)} cycles, the case {len(want)}")
    for t, (g, w) in enumerate(zip(got, want), 1):
        n_cells += 1
        if g != w:
            failures.append(f"figure 1: {name}, cycle {t}: diagram {g}, model {w}")
print(f"\nFigure 1: {n_cells} cells checked against case A")

# ---------------------------------------------------------------------------
# 3. The range check against check_isa.py's legal(word, pc), every PC and IMM0.
n = 0
for pc in range(CRF_N):
    for i0 in range(256):
        for i1 in (0, 1, 2047):
            w = (JUMP_OP << 28) | (i0 << 11) | i1
            crf = [assemble("NOP 1")] * CRF_N
            crf[pc] = w
            c = Ctrl(crf)
            c.pc = pc
            o = c.comb(1, 1, 0, 0)
            n += 1
            if (o["kind"] == "ILLJ") != (not legal(w, pc)):
                failures.append(f"range check: pc {pc}, IMM0 {i0}")
print(f"Range check: {n} JUMP words, ILLJ exactly when check_isa.py's legal(word, pc) is false")

# ---------------------------------------------------------------------------
# 4. Random programs against the top spec's slot-level and busy models.
loop = load("loop_trace.py")
busy_m = load("busy_trace.py")
Unit = loop["Unit"]


def unit_issued(o):
    k = o["kind"]
    if k == "NOPSLOT":
        return "(NOP slot)"
    if k == "HOLD":
        return f"NOP 1 (the JUMP at PC {o['a1']} waits)"
    if k == "ILLJ":
        return f"PC {o['pc']} JUMP illegal"
    if k == "ILL":
        return f"PC {o['p']} ILL"
    return f"PC {o['p']} {wname(o['w']).split()[0]}"


rng = random.Random(30)
MOVS = ["MOV GRF_A[0], EVEN_BANK", "MOV GRF_B[1], ODD_BANK", "MOV GRF_A[1], GRF_B[2]", "MOV EVEN_BANK, GRF_A[3]"]
stats = dict(slots=0, cycles=0, holds=0, jres=0, ill=0, illj=0, resets=0, two_reads=0)
for prog_i in range(4000):
    legal_jumps = prog_i % 2 == 0           # busy_trace.py assumes legal IMM0
    n_words = rng.randint(2, 10)
    text, tuples = [], []
    for pc in range(n_words):
        r = rng.random()
        if r < 0.35:
            m = rng.choice(MOVS)
            text.append(m), tuples.append(("OP", m))
        elif r < 0.5:
            k = rng.randint(0, 3)
            text.append(f"NOP {k}"), tuples.append(("NOP", k))
        elif r < 0.75 and pc >= 1:
            i0 = rng.randint(1, pc) if legal_jumps else rng.randint(0, pc + 2)
            i1 = rng.randint(0, 3)
            text.append(f"JUMP -{i0}, {i1}"), tuples.append(("JUMP", i0, i1))
        elif r < 0.85:
            text.append("ILL"), tuples.append(("ILL", "illegal"))
        else:
            text.append("EXIT"), tuples.append(("EXIT",))
    words = [ILL_WORD if x == "ILL" else assemble(x) for x in text]
    n_cyc = rng.randint(10, 60)
    trig = [int(rng.random() < 0.7) for _ in range(n_cyc)]
    rst = [int(rng.random() < 0.03) for _ in range(n_cyc)]
    top = Top(words)
    unit, ill_seen = Unit(list(text)), 0
    ours_busy = []
    for t in range(n_cyc + 6):
        tr, rs = (trig[t], rst[t]) if t < n_cyc else (0, 0)
        o = top.cycle(rst_n=1 - rs, trig=tr, col=t % 32)
        ours_busy.append(o["top_busy"])
        stats["cycles"] += 1
        if rs:
            stats["resets"] += 1
            unit, ill_seen = Unit(list(text)), 0
            continue
        if not tr:
            continue
        stats["slots"] += 1
        stats["jres"] += o["jres"]
        stats["two_reads"] += o["jres"] and o["kind"] != "NOPSLOT"
        stats["holds"] += o["kind"] == "HOLD"
        stats["ill"] += o["kind"] == "ILL"
        stats["illj"] += o["kind"] == "ILLJ"
        ill_seen |= o["kind"] == "ILL"
        _, want = unit.slot()
        got = unit_issued(o)
        a = o["after"]
        u_state = (unit.pc, int(unit.active), unit.cnt if unit.active else None, unit.nop_left,
                   int(unit.err or ill_seen))
        m_state = (a["pc"], a["loop"][0], a["loop"][1] if a["loop"][0] else None, a["nop"], a["err"])
        if got != want or u_state != m_state:
            failures.append(f"program {prog_i} {text}, cycle {t + 1}: {got} / {want}, {m_state} / {u_state}")
            break
        if o["bank_rd_en"] != int(o["kind"] == "OP" and "BANK" in wname(o["w"]).split(",")[1]):
            failures.append(f"program {prog_i}, cycle {t + 1}: bank_rd_en")
    if legal_jumps:
        padded = tuples + [("NOP", 1)] * (CRF_N - len(tuples))
        rows = busy_m["run"](padded, trig, rst)
        want = [r["busy"] for r in rows]
        if ours_busy[:len(want)] != want:
            failures.append(f"program {prog_i} {text}: busy differs from busy_trace.py")
print(f"\nRandom runs (seed 30): 4000 programs, {stats['cycles']} cycles, {stats['slots']} slots, "
      f"{stats['resets']} reset cycles")
print(f"  every slot == loop_trace.py's Unit (issued word, PC, loop state, NOP counter, err_illegal)")
print(f"  every cycle's busy == busy_trace.py's run() (the 2000 programs with legal JUMPs)")
print(f"  slots that resolved a JUMP and read CRF twice: {stats['two_reads']}; held over "
      f"([TOP-ISA-27]): {stats['holds']}, which would need a third read without the hold")
print(f"  illegal words: {stats['ill']}, out-of-range JUMPs: {stats['illj']}")

# ---------------------------------------------------------------------------
# 5. ANEMOS, case A of anemos_ctrl.out: commands up to EXIT.
out = (TOPX / "anemos_ctrl.out").read_text().split("Case A:")[1].split("Case ")[0]
cmds = [l.split() for l in out.splitlines() if l.strip() and l.split()[0].isdigit()]
k = next(i for i, f in enumerate(cmds, 1) if f[3] == "EXIT")
jumps = sum(f[3] == "JUMP" for f in cmds[:k])
ours = next(t for t, o in cycA if o["kind"] == "EXIT")
print(f"\nANEMOS (anemos_ctrl.out, case A): EXIT on command {k}, {jumps} of them JUMP fetches; "
      f"pcu_ctrl: EXIT in slot {ours}, no slot for a JUMP")
if (k, jumps, ours) != (7, 3, 4):
    failures.append("ANEMOS case A")

if failures:
    print("\nFAIL:", *failures[:20], sep="\n  ")
    sys.exit(1)
print("\nok   all cases match the doc")
