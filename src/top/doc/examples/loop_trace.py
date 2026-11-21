#!/usr/bin/env python3
"""Worked cases for the program counter, NOP and the JUMP loop state.

A slot-level model of [TOP-ISA-3], [TOP-ISA-5], [TOP-ISA-8], [TOP-ISA-12],
[TOP-ISA-13] and [TOP-ISA-26] to [TOP-ISA-28], next to the ANEMOS behaviour (src/instr_decoder.cpp and
src/pc_unit.cpp of github.com/gem5-X/cnm_framework, commit f2d4018), so the
cases where they differ are shown.

  - prints the trace of `JUMP -1, 2` and checks it against the table in
    programmers_guide.md ("Worked case" under JUMP);
  - counts body executions for several IMM1, NOP slots for several IMM0,
    and shows the PC wrap;
  - traces the broken-rule cases of [TOP-ISA-26], [TOP-ISA-27] and
    [TOP-ISA-28] next to ANEMOS and checks them against the guide's tables;
    if anemos_ctrl.out is present, checks the ANEMOS model against that run
    of ANEMOS's own decoder and PC unit.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/loop_trace.py
"""
import re
import sys
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent / "programmers_guide.md"
CRF = 32


class Unit:
    """Fetch-side state only: PC, loop state, NOP counter, err_illegal.

    bankside: [TOP-ISA-3], [TOP-ISA-4] (a JUMP takes no slot), [TOP-ISA-26]
    (a JUMP outside [TOP-ISA-14] is illegal), [TOP-ISA-27] (a JUMP reached
    from a JUMP waits one NOP slot), [TOP-ISA-28] (one loop state for every
    JUMP).
    anemos: its decoder and PC unit as read and run (anemos_ctrl.out): every
    JUMP fetch takes a triggering command, the PC is 8 bits wide, a CRF read
    at PC >= 32 returns the word 0 (NOP 0), and the PC goes from >= 31 to 0.
    """

    def __init__(self, prog, anemos=False):
        self.prog = prog + ["NOP 1"] * (CRF - len(prog))
        self.anemos = anemos
        self.pc, self.active, self.cnt, self.nop_left = 0, False, 0, 0
        self.err = 0

    def word(self, pc):
        return self.prog[pc] if pc < CRF else "NOP 0"   # ANEMOS: out of range

    def advance(self):
        if self.anemos:
            self.pc = self.pc + 1 if self.pc < CRF - 1 else 0
        else:
            self.pc = (self.pc + 1) % CRF                 # [TOP-ISA-8]

    def jump(self, off, imm1):
        """Apply one JUMP fetch; returns the description of what it did."""
        before = (self.active, self.cnt)
        if not self.active and (imm1 >= 1 or self.anemos):
            self.active = True
            # ANEMOS: jmp_cnt_nxt = IMM1 - 1 into a 32-bit uint.
            self.cnt = (imm1 - 1) % (1 << 32) if self.anemos else imm1 - 1
            taken = True
        elif not self.active:              # [TOP-ISA-13]: IMM1 = 0
            taken = False
        elif self.cnt != 0:
            self.cnt -= 1
            taken = True
        else:
            self.active = False
            taken = False
        jpc = self.pc
        if taken:
            self.pc = (self.pc - off) % (256 if self.anemos else CRF)
        else:
            self.advance()
        a0, c0 = before
        act = f"active {int(a0)}" + (f" → {int(self.active)}" if a0 != self.active else "")
        c0s = str(c0) if a0 else "–"
        cnt = f"cnt {c0s}" + (f" → {self.cnt}" if self.active and (not a0 or c0 != self.cnt) else "")
        return f"PC {jpc}: {act}, {cnt}, " + (f"jump to {self.pc}" if taken else "fall through")

    def slot(self):
        """One triggering command. Returns (jump description, issued text)."""
        if self.nop_left:                  # a multi-cycle NOP keeps the slot
            self.nop_left -= 1
            if not self.nop_left:
                self.advance()
            return "–", "(NOP slot)"
        jdesc = "–"
        ins = self.word(self.pc)
        if ins.startswith("JUMP"):
            off, imm1 = map(int, re.findall(r"\d+", ins))
            if self.anemos:                # one command per JUMP fetch
                jpc = self.pc
                jdesc = self.jump(off, imm1)
                return jdesc, f"PC {jpc} JUMP"
            if off == 0 or off > self.pc:  # [TOP-ISA-26]: illegal, one slot
                self.err = 1
                jpc = self.pc
                self.advance()
                return "–", f"PC {jpc} JUMP illegal"
            jdesc = self.jump(off, imm1)   # zero slots: resolve, refetch
            ins = self.word(self.pc)
            if ins.startswith("JUMP"):     # [TOP-ISA-27]: wait one slot
                return jdesc, f"NOP 1 (the JUMP at PC {self.pc} waits)"
        issued = f"PC {self.pc} {ins.split()[0]}"
        if ins.startswith("NOP"):
            imm0 = int(ins.split()[1])
            if self.anemos:                # nop_cnt_nxt = IMM0 - 1, uint8
                n = 1 + (imm0 - 1) % 256
            else:                          # [TOP-ISA-12]
                n = max(imm0, 1)
            self.nop_left = n - 1
            if not self.nop_left:
                self.advance()
        elif ins.startswith("EXIT"):       # [TOP-ISA-5]
            self.pc = 0
            if not self.anemos:            # ANEMOS resets only the PC
                self.active, self.cnt = False, 0
        else:
            self.advance()
        return jdesc, issued


