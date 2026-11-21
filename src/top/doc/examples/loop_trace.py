#!/usr/bin/env python3
"""Worked cases for the program counter, NOP and the JUMP loop state.

A slot-level model of [TOP-ISA-3], [TOP-ISA-5], [TOP-ISA-8], [TOP-ISA-12] and
[TOP-ISA-13], next to the ANEMOS behaviour (src/instr_decoder.cpp and
src/pc_unit.cpp of github.com/gem5-X/cnm_framework, commit f2d4018), so the
cases where they differ are shown.

  - prints the trace of `JUMP -1, 2` and checks it against the table in
    programmers_guide.md ("Worked case" under JUMP);
  - counts body executions for several IMM1, NOP slots for several IMM0,
    and shows the PC wrap.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/loop_trace.py
"""
import re
import sys
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent / "programmers_guide.md"
CRF = 32


class Unit:
    """Fetch-side state only: PC, loop state, NOP counter."""

    def __init__(self, prog, anemos=False):
        self.prog = prog + ["NOP 1"] * (CRF - len(prog))
        self.anemos = anemos
        self.pc, self.active, self.cnt, self.nop_left = 0, False, 0, 0

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
        self.pc = (self.pc - off) % CRF if taken else (self.pc + 1) % CRF
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
                self.pc = (self.pc + 1) % CRF
            return "–", "(NOP slot)"
        jdesc = "–"
        ins = self.prog[self.pc]
        if ins.startswith("JUMP"):         # zero slots: resolve, refetch
            off, imm1 = map(int, re.findall(r"\d+", ins))
            jdesc = self.jump(off, imm1)
            ins = self.prog[self.pc]
            assert not ins.startswith("JUMP"), "[TOP-ISA-7] broken"
        issued = f"PC {self.pc} {ins.split()[0]}"
        if ins.startswith("NOP"):
            imm0 = int(ins.split()[1])
            if self.anemos:                # nop_cnt_nxt = IMM0 - 1, uint8
                n = 1 + (imm0 - 1) % 256
            else:                          # [TOP-ISA-12]
                n = max(imm0, 1)
            self.nop_left = n - 1
            if not self.nop_left:
                self.pc = (self.pc + 1) % CRF
        elif ins.startswith("EXIT"):       # [TOP-ISA-5]
            self.pc = 0
            if not self.anemos:            # ANEMOS resets only the PC
                self.active, self.cnt = False, 0
        else:
            self.pc = (self.pc + 1) % CRF  # [TOP-ISA-8]
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
print("  IMM1  bankside  ANEMOS")
for imm1 in (0, 1, 2, 7):
    p = ["MOV GRF_A[0], EVEN_BANK", f"JUMP -1, {imm1}", "EXIT"]
    _, b, _ = run_until_exit(p)
    _, a, ua = run_until_exit(p, anemos=True)
    a_txt = str(a) if not ua.active else f">{a} (still looping, cnt {ua.cnt})"
    print(f"  {imm1:4}  {b:8}  {a_txt}")
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

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all cases match the spec")
