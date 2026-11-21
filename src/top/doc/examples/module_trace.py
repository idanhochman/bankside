#!/usr/bin/env python3
"""A toy program traced through the v1 module split, cycle by cycle.

Backs the worked case in ../hierarchy.md ("Worked case: the GEMV pattern
through the modules"). The model follows the split of [TOP-HIER-2] to
[TOP-HIER-5]:

  pcu_ctrl      S1: fetch from the CRF, decode, bank read request; owns the
                S1/S2 register.
  pcu_datapath  S2 to S5: source reads, S3 multiply, S4 add and the MAC
                accumulator read, S5 write-back; owns S2/S3, S3/S4, S4/S5.
  pcu_regfile   combinational read, write at the clock edge, write-through
                on every read port ([TOP-HAZ-1], [TOP-HIER-4]).

The accumulator bypass [TOP-HAZ-2] is GRF_B's write-through on its S4 read
port ([TOP-HIER-5]). The script runs the program three ways and compares the
bank write and GRF_B[0] with an in-order reference (one instruction at a time,
no pipeline):

  (a) write-through on the accumulator port, no datapath mux (chosen);
  (b) no write-through on that port, a bypass mux in pcu_datapath instead;
  (c) neither, to show the case the bypass exists for.

FP16 rounding uses struct's binary16 ('e'), which rounds to nearest even;
one double-precision operation rounded once to FP16 is correctly rounded
([TOP-FP-2]), and MAC is unfused ([TOP-FP-3]).

Run from the repo root:
    .venv/bin/python src/top/doc/examples/module_trace.py
Exits non-zero if (a) or (b) disagree with the reference, or (c) agrees.
"""
import struct
import sys

LANES = 16


def f16(x):
    return struct.unpack("<e", struct.pack("<e", x))[0]


# The program: the GEMV pattern of the programmer's guide, cut to two MACs.
PROGRAM = [
    ("MOV", "GRF_B", 0, "ODD_BANK", None, None),          # PC 0  load partial sums
    ("MAC", "GRF_B", 0, "EVEN_BANK", None, ("SRF_M", 0)),  # PC 1
    ("MAC", "GRF_B", 0, "ODD_BANK", None, ("SRF_M", 1)),   # PC 2
    ("NOP", 2),                                            # PC 3  [TOP-HAZ-3] gap
    ("MOV", "ODD_BANK", None, "GRF_B", 0, None),           # PC 4  store partial sums
    ("EXIT",),                                             # PC 5
]
TEXT = [
    "MOV GRF_B[0], ODD_BANK",
    "MAC GRF_B[0], EVEN_BANK, SRF_M[0]",
    "MAC GRF_B[0], ODD_BANK, SRF_M[1]",
    "NOP 2",
    "MOV ODD_BANK, GRF_B[0]",
    "EXIT",
]


def bank_init():
    # Bank columns addressed by (bank, col); the trigger of cycle k has col k.
    return {
        ("ODD_BANK", 1): [f16(0.5 * (i + 1)) for i in range(LANES)],    # partial sums
        ("EVEN_BANK", 2): [f16(1.0 + i) for i in range(LANES)],         # W[:,0]
        ("ODD_BANK", 3): [f16(2.0 - 0.25 * i) for i in range(LANES)],   # W[:,1]
    }


SRF_M = {0: f16(0.5), 1: f16(3.0)}


class Regfile:
    """pcu_regfile: combinational read, write at the edge, write-through."""

    def __init__(self, name, init=None):
        self.name, self.mem, self.wr = name, dict(init or {}), None

    def drive_write(self, idx, data):          # S5 drives the write port this cycle
        self.wr = (idx, data)

    def read(self, idx, write_through=True):
        if write_through and self.wr and self.wr[0] == idx:
            return self.wr[1], True
        return self.mem[idx], False

    def edge(self):
        if self.wr:
            self.mem[self.wr[0]] = self.wr[1]
        self.wr = None


