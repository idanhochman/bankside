#!/usr/bin/env python3
"""Checks the top spec's figures against the yaml and the models.

  1. The instruction bitfields (img/instr_control.reg.json, instr_data,
     instr_alu) against bankside_isa.yaml: every named field at the yaml's
     bit range, every other bit an unnamed gap, 32 bits in all.
  2. The pipeline-occupancy rows of every timing diagram in img/ ("PC n ..."
     rows whose cells are S1 to S5, and NOP rows whose cells are "slot k"):
     the k-th slot of the program is the k-th cycle with trig_valid = 1
     ([TOP-IF-1]), and an instruction issued in cycle c is in S_i in cycle
     c + i - 1 ([TOP-PIPE-1]).
  3. Figure 3 of the theory of operation (img/mac_accumulator_bypass.wave.json)
     against hazard_trace.py's pipeline model for case D: the accumulator
     each MAC reads in S4 and every S5 write ([TOP-HAZ-2], [TOP-HAZ-4]).
  4. Figure 1 of interfaces.md (img/busy_rise_fall.wave.json): busy from the
     trigger sequence by [TOP-IF-7] (no NOP slots or loop in that program).
  5. Figure 2 of interfaces.md, before the first reset
     (img/first_reset.wave.json), against [TOP-IF-13]: the control outputs
     and the S5 write enables are x up to and including the first cycle with
     rst_n = 0 and their reset values after it; bank_rd_en is 0 in every
     cycle without a slot; a configuration write counts only from the first
     cycle after the first reset with busy = 0 and trig_valid = 0.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/figures_check.py
Exits non-zero if a check fails.
"""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
IMG = HERE.parent / "img"
ISA = yaml.safe_load((HERE.parent / "bankside_isa.yaml").read_text())
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def expand(sig):
    """One value per cycle: '.' repeats, '=' and digits take the next data."""
    data = list(sig.get("data", []))
    out, prev = [], None
    for ch in sig["wave"]:
        if ch == ".":
            out.append(prev)
            continue
        if ch == "=" or ch.isdigit() and ch not in "01":
            prev = data.pop(0)
        elif ch in "pP":
            prev = "clk"
        else:
            prev = ch
        out.append(prev)
    check(not data, f"{sig['name']}: {len(data)} data texts left over")
    return out


def wave(name):
    return json.loads((IMG / name).read_text())


# 1. Bitfields ---------------------------------------------------------------------
for fmt, spec in ISA["formats"].items():
    reg = wave(f"instr_{fmt}.reg.json")["reg"]
    bit, got = 0, {}
    for f in reg:
        if "name" in f:
            got[f["name"]] = [bit + f["bits"] - 1, bit]
        bit += f["bits"]
    check(bit == ISA["instruction_width"], f"instr_{fmt}: {bit} bits")
    check(got == spec["fields"], f"instr_{fmt}: {got} != yaml {spec['fields']}")
    print(f"ok   1 instr_{fmt}.reg.json: {len(got)} fields at the yaml's bits, the rest unnamed")


# 2. Pipeline rows -----------------------------------------------------------------
def rows_ok(name):
    sigs = [s for s in wave(name)["signal"] if isinstance(s, dict) and "wave" in s]
    trig = next(expand(s) for s in sigs if s["name"] == "trig_valid")
    slots = [t for t, v in enumerate(trig) if v == "1"]
    k, n = 0, 0
    for s in sigs:
        if not s["name"].startswith("PC "):
            continue
        cells = expand(s)
        stages = [(t, v) for t, v in enumerate(cells) if v not in ("x", None)]
        if stages and stages[0][1].startswith("slot"):
            for j, (t, v) in enumerate(stages):
                check(t == slots[k + j] and v == f"slot {j + 1}", f"{name}: {s['name']} cycle {t + 1}")
            k += len(stages)
        else:
            c = slots[k]
            for i, (t, v) in enumerate(stages):
                check(t == c + i and v.split()[0] == f"S{i + 1}", f"{name}: {s['name']} cycle {t + 1} = {v}")
            check(len(stages) == 5 or c + len(stages) == len(cells), f"{name}: {s['name']} stages")
            k += 1
        n += 1
    return n


