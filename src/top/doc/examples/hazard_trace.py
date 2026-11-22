#!/usr/bin/env python3
"""Register-file hazards traced cycle by cycle, with and without write-through.

Backs "Hazards" in ../theory_of_operation.md: [TOP-HAZ-1] (write-through),
[TOP-HAZ-3] (distance 3 for S2 sources), [TOP-HAZ-4] (the MAC accumulator,
read in S4, needs no distance) and [TOP-HAZ-5] (what a read that breaks
[TOP-HAZ-3] returns).

The model keeps only what decides which value a read sees: one trigger per
cycle or a bubble ([TOP-PIPE-2]); an instruction issued in cycle t reads its
sources in S2 (t+1), a MAC reads its accumulator in S4 (t+3), and every
write is in S5 (t+4) ([TOP-PIPE-1]). NOP n takes n slots and reads and
writes nothing; it isn't sent down S2 to S5 here (whether it travels is #24,
and it can't change a register value either way). A register file is
combinational on read, writes at the end of the cycle, and, with
write-through, a read of the entry written in the same cycle returns the
written value. Values are lane 0 only, FP16-exact.

  1. The toy programs of the theory of operation, traced cycle by cycle.
  2. A distance sweep k = 1..4 for an S2 source and for the accumulator, with
     and without write-through: the smallest safe k is the [TOP-HAZ-3] limit.
  3. 20000 random programs with random bubbles: every program that keeps
     [TOP-HAZ-3] matches in-order execution under write-through, and every
     S2 read (legal or not) returns what [TOP-HAZ-5] says: the newest write
     to that entry whose S5 cycle is the read's cycle or earlier.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/hazard_trace.py
Exits non-zero if any check fails.
"""
import random
import struct
import sys

failures = []


def f16(x):
    return struct.unpack("<e", struct.pack("<e", x))[0]


# Instructions: (op, dst, srcs) with dst and srcs as "GRF_A[1]"-style names.
#   MOV dst, src         dst <- src
#   ADD dst, a, b        dst <- a + b
#   MUL dst, a, b        dst <- a * b
#   MAC dst, a, b        dst <- dst + a * b   (dst read in S4, [TOP-HAZ-2])
#   NOP n
def text(ins):
    if ins[0] == "NOP":
        return f"NOP {ins[1]}"
    return f"{ins[0]} {ins[1]}, " + ", ".join(ins[2])


def compute(op, srcs, acc=None):
    if op == "MOV":
        return srcs[0]
    if op == "ADD":
        return f16(srcs[0] + srcs[1])
    if op == "MUL":
        return f16(srcs[0] * srcs[1])
    if op == "MAC":
        return f16(acc + f16(srcs[0] * srcs[1]))
    raise ValueError(op)


def in_order(program, init):
    """One instruction at a time, no pipeline: what the program means."""
    regs = dict(init)
    for ins in program:
        if ins[0] == "NOP":
            continue
        op, dst, srcs = ins
        regs[dst] = compute(op, [regs[s] for s in srcs], regs[dst] if op == "MAC" else None)
    return regs


def schedule(program, triggers):
    """Issue cycle of each instruction (None for NOPs), given the trigger
    pattern: triggers[i] is 1 if cycle i+1 has trig_valid = 1."""
    issue, slot_of = [], []
    cyc = (i + 1 for i, t in enumerate(triggers) if t)
    for ins in program:
        n = max(ins[1], 1) if ins[0] == "NOP" else 1
        cycles = [next(cyc) for _ in range(n)]
        issue.append(None if ins[0] == "NOP" else cycles[0])
    return issue