def run_until_exit(prog, anemos=False, limit=10_000):
    u = Unit(prog, anemos)
    rows, body = [], 0
    for s in range(1, limit + 1):
        j, issued = u.slot()
        rows.append((s, j, issued, u.pc))
        body += issued == "PC 0 MOV"
        if issued.endswith("EXIT"):
            return rows, body, u
    return rows, body, u


failures = []

# Case 1: the trace in the guide.
prog = ["MOV GRF_A[0], EVEN_BANK", "JUMP -1, 2", "EXIT"]
rows, body, _ = run_until_exit(prog)
table = ["| Slot | JUMP fetched (state before → after) | Instruction issued | PC after |",
         "|---|---|---|---|"]
table += [f"| {s} | {j} | {i} | {pc} |" for s, j, i, pc in rows]
print("Case 1: JUMP -1, 2 (bankside)\n")
print("\n".join(table))
if "\n".join(table) not in GUIDE.read_text():
    failures.append("the guide's worked-case table differs from this trace")
print(f"\n  body ran {body} times (IMM1 + 1 = 3)\n")

# Case 2: body count against IMM1, bankside vs ANEMOS.
print("Case 2: times the body runs, `JUMP -1, IMM1`")
print("  (slots: triggering commands up to and including EXIT; ANEMOS spends")
print("  one on every JUMP fetch, bankside none, [TOP-ISA-4])")
print("  IMM1  bankside body/slots  ANEMOS body/slots")
for imm1 in (0, 1, 2, 7):
    p = ["MOV GRF_A[0], EVEN_BANK", f"JUMP -1, {imm1}", "EXIT"]
    rb, b, _ = run_until_exit(p)
    ra, a, ua = run_until_exit(p, anemos=True)
    a_txt = f"{a}/{len(ra)}" if not ua.active else f">{a} (still looping, cnt {ua.cnt})"
    print(f"  {imm1:4}  {b:>10}/{len(rb):<6}  {a_txt}")
    if b != imm1 + 1:
        failures.append(f"IMM1 = {imm1}: body {b}")

# Case 3: slots taken by NOP IMM0.
print("\nCase 3: slots taken by `NOP IMM0`")
print("  IMM0  bankside  ANEMOS")
for imm0 in (0, 1, 2, 255):
    counts = []
    for anemos in (False, True):
        u = Unit([f"NOP {imm0}", "EXIT"], anemos)
        n = 0
        while True:
            n += 1
            _, issued = u.slot()
            if u.pc == 1 and not u.nop_left:
                break
        counts.append(n)
    print(f"  {imm0:4}  {counts[0]:8}  {counts[1]}")
    if counts[0] != max(imm0, 1):
        failures.append(f"NOP {imm0}: {counts[0]} slots")

# Case 4: the PC wraps from 31 to 0 ([TOP-ISA-8]); same in ANEMOS.
u = Unit(["NOP 1"] * CRF)
pcs = []
for _ in range(CRF + 2):
    pcs.append(u.pc)
    u.slot()
print(f"\nCase 4: PC over {CRF + 2} slots of NOP 1: ... {pcs[-4:]}")
if pcs[-4:] != [30, 31, 0, 1]:
    failures.append("PC wrap")

# Case 5: the guide's ReLU kernel runs its body n times.
print("\nCase 5: ReLU kernel, `JUMP -3, n-1`: body runs")
for n in (1, 2, 5):
    k = ["MOV(RELU) GRF_A[0], EVEN_BANK", "NOP 2", "MOV EVEN_BANK, GRF_A[0]",
         f"JUMP -3, {n - 1}", "EXIT"]
    rows, _, _ = run_until_exit(k)
    loads = sum(i == "PC 0 MOV(RELU)" for _, _, i, _ in rows)
    print(f"  n = {n}: {loads} times, {len(rows)} slots (4 per column + EXIT)")
    if loads != n or len(rows) != 4 * n + 1:
        failures.append(f"ReLU kernel n = {n}")