for f in sorted(IMG.glob("*.wave.json")):
    if any(isinstance(s, dict) and s.get("name", "").startswith("PC ") for s in wave(f.name)["signal"]):
        n = rows_ok(f.name)
        print(f"ok   2 {f.name}: {n} rows, slots and stages where trig_valid puts them")

# 3. The accumulator bypass, case D -----------------------------------------------
out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        hz = runpy.run_path(str(HERE / "hazard_trace.py"))
except SystemExit as e:
    sys.exit(f"FAIL hazard_trace.py exited with {e.code}")
D = [("MOV", "GRF_B[2]", ["SRF_M[1]"]),
     ("MAC", "GRF_B[2]", ["GRF_A[1]", "SRF_M[0]"]),
     ("MAC", "GRF_B[2]", ["GRF_A[1]", "SRF_M[2]"])]
log = []
hz["pipeline"](D, hz["INIT"], [1, 1, 1], True, log)
acc, wr = {}, {}
for line in log:
    t = int(line.split()[1])
    for ev in line.split("  ", 2)[-1].split("; "):
        if " S4 reads GRF_B[2] = " in ev:
            acc[t] = ev.split(" = ")[1].split()[0]
        if " S5 writes GRF_B[2] <- " in ev:
            wr[t] = ev.split("<- ")[1]
fig = {s["name"]: expand(s) for s in wave("mac_accumulator_bypass.wave.json")["signal"]
       if isinstance(s, dict) and "wave" in s}
f_acc = {t + 1: v for t, v in enumerate(fig["grf_b port 2 (S4 accumulator)"]) if v != "x"}
f_wr = {t + 1: v for t, v in enumerate(fig["grf_b write (S5), GRF_B[2]"]) if v != "x"}
check(f_acc == acc, f"figure 3 accumulator {f_acc} != model {acc}")
check(f_wr == wr, f"figure 3 writes {f_wr} != model {wr}")
print(f"ok   3 mac_accumulator_bypass.wave.json: S4 reads {acc}, S5 writes {wr}, as hazard_trace.py's case D")

# 4. busy, case P -------------------------------------------------------------------
fig = {s["name"]: expand(s) for s in wave("busy_rise_fall.wave.json")["signal"]
       if isinstance(s, dict) and "wave" in s}
trig = fig["trig_valid"]
want = ["1" if any(trig[u] == "1" for u in range(max(0, t - 4), t)) else "0" for t in range(len(trig))]
check(fig["busy"] == want, f"figure busy_rise_fall: {fig['busy']} != {want}")
print("ok   4 busy_rise_fall.wave.json: busy = a slot in the 4 cycles before ([TOP-IF-7])")

# 5. Before the first reset ----------------------------------------------------------
fig = {s["name"]: expand(s) for s in wave("first_reset.wave.json")["signal"]
       if isinstance(s, dict) and "wave" in s}
rst, trig, busy = fig["rst_n"], fig["trig_valid"], fig["busy"]
first = rst.index("0")                     # the first reset cycle (0-based)
for name in ("busy", "err_illegal", "bank_wr_en", "grf_*_wr_en, srf_*_wr_en (dp)"):
    v = fig[name]
    check(all(x == "x" for x in v[:first + 1]), f"first_reset: {name} defined before the reset ends")
    check(all(x != "x" for x in v[first + 1:]), f"first_reset: {name} undefined after the reset")
check(busy[first + 1:] == [("1" if any(trig[u] == "1" and rst[u] == "1" for u in range(max(first + 1, t - 4), t))
                            else "0") for t in range(first + 1, len(rst))], "first_reset: busy after the reset")
check(all(fig["bank_rd_en"][t] == "0" for t in range(len(rst)) if not (trig[t] == "1" and rst[t] == "1")),
      "first_reset: bank_rd_en without a slot")
cfg = fig["a cfg_wr_en = 1 would take effect"]
check(all(x == "x" for x in cfg[:first + 1]), "first_reset: cfg before the reset")
check(cfg[first + 1:] == [("1" if busy[t] == "0" and trig[t] == "0" else "0") for t in range(first + 1, len(rst))],
      "first_reset: cfg gate")
print(f"ok   5 first_reset.wave.json: undefined through cycle {first + 1}, the first with rst_n = 0; "
      "reset values after it ([TOP-IF-13])")

if failures:
    print("\nFAIL:", *failures[:30], sep="\n  ")
    sys.exit(1)
print("\nok   all figures match")