def pipeline(program, init, triggers, write_through=True, log=None):
    """Cycle-level run. Returns (registers, list of S2 reads as
    (instruction index, entry, cycle, value))."""
    issue = schedule(program, triggers)
    regs = dict(init)
    results, s2vals, s2log = {}, {}, []
    last = max(c for c in issue if c is not None) + 4
    for t in range(1, last + 1):
        wr = None                       # the S5 write of this cycle
        for i, c in enumerate(issue):
            if c is not None and c + 4 == t:
                wr = (program[i][1], results[i], i)

        def read(entry):
            if write_through and wr and wr[0] == entry:
                return wr[1], True
            return regs[entry], False

        events = []
        for i, c in enumerate(issue):
            if c is None:
                continue
            op, dst, srcs = program[i]
            if c + 1 == t:              # S2: sources
                vals = []
                for s in srcs:
                    v, through = read(s)
                    vals.append(v)
                    s2log.append((i, s, t, v))
                    events.append(f"PC {i} S2 reads {s} = {v}" + (" (write-through)" if through else ""))
                s2vals[i] = vals
                if op != "MAC":
                    results[i] = compute(op, vals)
            if op == "MAC" and c + 3 == t:   # S4: accumulator
                acc, through = read(dst)
                results[i] = compute(op, s2vals[i], acc)
                events.append(f"PC {i} S4 reads {dst} = {acc}" + (" (write-through)" if through else "")
                              + f"; result {results[i]}")
        if wr:
            events.append(f"PC {wr[2]} S5 writes {wr[0]} <- {wr[1]}")
            regs[wr[0]] = wr[1]
        if log is not None:
            trig = "trigger" if t <= len(triggers) and triggers[t - 1] else "bubble "
            log.append(f"    cycle {t:2} {trig}  " + ("; ".join(events) if events else "-"))
    return regs, s2log, issue


def haz3_ok(program):
    """[TOP-HAZ-3], counted in slots: no S2 source written by an instruction
    issued fewer than 3 slots earlier. Returns the violations."""
    slot, start = 0, []
    for ins in program:
        start.append(slot)
        slot += max(ins[1], 1) if ins[0] == "NOP" else 1
    bad = []
    for j, cj in enumerate(program):
        if cj[0] == "NOP":
            continue
        for i in range(j):
            pi = program[i]
            if pi[0] != "NOP" and pi[1] in cj[2] and start[j] - start[i] < 3:
                bad.append((i, j))
    return bad


INIT = {"GRF_A[1]": 0.5, "GRF_B[2]": 0.25, "SRF_M[0]": 1.0, "SRF_M[1]": 2.0, "SRF_M[2]": 3.0}


def trace(title, program, triggers, init=INIT):
    print(title)
    for pc, ins in enumerate(program):
        print(f"    PC {pc}  {text(ins)}")
    print("    initial: " + ", ".join(f"{k} = {v}" for k, v in init.items()))
    out = {}
    for wt in (True, False):
        log = []
        regs, _, _ = pipeline(program, init, triggers, wt, log)
        print(f"  write-through {'on (chosen)' if wt else 'off'}:")
        print("\n".join(log))
        out[wt] = regs
    ref = in_order(program, init)
    return out, ref


# 1. Toy programs -----------------------------------------------------------------
print("1. Toy programs, traced (one trigger per cycle unless marked)\n")

A = [("MOV", "GRF_A[1]", ["SRF_M[1]"]),
     ("NOP", 2),
     ("ADD", "GRF_B[2]", ["GRF_A[1]", "GRF_A[1]"])]
out, ref = trace("Case A: [TOP-HAZ-3] at its limit, k = 3 slots", A, [1] * 4)
print(f"  GRF_B[2]: in order {ref['GRF_B[2]']}, write-through {out[True]['GRF_B[2]']},"
      f" no write-through {out[False]['GRF_B[2]']}\n")
if out[True]["GRF_B[2]"] != ref["GRF_B[2]"] or out[False]["GRF_B[2]"] == ref["GRF_B[2]"]:
    failures.append("case A")

B = [("MOV", "GRF_A[1]", ["SRF_M[0]"]),
     ("MOV", "GRF_A[1]", ["SRF_M[1]"]),
     ("NOP", 1),
     ("ADD", "GRF_B[2]", ["GRF_A[1]", "GRF_A[1]"])]
