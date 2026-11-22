#!/usr/bin/env python3
"""Register-file and bank hazards traced cycle by cycle.

Backs "Hazards" and "Bank access" in ../theory_of_operation.md:
[TOP-HAZ-1] (write-through), [TOP-HAZ-3] (distance 3 for S2 sources),
[TOP-HAZ-4] (the MAC accumulator, read in S4, needs no distance),
[TOP-HAZ-5] (what a read that breaks [TOP-HAZ-3] returns), [TOP-PIPE-1]
(every write in S5), [TOP-IF-2] and [TOP-IF-3] (the v1 bank), [TOP-HAZ-6]
(distance 4 from a bank store to a read of its column) and [TOP-HAZ-7]
(what a bank read that breaks [TOP-HAZ-6] returns).

The model keeps only what decides which value a read sees: one trigger per
cycle or a bubble ([TOP-PIPE-2]); an instruction issued in cycle t requests
its bank source in S1 (t), which the bank samples at the end of t, gets the
bank data and reads its register sources in S2 (t+1), a MAC reads its
accumulator in S4 (t+3), and every write, a bank store included, is in S5
(t+4) ([TOP-PIPE-1]). NOP n takes n slots and reads and writes nothing; it
isn't sent down S2 to S5 here (it travels as a slot, [TOP-IF-7], but can't
change a value). A register file is combinational on read, writes at the
end of the cycle, and, with write-through, a read of the entry written in
the same cycle returns the written value. The bank applies a store and a
read sampled on the same edge write first (chosen) or read first. A bank
column is named "EVEN_BANK@3": the column of the trigger of the instruction
that names it, one row throughout. Values are lane 0 only, FP16-exact.

  1. The toy programs of the theory of operation, traced cycle by cycle.
  2. A distance sweep k = 1..4 for an S2 source and for the accumulator, with
     and without write-through: the smallest safe k is the [TOP-HAZ-3] limit.
  3. 20000 random programs with random bubbles: every program that keeps
     [TOP-HAZ-3] matches in-order execution under write-through, and every
     S2 read (legal or not) returns what [TOP-HAZ-5] says: the newest write
     to that entry whose S5 cycle is the read's cycle or earlier.
  4. The bank: store-then-load at the [TOP-HAZ-6] limit (case E), a broken
     rule with an older store in flight (F) and with a bubble (G), the bank
     distance sweep k = 1..6 (write-first 4, read-first 5), and 20000 random
     programs with loads and stores: every program keeping [TOP-HAZ-3] and
     [TOP-HAZ-6] matches in-order execution, and every bank read returns
     what [TOP-HAZ-7] says.
  5. [TOP-PIPE-1] against ANEMOS's early writes (a MOV from a register and a
     bank store written in the decode cycle): a write-after-write case that
     ends out of order (H) and two writes to one file in one cycle (I).

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


def is_bank(entry):
    """A bank column, written "EVEN_BANK@3": the column of the instruction's
    own triggering command ([TOP-ARCH-6], [TOP-ARCH-8]); one row throughout."""
    return "BANK" in entry


def pipeline(program, init, triggers, write_through=True, log=None,
             bank_write_first=True, early=None):
    """Cycle-level run. Returns (registers and bank columns, list of S2 reads
    as (instruction index, entry, cycle, value), issue cycles, list of bank
    reads as (instruction index, column, cycle, value)).

    A bank source is requested in S1 (cycle c) and sampled by the bank at the
    end of that cycle ([TOP-IF-2]); a bank store is written at the end of its
    S5 cycle ([TOP-IF-3]). bank_write_first: a store and a read on the same
    edge give the read the stored data (the v1 bank, chosen); otherwise the
    read gets the data from before the store.

    early(ins) True: the instruction reads its sources and writes its
    destination in its S1 cycle, as ANEMOS does for MOV from a register and
    for bank stores (the R9 alternative); every other write stays in S5."""
    issue = schedule(program, triggers)
    regs = dict(init)
    results, s2vals, s1vals, s2log, banklog = {}, {}, {}, [], []
    wcyc = {i: (c if early and early(program[i]) else c + 4)
            for i, c in enumerate(issue) if c is not None}
    last = max(c for c in issue if c is not None) + 4
    for t in range(1, last + 1):
        writes = [i for i in sorted(wcyc) if wcyc[i] == t]

        def read(entry, through_ok):
            # the newest write of this cycle whose value is already known
            for i in reversed(writes):
                if program[i][1] == entry and i in results and through_ok:
                    return results[i], True
            return regs[entry], False

        events = []
        for i, c in enumerate(issue):
            if c is None:
                continue
            op, dst, srcs = program[i]
            if c == t:                  # S1: bank read request
                for s in srcs:
                    if is_bank(s):
                        v, through = read(s, bank_write_first)
                        s1vals[(i, s)] = v
                        banklog.append((i, s, t, v))
                        events.append(f"PC {i} S1 bank read {s} = {v}" + (" (store of this edge)" if through else ""))
                if early and early(program[i]):
                    vals = [s1vals[(i, s)] if is_bank(s) else regs[s] for s in srcs]
                    results[i] = compute(op, vals)
                    events.append(f"PC {i} S1 reads " + ", ".join(srcs) + f" (early write)")
        for i, c in enumerate(issue):
            if c is None or (early and early(program[i])):
                continue
            op, dst, srcs = program[i]
            if c + 1 == t:              # S2: sources
                vals = []
                for s in srcs:
                    if is_bank(s):
                        v = s1vals[(i, s)]
                        vals.append(v)
                        events.append(f"PC {i} S2 bank_rd_data {s} = {v}")
                        continue
                    v, through = read(s, write_through)
                    vals.append(v)
                    s2log.append((i, s, t, v))
                    events.append(f"PC {i} S2 reads {s} = {v}" + (" (write-through)" if through else ""))
                s2vals[i] = vals
                if op != "MAC":
                    results[i] = compute(op, vals)
            if op == "MAC" and c + 3 == t:   # S4: accumulator
                acc, through = read(dst, write_through)
                results[i] = compute(op, s2vals[i], acc)
                events.append(f"PC {i} S4 reads {dst} = {acc}" + (" (write-through)" if through else "")
                              + f"; result {results[i]}")
        for i in writes:                # in program order: the newest wins
            stage = "S1" if early and early(program[i]) and wcyc[i] == issue[i] else "S5"
            events.append(f"PC {i} {stage} writes {program[i][1]} <- {results[i]}")
            regs[program[i][1]] = results[i]
        if log is not None:
            trig = "trigger" if t <= len(triggers) and triggers[t - 1] else "bubble "
            log.append(f"    cycle {t:2} {trig}  " + ("; ".join(events) if events else "-"))
    return regs, s2log, issue, banklog


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
        regs, _, _, _ = pipeline(program, init, triggers, wt, log)
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
    regs, s2log, issue, _ = pipeline(prog, init, trig, True)
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

# 4. Bank columns ([TOP-IF-2], [TOP-IF-3], [TOP-HAZ-6], [TOP-HAZ-7]) -----------------
# A bank column is named "EVEN_BANK@3": the column of the trigger of the
# instruction that names it. One row throughout.
def rule_violations(program, bank_dist=4):
    """[TOP-HAZ-3] (GRF/SRF sources, 3 slots) and [TOP-HAZ-6] (bank columns,
    bank_dist slots), counted in slots. Returns (haz3, haz6) violations."""
    slot, start = 0, []
    for ins in program:
        start.append(slot)
        slot += max(ins[1], 1) if ins[0] == "NOP" else 1
    h3, h6 = [], []
    for j, cj in enumerate(program):
        if cj[0] == "NOP":
            continue
        for i in range(j):
            pi = program[i]
            if pi[0] == "NOP" or pi[1] not in cj[2]:
                continue
            k = start[j] - start[i]
            if is_bank(pi[1]):
                if k < bank_dist:
                    h6.append((i, j))
            elif k < 3:
                h3.append((i, j))
    return h3, h6


def bank_text(ins):
    t = text(ins).replace("@", " col ")
    return t


BINIT = {"GRF_A[0]": 0.125, "GRF_A[1]": 0.5, "GRF_A[2]": 0.25, "SRF_M[1]": 2.0, "EVEN_BANK@3": 0.75}


def btrace(title, program, triggers, init=BINIT):
    print(title)
    for pc, ins in enumerate(program):
        print(f"    PC {pc}  {bank_text(ins)}")
    print("    initial: " + ", ".join(f"{k.replace('@', ' col ')} = {v}" for k, v in init.items()))
    out = {}
    for wf in (True, False):
        log = []
        regs, _, _, _ = pipeline(program, init, triggers, True, log, bank_write_first=wf)
        print(f"  bank {'write-first (chosen)' if wf else 'read-first'}:")
        print("\n".join(log).replace("@", " col "))
        out[wf] = regs
    return out, in_order(program, init)


print("4. Bank columns: store in S5, read requested in S1 and sampled at the end of that cycle\n")
E = [("MOV", "EVEN_BANK@3", ["GRF_A[1]"]),
     ("NOP", 3),
     ("MOV", "GRF_A[0]", ["EVEN_BANK@3"])]
out, ref = btrace("Case E: store then load of the same column, k = 4 slots ([TOP-HAZ-6] at its limit)", E, [1] * 5)
print(f"  GRF_A[0]: in order {ref['GRF_A[0]']}, write-first {out[True]['GRF_A[0]']},"
      f" read-first {out[False]['GRF_A[0]']}\n")
if out[True]["GRF_A[0]"] != ref["GRF_A[0]"] or out[False]["GRF_A[0]"] == ref["GRF_A[0]"]:
    failures.append("case E")

F = [("MOV", "EVEN_BANK@3", ["GRF_A[1]"]),
     ("MOV", "EVEN_BANK@3", ["GRF_A[2]"]),
     ("NOP", 2),
     ("MOV", "GRF_A[0]", ["EVEN_BANK@3"])]
out, ref = btrace("Case F: [TOP-HAZ-6] broken (k = 3 from PC 1), an older store (PC 0) in flight", F, [1] * 5)
print(f"  GRF_A[0]: in order {ref['GRF_A[0]']}, write-first {out[True]['GRF_A[0]']}"
      f" (PC 0's 0.5, not the 0.75 held before the program)\n")
if out[True]["GRF_A[0]"] != 0.5:
    failures.append("case F")

out, ref = btrace("Case G: program F with a bubble after PC 1 (k = 3 slots but 4 cycles)", F, [1, 1, 0, 1, 1, 1])
print(f"  GRF_A[0]: in order {ref['GRF_A[0]']}, write-first {out[True]['GRF_A[0]']}"
      " (the read meets PC 1's store: rule broken in slots, result still in order)\n")
if out[True]["GRF_A[0]"] != 0.25:
    failures.append("case G")

print("   Bank distance sweep: MOV EVEN_BANK col 3, GRF_A[1] ... MOV GRF_A[0], EVEN_BANK col 3"
      " (NOP k-1 between), no bubbles")
print("   k   write-first (chosen)   read-first")
bank_ok = {}
for k in range(1, 7):
    gap = [("NOP", k - 1)] if k > 1 else []
    prog = [("MOV", "EVEN_BANK@3", ["GRF_A[1]"])] + gap + [("MOV", "GRF_A[0]", ["EVEN_BANK@3"])]
    ref = in_order(prog, BINIT)["GRF_A[0]"]
    row = []
    for wf in (True, False):
        got = pipeline(prog, BINIT, [1] * 10, True, bank_write_first=wf)[0]["GRF_A[0]"]
        bank_ok[(wf, k)] = got == ref
        row.append(f"{got:5} {'ok ' if got == ref else 'old'}")
    print(f"   {k}   {row[0]:>9}              {row[1]:>9}")
bank_min = {wf: [k for k in range(1, 7) if all(bank_ok[(wf, j)] for j in range(k, 7))][0] for wf in (True, False)}
print(f"   smallest safe k: {bank_min[True]} (write-first), {bank_min[False]} (read-first)\n")
if bank_min != {True: 4, False: 5}:
    failures.append(f"bank sweep: {bank_min}")

# Timing only, as in section 3: the random pairs don't keep the yaml legal
# lists (a store from GRF_B to EVEN_BANK, say), since the pairing doesn't
# change when a column is read or written.
BREGS = ["GRF_A[0]", "GRF_A[1]", "GRF_B[0]", "SRF_M[0]"]
BCOLS = ["EVEN_BANK@0", "EVEN_BANK@1", "ODD_BANK@0"]
BGRF = ["GRF_A[0]", "GRF_A[1]", "GRF_B[0]"]


def random_bank_program(rng, n):
    prog = []
    for _ in range(n):
        op = rng.choice(["LD", "ST", "ST", "ADD", "MOV", "NOP"])
        if op == "NOP":
            prog.append(("NOP", rng.randint(0, 4)))
        elif op == "LD":
            prog.append(("MOV", rng.choice(BGRF), [rng.choice(BCOLS)]))
        elif op == "ST":
            prog.append(("MOV", rng.choice(BCOLS), [rng.choice(BGRF)]))
        elif op == "ADD":
            prog.append(("ADD", rng.choice(BGRF), [rng.choice(BCOLS), rng.choice(BREGS)]))
        else:
            prog.append(("MOV", rng.choice(BGRF), [rng.choice(BREGS)]))
    if not any(ins[0] != "NOP" for ins in prog):
        prog.append(("MOV", "EVEN_BANK@0", ["GRF_A[0]"]))
    return prog


rng = random.Random(10)
b_legal = b_legal_ok = b_legal_rf_ok = b_broken = b_broken_differ = b_reads = b_reads_ok = b_reads_old = 0
for _ in range(20000):
    prog = random_bank_program(rng, rng.randint(2, 8))
    init = {e: rng.choice(VALUES) for e in BREGS + BCOLS}
    trig = [rng.choice([1, 1, 1, 0]) for _ in range(60)]
    trig[0] = 1
    need = sum(max(i[1], 1) if i[0] == "NOP" else 1 for i in prog)
    if sum(trig) < need:
        trig += [1] * need
    regs, _, issue, banklog = pipeline(prog, init, trig, True)
    slot_of, n = [], 0
    for ins in prog:
        slot_of.append(n)
        n += max(ins[1], 1) if ins[0] == "NOP" else 1
    # [TOP-HAZ-6] checked on every bank read: the newest store to the column
    # whose S5 cycle is the read's S1 cycle or earlier, else the earlier contents.
    stores = sorted((issue[i] + 4, prog[i][1], i) for i in range(len(prog))
                    if issue[i] is not None and is_bank(prog[i][1]))
    stored = {i: pipeline(prog[: i + 1], init, trig, True)[0][col] for (_, col, i) in stores}
    for (j, col, t, v) in banklog:
        newest = [s for s in stores if s[1] == col and s[0] <= t]
        expect = stored[newest[-1][2]] if newest else init[col]
        b_reads += 1
        b_reads_ok += expect == v
        # draft 0.1's "old data", read in slots: the newest store to the
        # column issued 4 or more slots before the read, else the earlier
        # contents (what the read gets if no store breaks the rule against it)
        done = [s for s in stores if s[1] == col and slot_of[j] - slot_of[s[2]] >= 4]
        old = stored[done[-1][2]] if done else init[col]
        b_reads_old += old == v
    h3, h6 = rule_violations(prog)
    if not h3 and not h6:
        b_legal += 1
        b_legal_ok += regs == in_order(prog, init)
        b_legal_rf_ok += pipeline(prog, init, trig, True, bank_write_first=False)[0] == in_order(prog, init)
    elif h6 and not h3:
        b_broken += 1
        b_broken_differ += regs != in_order(prog, init)

print("   Random programs with bank loads and stores (seed 10), random bubbles")
print(f"   programs keeping [TOP-HAZ-3] and [TOP-HAZ-6]: {b_legal}; equal to in-order execution: {b_legal_ok}")
print(f"   the same programs with a read-first bank: equal to in-order: {b_legal_rf_ok}")
print(f"   programs breaking only [TOP-HAZ-6]: {b_broken}; of them differing from in-order: {b_broken_differ}")
print(f"   bank reads checked against [TOP-HAZ-7] (newest store with S5 cycle <= read's S1 cycle): "
      f"{b_reads}; matching: {b_reads_ok}")
print(f"   the same reads against draft 0.1's 'old data' (newest store 4 or more slots earlier): "
      f"matching {b_reads_old}\n")
if b_legal_ok != b_legal or b_reads_ok != b_reads or b_legal_rf_ok == b_legal or b_reads_old == b_reads:
    failures.append("random bank programs")

# 5. R9: every write in S5, against ANEMOS's early writes ----------------------------
print("5. [TOP-PIPE-1]: every write in S5, against writing MOV and bank stores in S1 (ANEMOS)\n")


def anemos_early(ins):
    """ANEMOS writes a MOV whose source is not a bank, and a bank store, in its
    decode cycle (instr_decoder.cpp: grfa_wr_en_comb, even_out_en); bank loads
    and arithmetic go through its write pipe."""
    return ins[0] == "MOV" and not is_bank(ins[2][0])


def r9_case(title, prog, entry, init=BINIT):
    print(title)
    for pc, ins in enumerate(prog):
        print(f"    PC {pc}  {bank_text(ins)}")
    ref = in_order(prog, init)[entry]
    s5 = pipeline(prog, init, [1] * 10, True)[0][entry]
    log = []
    early = pipeline(prog, init, [1] * 10, False, log, early=anemos_early)[0][entry]
    issue = schedule(prog, [1] * 10)
    wc = {}
    for i, c in enumerate(issue):
        if c is not None:
            w = c if anemos_early(prog[i]) else c + 4
            f = prog[i][1].split("[")[0].split("@")[0]
            wc.setdefault((f, w), []).append(i)
    two = {k: v for k, v in wc.items() if len(v) > 1}
    print("  early writes (S1 for MOV and bank stores):")
    print("\n".join(log).replace("@", " col "))
    print(f"  {entry.replace('@', ' col ')}: in order {ref}, all writes in S5 {s5}, early writes {early}"
          + (f"; two writes to {', '.join(f'{f} in cycle {w}' for (f, w) in two)}" if two else ""))
    print()
    return ref, s5, early, two


ref, s5, early, _ = r9_case("Case H: a MOV right after an ADD to the same entry (write after write)",
                            [("ADD", "GRF_A[0]", ["GRF_A[1]", "GRF_A[1]"]),
                             ("MOV", "GRF_A[0]", ["SRF_M[1]"])], "GRF_A[0]")
if not (s5 == ref != early):
    failures.append("case H")
ref, s5, early, two = r9_case("Case I: a MOV 4 slots after an ADD to the same file (one write port)",
                              [("ADD", "GRF_A[0]", ["GRF_A[1]", "GRF_A[1]"]),
                               ("NOP", 3),
                               ("MOV", "GRF_A[1]", ["SRF_M[1]"])], "GRF_A[1]")
if not two:
    failures.append("case I")

if failures:
    print("\nFAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("\nok   all checks pass")