def run(acc_write_through, dp_bypass, log=None):
    bank = bank_init()
    # Register files aren't reset ([TOP-ARCH-5]): GRF_B[0] holds -1.0 from an
    # earlier run, which a read that misses the new value would return.
    grf_b = Regfile("grf_b", {0: [f16(-1.0)] * LANES})
    srf_m = Regfile("srf_m", SRF_M)
    s2 = s3 = s4 = s5 = None        # pipeline registers: S1/S2, S2/S3, S3/S4, S4/S5
    pc, nop_left, cycle, done = 0, 0, 0, False
    bank_writes = []
    rows = []
    while True:
        cycle += 1
        ev = {k: "" for k in ("S1", "S2", "S3", "S4", "S5")}
        # S5 (pcu_datapath -> regfile write port / bank_wr_*)
        if s5:
            if s5["dst"] == "GRF_B":
                grf_b.drive_write(s5["dst_idx"], s5["val"])
                ev["S5"] = f"{s5['txt']}: grf_b.wr[{s5['dst_idx']}] <- {s5['val'][0]}"
            elif s5["dst"] == "ODD_BANK":
                bank_writes.append((cycle, "ODD_BANK", s5["col"], s5["val"]))
                ev["S5"] = f"{s5['txt']}: bank_wr ODD col {s5['col']} <- {s5['val'][0]}"
        # S4 (pcu_datapath: add, MAC accumulator through grf_b's S4 port)
        n5 = None
        if s4:
            v = s4["val"]
            if s4["op"] == "MAC":
                acc, via = grf_b.read(s4["dst_idx"], write_through=acc_write_through)
                how = "write-through" if via else "register"
                if dp_bypass and s5 and s5["dst"] == "GRF_B" and s5["dst_idx"] == s4["dst_idx"]:
                    acc, how = s5["val"], "datapath mux"
                v = [f16(a + p) for a, p in zip(acc, v)]
                ev["S4"] = f"{s4['txt']}: grf_b.rd2[{s4['dst_idx']}] = {acc[0]} ({how}); add -> {v[0]}"
            else:
                ev["S4"] = f"{s4['txt']}: pass"
            n5 = dict(s4, val=v)
        # S3 (pcu_datapath: multiply)
        n4 = None
        if s3:
            v = s3["a"]
            if s3["op"] == "MAC":
                v = [f16(a * b) for a, b in zip(s3["a"], s3["b"])]
                ev["S3"] = f"{s3['txt']}: mul -> {v[0]}"
            else:
                ev["S3"] = f"{s3['txt']}: pass"
            n4 = dict(s3, val=v)
        # S2 (pcu_datapath: sources from bank_rd_data and the regfile S2 ports)
        n3 = None
        if s2:
            op, dst, di, src, si, src1 = s2["ins"]
            parts = []
            if src in ("EVEN_BANK", "ODD_BANK"):
                a = bank[(src, s2["col"])]
                parts.append(f"bank_rd_data {src[0]} col {s2['col']} = {a[0]}")
            else:
                a, via = grf_b.read(si)
                parts.append(f"grf_b.rd0[{si}] = {a[0]}" + (" (write-through)" if via else ""))
            b = None
            if src1:
                s, via = srf_m.read(src1[1])
                b = [s] * LANES                     # broadcast, [TOP-ISA-11]
                parts.append(f"srf_m.rd0[{src1[1]}] = {s}")
            ev["S2"] = f"{s2['txt']}: " + "; ".join(parts)
            n3 = dict(op=op, dst=dst, dst_idx=di, a=a, b=b, col=s2["col"], txt=s2["txt"])
        # S1 (pcu_ctrl: one trigger per cycle until EXIT)
        n2 = None
        if not done:
            ins = PROGRAM[pc]
            if ins[0] == "NOP":
                nop_left = nop_left or ins[1]
                ev["S1"] = f"PC {pc} NOP slot {ins[1] - nop_left + 1}/{ins[1]}"
                nop_left -= 1
                if nop_left == 0:
                    pc += 1
            elif ins[0] == "EXIT":
                ev["S1"] = f"PC {pc} EXIT"
                pc, done = 0, True
            else:
                req = ins[3] if ins[3] in ("EVEN_BANK", "ODD_BANK") else None
                ev["S1"] = f"PC {pc} {ins[0]}" + (f"; bank_rd {req[0]} col {cycle}" if req else "")
                n2 = dict(ins=ins, col=cycle, txt=f"PC{pc}")
                pc += 1
        rows.append((cycle, ev))
        # clock edge: register files write, pipeline registers advance
        grf_b.edge()
        srf_m.edge()
        s2, s3, s4, s5 = n2, n3, n4, n5
        if done and not (s2 or s3 or s4 or s5):
            break
    if log:
        for cycle, ev in rows:
            log(f"| {cycle} | " + " | ".join(ev[k] or "–" for k in ("S1", "S2", "S3", "S4", "S5")) + " |")
    return bank_writes, grf_b.mem[0]


def reference():
    """In-order ISA execution: each instruction completes before the next."""
    bank, grf_b, cycle, out = bank_init(), {}, 0, []
    for ins in PROGRAM:
        if ins[0] == "NOP":
            cycle += ins[1]
            continue
        cycle += 1
        if ins[0] == "EXIT":
            break
        op, dst, di, src, si, src1 = ins
        if op == "MOV" and dst == "GRF_B":
            grf_b[di] = bank[(src, cycle)]
        elif op == "MAC":
            p = [f16(a * SRF_M[src1[1]]) for a in bank[(src, cycle)]]
            grf_b[di] = [f16(acc + x) for acc, x in zip(grf_b[di], p)]
        elif op == "MOV" and dst == "ODD_BANK":
            out.append(("ODD_BANK", cycle, grf_b[si]))
    return out, grf_b[0]


ref_writes, ref_grf = reference()
print("Program (PC: instruction):")
for i, t in enumerate(TEXT):
    print(f"  {i}: {t}")
print("\nTrace of (a), lane 0 values. One trigger per cycle; trigger k has row 0, col k.\n")
print("| Cycle | pcu_ctrl S1 | pcu_datapath S2 | S3 | S4 | S5 |")
print("|---|---|---|---|---|---|")
wa, ga = run(True, False, log=print)
wb, gb = run(False, True)
wc, gc = run(False, False)

ok = True
print(f"\nReference bank write: ODD col {ref_writes[0][1]}, lanes 0..3 = {ref_writes[0][2][:4]}")
for tag, w, g, want in (("(a) write-through", wa, ga, True),
                        ("(b) datapath mux", wb, gb, True),
                        ("(c) neither", wc, gc, False)):
    same = [(b, c, d) for _, b, c, d in w] == ref_writes and g == ref_grf
    print(f"  {tag:18} bank write col {w[0][2]} lanes 0..3 = {w[0][3][:4]}  "
          f"{'== reference' if same else '!= reference'}")
    ok &= same == want
print("ok   (a) and (b) match the in-order reference; (c) does not" if ok else "FAIL")
sys.exit(0 if ok else 1)