out, ref = trace("Case B: [TOP-HAZ-3] broken (k = 2 from PC 1), an older write (PC 0) in flight", B, [1] * 5)
print(f"  GRF_B[2]: in order {ref['GRF_B[2]']}, write-through {out[True]['GRF_B[2]']}"
      f" (reads PC 0's 1.0, not the 0.5 held before the program)\n")
if out[True]["GRF_B[2]"] != 2.0:
    failures.append("case B")

out, ref = trace("Case C: program B with a bubble after PC 1 (k = 2 slots but 3 cycles)", B, [1, 1, 0, 1, 1])
print(f"  GRF_B[2]: in order {ref['GRF_B[2]']}, write-through {out[True]['GRF_B[2]']}"
      " (the read meets PC 1's write: rule broken in slots, result still in order)\n")
if out[True]["GRF_B[2]"] != 4.0:
    failures.append("case C")

D = [("MOV", "GRF_B[2]", ["SRF_M[1]"]),
     ("MAC", "GRF_B[2]", ["GRF_A[1]", "SRF_M[0]"]),
     ("MAC", "GRF_B[2]", ["GRF_A[1]", "SRF_M[2]"])]
out, ref = trace("Case D: [TOP-HAZ-4], MACs right after the producer of their accumulator", D, [1] * 3)
print(f"  GRF_B[2]: in order {ref['GRF_B[2]']}, write-through {out[True]['GRF_B[2]']},"
      f" no write-through {out[False]['GRF_B[2]']}\n")
if out[True]["GRF_B[2]"] != ref["GRF_B[2]"] or out[False]["GRF_B[2]"] == ref["GRF_B[2]"]:
    failures.append("case D")

# 2. Distance sweep ----------------------------------------------------------------
print("2. Distance sweep: consumer k slots after the producer (NOP k-1 between), no bubbles")
print("   S2 source:   MOV GRF_A[1], SRF_M[1] ... ADD GRF_B[2], GRF_A[1], GRF_A[1]")
print("   accumulator: MOV GRF_B[2], SRF_M[1] ... MAC GRF_B[2], GRF_A[1], SRF_M[2]")
print("   k   S2 source (result in GRF_B[2])       MAC accumulator (result in GRF_B[2])")
print("       write-through   no write-through     write-through   no write-through")
ok_at = {}
for k in range(1, 5):
    gap = [("NOP", k - 1)] if k > 1 else []
    src = [("MOV", "GRF_A[1]", ["SRF_M[1]"])] + gap + [("ADD", "GRF_B[2]", ["GRF_A[1]", "GRF_A[1]"])]
    acc = [("MOV", "GRF_B[2]", ["SRF_M[1]"])] + gap + [("MAC", "GRF_B[2]", ["GRF_A[1]", "SRF_M[2]"])]
    row = []
    for prog, key in ((src, "src"), (acc, "acc")):
        ref = in_order(prog, INIT)["GRF_B[2]"]
        for wt in (True, False):
            got = pipeline(prog, INIT, [1] * 8, wt)[0]["GRF_B[2]"]
            ok = got == ref
            row.append(f"{got:5} {'ok ' if ok else 'old'}")
            ok_at[(key, wt, k)] = ok
    print(f"   {k}   {row[0]:>9}       {row[1]:>9}            {row[2]:>9}       {row[3]:>9}")
# smallest k from which every larger k in the sweep is safe
min_k = {}
for key in ("src", "acc"):
    for wt in (True, False):
        safe = [k for k in range(1, 5) if all(ok_at[(key, wt, j)] for j in range(k, 5))]
        min_k[(key, wt)] = safe[0] if safe else None
print(f"   smallest safe k: S2 source {min_k.get(('src', True))} (write-through),"
      f" {min_k.get(('src', False))} (without); accumulator {min_k.get(('acc', True))} (write-through),"
      f" {min_k.get(('acc', False))} (without)\n")
