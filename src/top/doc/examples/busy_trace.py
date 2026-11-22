#!/usr/bin/env python3
"""When `busy` rises and falls ([TOP-IF-7]), traced cycle by cycle.

Backs [TOP-IF-7] and its worked cases in ../interfaces.md, and checks that
the choice keeps [TOP-IF-8] (configuration writes ignored while busy = 1 or
trig_valid = 1) and [TOP-HIER-6] (a configuration write that counts never
meets an S5 write).

The model is slot-level control only, from the programmer's guide: one slot
per cycle with trig_valid = 1 ([TOP-IF-1]); NOP n takes max(n, 1) slots and
holds the PC until its last one ([TOP-ISA-12], [TOP-ISA-8]); a JUMP takes no
slot and acts on the loop state as the table of [TOP-ISA-3] says
([TOP-ISA-4]); a JUMP reached from a JUMP waits one NOP 1 slot
([TOP-ISA-27]); EXIT sets PC <- 0 and clears the loop state ([TOP-ISA-5]);
an illegal word takes one slot ([TOP-ISA-24]). A cycle with rst_n = 0 makes
no entry and its closing edge clears the PC, the loop state, the NOP counter
and every pipeline stage ([TOP-IF-4]).

The state the unit holds during cycle t is the state left by the edge that
ends cycle t - 1. Three definitions of busy are compared:

  chosen   busy(t) = an entry in S2, S3, S4 or S5 in cycle t (a slot issued
           in cycles t-4 .. t-1, not cancelled by reset), or NOP slots left,
           or loop_active = 1. Every slot is an entry, whatever it issues.
           No input enters it: it comes from registers only.
  (1b)     the chosen busy, OR trig_valid in the same cycle (an entry in S1
           counts; a path from the trig_valid input to the busy output).
  (2b)     like the chosen busy, but only entries that write a register file
           or the bank count (NOP slots, EXIT and illegal words don't).

Run from the repo root:
    .venv/bin/python src/top/doc/examples/busy_trace.py
Exits non-zero if a check fails, including when a table printed here is not
in interfaces.md word for word.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = open(os.path.join(HERE, "..", "interfaces.md")).read()
failures = []

# Program words: ("OP", text) one slot with a write; ("NOP", n);
# ("JUMP", imm0, imm1); ("EXIT",); ("ILL", text) one slot, no write.


def wtext(w):
    if w[0] in ("OP", "ILL"):
        return w[1]
    if w[0] == "NOP":
        return f"NOP {w[1]}"
    if w[0] == "JUMP":
        return f"JUMP -{w[1]}, {w[2]}"
    return "EXIT"


def run(program, trig, rst=None):
    """Returns one dict per cycle 1..len(trig)+6 with the issued slot, the
    state held during the cycle and the three busy values."""
    n = len(trig) + 6
    trig = list(trig) + [0] * 6
    rst = (list(rst) if rst else []) + [0] * (n - len(rst or []))
    pc, nop_left, active, cnt = 0, 0, 0, 0
    entries = {}          # issue cycle -> (text, has a write)
    rows = []
    for t in range(1, n + 1):
        state = dict(nop_left=nop_left, active=active)
        issued = None
        if trig[t - 1] and not rst[t - 1]:
            if nop_left:
                nop_left -= 1
                issued = (f"PC {pc} NOP slot", False)
                if nop_left == 0:
                    pc = (pc + 1) % 32
            else:
                w = program[pc]
                if w[0] == "JUMP":
                    # [TOP-ISA-3]; IMM0 assumed legal ([TOP-ISA-14])
                    if not active and w[2] >= 1:
                        npc, active, cnt = pc - w[1], 1, w[2] - 1
                    elif not active:
                        npc = pc + 1
                    elif cnt != 0:
                        npc, cnt = pc - w[1], cnt - 1
                    else:
                        npc, active = pc + 1, 0
                    pc = npc % 32
                    w = program[pc]
                    if w[0] == "JUMP":           # [TOP-ISA-27]
                        issued = ("NOP 1 (JUMP waits)", False)
                        w = None
                if w is not None:
                    issued = (f"PC {pc} {wtext(w)}", w[0] == "OP")
                    if w[0] == "NOP" and max(w[1], 1) > 1:
                        nop_left = max(w[1], 1) - 1
                    elif w[0] == "EXIT":
                        pc, active, cnt = 0, 0, 0
                    else:
                        pc = (pc + 1) % 32
            entries[t] = issued
        live = [c for c in range(t - 4, t) if c in entries]
        stages = {f"S{t - c + 1}": entries[c] for c in live}
        busy = int(bool(live) or state["nop_left"] > 0 or state["active"] == 1)
        busy_1b = int(busy or trig[t - 1] == 1)
        busy_2b = int(any(entries[c][1] for c in live) or state["nop_left"] > 0 or state["active"] == 1)
        rows.append(dict(t=t, trig=trig[t - 1], rst=rst[t - 1], issued=issued, stages=stages,
                         s5=("S5" in stages), busy=busy, busy_1b=busy_1b, busy_2b=busy_2b, **state))
        if rst[t - 1]:
            pc, nop_left, active, cnt = 0, 0, 0, 0
            entries = {}
    return rows


def table(rows, cycles, with_2b=False):
    head = "| Cycle | `trig_valid` | Slot issued (S1) | In S2 to S5 | NOP slots left | `loop_active` | `busy` | (1b) | configuration write |"
    sep = "|---|---|---|---|---|---|---|---|---|"
    if with_2b:
        head = head.replace("| (1b) |", "| (1b) | (2b) |")
        sep += "---|"
    out = [head, sep]
    for r in rows:
        if r["t"] not in cycles:
            continue
        ins = r["issued"][0] if r["issued"] else "–"
        st = ", ".join(f"{k}: {v[0].split(' ', 2)[0] + ' ' + v[0].split(' ', 2)[1] if v[0].startswith('PC') else v[0]}"
                       for k, v in sorted(r["stages"].items())) or "–"
        cfg = "takes effect" if not r["busy"] and not r["trig"] else "ignored"
        cells = [str(r["t"]), str(r["trig"]), ins, st, str(r["nop_left"]), str(r["active"]),
                 f"**{r['busy']}**", str(r["busy_1b"])]
        if with_2b:
            cells.append(str(r["busy_2b"]))
        cells.append(cfg)
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def show(title, program, trig, cycles, with_2b=False, rst=None, in_spec=True):
    print(title)
    for pc, w in enumerate(program):
        print(f"    PC {pc}  {wtext(w)}")
    rows = run(program, trig, rst)
    tab = table(rows, cycles, with_2b)
    print(tab)
    print()
    if in_spec and tab not in SPEC:
        failures.append(f"{title}: table not in interfaces.md")
    return rows


def edges(rows, key):
    rise = [r["t"] for i, r in enumerate(rows) if r[key] and (i == 0 or not rows[i - 1][key])]
    fall = [r["t"] for i, r in enumerate(rows) if not r[key] and i > 0 and rows[i - 1][key]]
    return rise, fall


# 1. Worked cases ------------------------------------------------------------------
print("1. Worked cases (the tables are checked against interfaces.md)\n")

P = [("OP", "MOV GRF_A[0], EVEN_BANK"), ("EXIT",)]
rows = show("Case P: rise and fall. Idle in cycle 1, triggers in cycles 2 and 3",
            P, [0, 1, 1], range(1, 10))
print(f"  rise/fall chosen {edges(rows, 'busy')}, (1b) {edges(rows, 'busy_1b')}\n")
if edges(rows, "busy") != ([3], [8]) or edges(rows, "busy_1b") != ([2], [8]):
    failures.append("case P edges")

Q = [("OP", "ADD GRF_A[0], GRF_A[1], SRF_A[0]"), ("NOP", 3), ("EXIT",)]
rows = show("Case Q: bubbles inside a NOP. ADD in cycle 1, NOP slot 1 in 2, bubbles 3 to 8, slots 2 and 3 in 9 and 10, EXIT in 11",
            Q, [1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1], range(1, 17))
if edges(rows, "busy") != ([2], [16]):
    failures.append("case Q edges")

R = [("OP", "MOV GRF_A[0], EVEN_BANK"), ("JUMP", 1, 1), ("EXIT",)]
rows = show("Case R: bubbles inside a loop. Slot 2 starts the loop, bubbles 3 to 8, slot 3 ends it and issues EXIT",
            R, [1, 1, 0, 0, 0, 0, 0, 0, 1], range(1, 15), in_spec=False)
if edges(rows, "busy") != ([2], [14]):
    failures.append("case R edges")

S = [("OP", "MOV GRF_B[0], GRF_A[0]"), ("NOP", 2), ("EXIT",)]
rows = show("Case S: where (2b) differs. Triggers in cycles 1 to 4",
            S, [1, 1, 1, 1], range(1, 10), with_2b=True)
print(f"  falls: chosen {edges(rows, 'busy')[1]}, (2b) {edges(rows, 'busy_2b')[1]}\n")
if edges(rows, "busy")[1] != [9] or edges(rows, "busy_2b")[1] != [6]:
    failures.append("case S edges")

T = [("OP", "MOV GRF_A[0], EVEN_BANK"), ("JUMP", 1, 5), ("EXIT",)]
rows = show("Case T: the host stops inside a loop; rst_n = 0 in cycle 10",
            T, [1, 1] + [0] * 10, range(1, 13), rst=[0] * 9 + [1], in_spec=False)
if edges(rows, "busy") != ([2], [11]):
    failures.append("case T edges")

# 2. Random runs -------------------------------------------------------------------
rng = random.Random(24)
runs = cyc = acc_equal = acc_cycles = s5_meets = entries_ok = closed_ok = differ_2b = 0
max_shift = 0
for _ in range(5000):
    prog = []
    for pc in range(rng.randint(2, 10)):
        k = rng.choice(["OP", "OP", "NOP", "JUMP", "EXIT", "ILL"])
        if k == "OP":
            prog.append(("OP", "op"))
        elif k == "ILL":
            prog.append(("ILL", "illegal"))
        elif k == "NOP":
            prog.append(("NOP", rng.randint(0, 4)))
        elif k == "JUMP" and pc >= 1:
            prog.append(("JUMP", rng.randint(1, pc), rng.randint(0, 3)))
        else:
            prog.append(("EXIT",))
    prog += [("EXIT",)] * (32 - len(prog))
    trig = [rng.choice([1, 1, 0]) for _ in range(rng.randint(5, 40))]
    rst = [1 if rng.random() < 0.03 else 0 for _ in trig]
    rows = run(prog, trig, rst)
    runs += 1
    ntrig = sum(1 for a, b in zip(trig, rst) if a and not b)
    entries_ok += sum(1 for r in rows if r["issued"]) == ntrig
    for r in rows:
        cyc += 1
        a_chosen = not r["busy"] and not r["trig"]
        a_1b = not r["busy_1b"] and not r["trig"]
        acc_equal += a_chosen == a_1b
        acc_cycles += a_chosen
        s5_meets += a_chosen and (r["s5"] or r["nop_left"] > 0 or r["active"])
    # closed form after the last slot L (no reset after it): 1 in L+1..L+4,
    # then the NOP and loop state left by L, for good
    slots = [r["t"] for r in rows if r["issued"]]
    if slots and not any(r["rst"] for r in rows if r["t"] > slots[-1]):
        L = slots[-1]
        tail = rows[L:]
        hold = tail[4]["nop_left"] > 0 or tail[4]["active"] == 1
        closed_ok += all(r["busy"] for r in tail[:4]) and all(r["busy"] == hold for r in tail[4:])
    else:
        closed_ok += 1
    f_c = [r["t"] for r in rows if r["busy"]]
    f_b = [r["t"] for r in rows if r["busy_2b"]]
    if f_c != f_b:
        differ_2b += 1
        if f_c and f_b:
            max_shift = max(max_shift, f_c[-1] - f_b[-1])
        elif f_c:
            max_shift = max(max_shift, 4)

print("2. Random runs (seed 24): 5000 programs of 2 to 10 words, random triggers and resets")
print(f"   cycles: {cyc}; configuration write accepted (chosen busy): {acc_cycles}")
print(f"   cycles where the chosen busy and (1b) accept the same configuration writes ([TOP-IF-8]): {acc_equal}")
print(f"   accepted cycles with an entry in S5, NOP slots left or loop_active = 1 ([TOP-HIER-6]): {s5_meets}")
print(f"   runs where every trigger outside reset made exactly one entry: {entries_ok} of {runs}")
print(f"   runs matching the closed form (1 for 4 cycles after the last slot, then NOP/loop state): {closed_ok} of {runs}")
print(f"   runs where (2b) differs from the chosen busy: {differ_2b}; largest shift of the last busy cycle: {max_shift} cycles")
if acc_equal != cyc or s5_meets or entries_ok != runs or closed_ok != runs or max_shift < 4:
    failures.append("random runs")

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all checks pass")