# Cases 6 to 10: the rules of [TOP-ISA-6], [TOP-ISA-7] and [TOP-ISA-14]
# broken, bankside next to ANEMOS, one row per triggering command. The
# ANEMOS column is this model; with anemos_ctrl.out present it is also
# checked against ANEMOS's own decoder and PC unit, run (anemos_ctrl.cpp).
ANEMOS_OUT = Path(__file__).resolve().parent / "anemos_ctrl.out"


def anemos_run(letter):
    """(PC, word) per triggering command from anemos_ctrl.out, case `letter`."""
    if not ANEMOS_OUT.exists():
        return None
    text = ANEMOS_OUT.read_text().split(f"Case {letter}:")[1].split("Case ")[0]
    rows = []
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 7 and f[0].isdigit() and f[1] == "1":
            rows.append("(NOP slot)" if f[4] != "0" else f"PC {f[2]} {f[3]}")
    return rows


def side_by_side(title, letter, prog, slots, guide_check=True):
    b, a = Unit(prog), Unit(prog, anemos=True)
    lines = ["| Slot | bankside: issued | `err_illegal` | bankside loop state after | ANEMOS: decoded | ANEMOS loop state after |",
             "|---|---|---|---|---|---|"]
    a_issued = []
    for s in range(1, slots + 1):
        _, ib = b.slot()
        _, ia = a.slot()
        a_issued.append(ia)
        st = lambda u: f"active {int(u.active)}" + (f", cnt {u.cnt}" if u.active else "")
        lines.append(f"| {s} | {ib} | {b.err} | {st(b)} | {ia} | {st(a)} |")
    table = "\n".join(lines)
    print(f"\nCase {title}\n")
    for i, l in enumerate(prog):
        print(f"    PC {i}  {l}")
    print()
    print(table)
    if guide_check and table not in GUIDE.read_text():
        failures.append(f"case {letter}: the guide's table differs from this trace")
    run = anemos_run(letter)
    if run is not None:
        n = min(len(run), slots)
        ok = run[:n] == a_issued[:n]
        print(f"\n  ANEMOS column == anemos_ctrl.out case {letter}, {n} commands: {ok}")
        if not ok:
            failures.append(f"case {letter}: ANEMOS model != ANEMOS run: {run[:n]} {a_issued[:n]}")
    return b, a


MOV0, MOVB, MOV1 = "MOV GRF_A[0], EVEN_BANK", "MOV GRF_B[0], ODD_BANK", "MOV GRF_A[1], EVEN_BANK"
b, _ = side_by_side("6: JUMP -0, 3 at PC 1, IMM0 = 0 ([TOP-ISA-14] broken, [TOP-ISA-26])",
                    "B", [MOV0, "JUMP -0, 3", "EXIT"], 4)
if b.err != 1:
    failures.append("case 6: err_illegal not set")
b, _ = side_by_side("7: JUMP -5, 1 at PC 2, IMM0 > PC ([TOP-ISA-14] broken, [TOP-ISA-26])",
                    "C", [MOV0, MOVB, "JUMP -5, 1", "EXIT"], 5)
if b.err != 1:
    failures.append("case 7: err_illegal not set")
b, _ = side_by_side("8: nested loops ([TOP-ISA-6] broken, [TOP-ISA-28])",
                    "D", [MOV0, MOVB, "JUMP -1, 1", MOV1, "JUMP -4, 1", "EXIT"], 14)
rows, body, u = run_until_exit([MOV0, MOVB, "JUMP -1, 1", MOV1, "JUMP -4, 1", "EXIT"], limit=1000)
print(f"\n  bankside reaches EXIT within 1000 slots: {rows[-1][2].endswith('EXIT')}"
      f" (meant: PC 1 runs 4 times, EXIT in slot 9)")
if rows[-1][2].endswith("EXIT"):
    failures.append("case 8: nested loops terminated")
b, _ = side_by_side("9: a JUMP right after a JUMP ([TOP-ISA-7] broken, [TOP-ISA-27])",
                    "E", [MOV0, "JUMP -1, 1", "JUMP -2, 0", "EXIT"], 5)
if b.err != 0:
    failures.append("case 9: err_illegal set")

# Case 10: ANEMOS's NOP counts clock cycles, not commands (anemos_ctrl.out F).
print("\nCase 10: `NOP 3`, then MOV, with a triggering command every 2nd cycle")
print("  bankside: the MOV issues on the 4th command ([TOP-ISA-12])")
run = anemos_run("F")
if run is not None:
    k = run.index("PC 1 MOV") + 1
    print(f"  ANEMOS run: the MOV decodes on command {k}: {run[:k]}")
    if k != 3:
        failures.append(f"case 10: ANEMOS MOV on command {k}")

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all cases match the spec")