if min_k.get(("src", True)) != 3 or min_k.get(("src", False)) != 4 or min_k.get(("acc", True)) != 1:
    failures.append(f"sweep: {min_k}")

# 3. Random programs ---
# Timing only: the operand combinations don't keep the yaml legal lists, since
# which sources an instruction may take doesn't change when it reads them.------------------------------------------------------------
ENTRIES = ["GRF_A[0]", "GRF_A[1]", "GRF_B[0]", "GRF_B[1]", "SRF_M[0]", "SRF_A[0]"]
GRFS = [e for e in ENTRIES if e.startswith("GRF")]
VALUES = [0.5, 1.0, 1.5, 2.0, -1.0, 0.25]


def random_program(rng, n):
    prog = []
    for _ in range(n):
        op = rng.choice(["MOV", "ADD", "MUL", "MAC", "NOP"])
        if op == "NOP":
            prog.append(("NOP", rng.randint(0, 3)))
        elif op == "MOV":
            prog.append(("MOV", rng.choice(ENTRIES), [rng.choice(ENTRIES)]))
        elif op == "MAC":
            prog.append(("MAC", rng.choice([e for e in GRFS if e.startswith("GRF_B")]),
                         [rng.choice(ENTRIES), rng.choice(ENTRIES)]))
        else:
            prog.append((op, rng.choice(GRFS), [rng.choice(ENTRIES), rng.choice(ENTRIES)]))
    if all(i[0] == "NOP" for i in prog):
        prog.append(("MOV", "GRF_A[0]", ["SRF_M[0]"]))
    return prog


rng = random.Random(8)
legal_runs = legal_ok = legal_ok_nowt = broken_runs = haz5_reads = haz5_ok = broken_differ = 0
for _ in range(20000):
    prog = random_program(rng, rng.randint(2, 8))
    init = {e: rng.choice(VALUES) for e in ENTRIES}
    trig = [rng.choice([1, 1, 1, 0]) for _ in range(60)]
    trig[0] = 1
    need = sum(max(i[1], 1) if i[0] == "NOP" else 1 for i in prog)
    if sum(trig) < need:
        trig += [1] * need
    regs, s2log, issue = pipeline(prog, init, trig, True)
    # [TOP-HAZ-5] checked on every S2 read: replay the S5 writes in cycle order.
    writes = sorted((issue[i] + 4, prog[i][1], i) for i in range(len(prog)) if issue[i] is not None)
    # The value each instruction wrote: its entry after a run of the program
    # cut after it (it is that entry's last write in the cut program).
    written = {}
    for (cyc, entry, i) in writes:
        written[i] = pipeline(prog[: i + 1], init, trig, True)[0][entry]
    for (j, entry, t, v) in s2log:
        newest = [w for w in writes if w[1] == entry and w[0] <= t]
        expect = written[newest[-1][2]] if newest else init[entry]
        haz5_reads += 1
        haz5_ok += expect == v
    if not haz3_ok(prog):
        legal_runs += 1
        legal_ok += regs == in_order(prog, init)
        legal_ok_nowt += pipeline(prog, init, trig, False)[0] == in_order(prog, init)
    else:
        broken_runs += 1
        broken_differ += regs != in_order(prog, init)

print("3. Random programs (seed 8) with random bubbles, write-through on")
print(f"   programs keeping [TOP-HAZ-3]: {legal_runs}; equal to in-order execution: {legal_ok}")
print(f"   the same programs without write-through: equal to in-order: {legal_ok_nowt}")
print(f"   programs breaking [TOP-HAZ-3]: {broken_runs}; of them differing from in-order: {broken_differ}")
print(f"   S2 reads checked against [TOP-HAZ-5] (newest write with S5 cycle <= read cycle): "
      f"{haz5_reads}; matching: {haz5_ok}")
if legal_ok != legal_runs or haz5_ok != haz5_reads or legal_ok_nowt == legal_runs:
    failures.append("random programs")

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all checks pass")
