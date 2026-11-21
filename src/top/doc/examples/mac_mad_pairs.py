#!/usr/bin/env python3
"""Which MAC/MAD source pairs are legal ([TOP-ISA-22]) and what MAD's SRC2
may hold ([TOP-ISA-23]): the options weighed, and where they differ.

Run from the repo root:
    .venv/bin/python src/top/doc/examples/mac_mad_pairs.py

What it shows:
  1. How Table II's counts for MUL (32) and ADD (40) follow from "GRF" = GRF_A,
     GRF_B and "BANK" = EVEN_BANK, ODD_BANK with at most one bank operand, and
     that the same reading gives MAC 16 and MAD 32, not the paper's 14 and 28.
  2. Every MAC/MAD source pair the paper or ANEMOS actually uses.
  3. How many ways there are to drop 2 of the 16 pairs (to reach 14) without
     dropping a pair that is used: the counts alone can't say which two.
  4. The options: (A) all 16 pairs, what ANEMOS's decoder accepts minus its
     two-bank pairs; (B) drop the same-file pairs (GRF_A, GRF_A) and
     (GRF_B, GRF_B). The program where they differ.
  5. MAD's SRC2: SRF_A only (the paper) or any of the five codes ANEMOS's
     decoder routes to the adder; the program where they differ.
  6. bankside_isa.yaml gives exactly option A and SRF_A only.
Exits non-zero if the yaml doesn't.

The ANEMOS facts are read from github.com/gem5-X/cnm_framework at commit
f2d4018 (src/instr_decoder.cpp, inputs/src/map_dp.cpp, inputs/src/map_conv.cpp),
not run. The paper facts are from ISCA 2021 Table II and Sections III-C and
IV-B (see paper_table3.py for the extraction).
"""
import itertools
import sys
from pathlib import Path

import yaml

isa = yaml.safe_load((Path(__file__).resolve().parent.parent / "bankside_isa.yaml").read_text())
BANKS = {"EVEN_BANK", "ODD_BANK"}
GRF = ["GRF_A", "GRF_B"]
BANK = ["EVEN_BANK", "ODD_BANK"]
ok = True


def pairs(src0, src1, extra_excl=()):
    return [(a, b) for a in src0 for b in src1
            if not (a in BANKS and b in BANKS) and (a, b) not in extra_excl]


# 1. Table II counts ----------------------------------------------------------
print("1. Table II under GRF = {GRF_A, GRF_B}, BANK = {EVEN_BANK, ODD_BANK}, "
      "at most one bank operand [TOP-ARCH-7]")
mul = pairs(GRF + BANK, GRF + BANK + ["SRF_M"])
add = [(a, b) for a, b in pairs(GRF + BANK + ["SRF_A"], GRF + BANK + ["SRF_A"])
       if not (a == b == "SRF_A")]
rows = [("MUL", len(mul), 2, 32), ("ADD", len(add), 2, 40),
        ("MAC", len(mul), 1, 14), ("MAD", len(mul), 2, 28)]
for op, n, dsts, paper in rows:
    print(f"   {op}: {n} source pairs x {dsts} DST = {n * dsts:2}   paper {paper}"
          + ("" if n * dsts == paper else f"   <- {n * dsts - paper} more"))
print(f"   paper total for computations: 32 + 40 + 14 + 28 = {32 + 40 + 14 + 28} "
      "(Section III-C says 114)")
print("   Without the one-bank rule MUL would be 40, so the rule is in the paper's count.")

# 2. Pairs in use -----------------------------------------------------------------
USED = {
    ("EVEN_BANK", "GRF_A"): "paper Fig. 7: MAC(AAM) GRF_A, EVENBANK, GRF_A",
    ("GRF_A", "GRF_B"): "paper Sec. IV-B: MAD GRF_B[0], GRF_A[0], GRF_B[1]",
    ("GRF_A", "EVEN_BANK"): "ANEMOS map_dp: MAC GRFB7 GRFAi EVEN_BANK",
    ("GRF_B", "ODD_BANK"): "ANEMOS map_dp: MAC GRFB7 GRFBi ODD_BANK",
    ("EVEN_BANK", "SRF_M"): "ANEMOS map_conv: MAC/MAD GRFB0 EVEN_BANK SRFM",
    ("ODD_BANK", "SRF_M"): "ANEMOS map_conv: MAC GRFB0 ODD_BANK SRFM",
}
print("\n2. MAC/MAD source pairs that a published kernel or example uses")
for p, where in USED.items():
    print(f"   ({p[0]}, {p[1]})".ljust(28) + where)
print("   (The paper's Fig. 5 and Sec. III-C also use BANK x GRF_A and BANK x SRF_M"
      "\n    without naming the bank; they are covered by the lines above.)")

# 3. Two-pair exclusions consistent with the counts ---------------------------------
free = [p for p in mul if p not in USED]
sets = list(itertools.combinations(free, 2))
print(f"\n3. Ways to drop 2 of the 16 pairs, keeping every used pair: "
      f"C({len(free)}, 2) = {len(sets)}")
print("   Any of them reproduces 14 and 28, so the counts don't identify the pairs.")

# 4. The options -----------------------------------------------------------------
B_EXCL = [("GRF_A", "GRF_A"), ("GRF_B", "GRF_B")]
opt_a = set(mul)
opt_b = set(pairs(GRF + BANK, GRF + BANK + ["SRF_M"], B_EXCL))
print("\n4. Options for the MAC/MAD source pairs")
print(f"   A (ANEMOS's decoder, minus two banks): {len(opt_a)} pairs -> MAC {len(opt_a)}, "
      f"MAD {2 * len(opt_a)}")
print(f"   B (drop same-file GRF pairs):          {len(opt_b)} pairs -> MAC {len(opt_b)}, "
      f"MAD {2 * len(opt_b)}")
print(f"   A - B = {sorted(opt_a - opt_b)}")
print("   Where they differ: MAC GRF_B[0], GRF_A[1], GRF_A[2]")
print("     A and ANEMOS: GRF_B[0] <- round(GRF_B[0] + round(GRF_A[1] x GRF_A[2]))")
print("     B:            illegal [TOP-ISA-2]: one-slot NOP, err_illegal <- 1, GRF_B[0] unchanged")
print("   No published kernel uses either pair, so neither option breaks one.")
print("   B is 1 of the 45 sets in 3: matching the count doesn't make it the paper's set.")
print("   MUL accepts both pairs (its 32 needs all 16), and a MAC or MAD reads its two")
print("   sources in S2 exactly like a MUL, so B saves no read port.")

# 5. MAD SRC2 -----------------------------------------------------------------------
ANEMOS_SRC2 = ["GRF_A", "GRF_B", "SRF_A", "EVEN_BANK", "ODD_BANK"]
anemos_mad = [(a, b, c, d) for a, b in mul for c in ANEMOS_SRC2 for d in GRF
              if sum(x in BANKS for x in (a, b, c)) <= 1]
print("\n5. MAD SRC2 (the addend)")
print(f"   paper Table II: SRF_A only       -> MAD {len(mul) * 2}")
print(f"   ANEMOS decoder: {', '.join(ANEMOS_SRC2)} (indexed by SRC1#), at most one bank"
      f" -> MAD {len(anemos_mad)}")
print("   Where they differ: MAD GRF_A[0], EVEN_BANK, SRF_M[2], GRF_B[2]")
print("     ANEMOS:   GRF_A[0] <- round(round(bank x SRF_M[2]) + GRF_B[2])")
print("     bankside: illegal [TOP-ISA-23]: one-slot NOP, err_illegal <- 1")
print("   No ANEMOS kernel uses an addend other than SRF_A (map_conv: MAD ... SRFM0 SRFA0).")

# 6. The yaml ------------------------------------------------------------------------
print("\n6. bankside_isa.yaml")
for op in ("MUL", "MAC", "MAD"):
    ins = isa["instructions"][op]
    (entry,) = ins["legal"]
    got = set(pairs(entry["src0"], entry["src1"]))
    good = got == opt_a and "one_bank_operand" in ins["constraints"]
    ok &= good
    extra = f", src2 {entry['src2']}" if "src2" in entry else ""
    print(f"   {op}: {len(got)} source pairs{extra}, dst {entry['dst']}: "
          + ("option A" if good else "NOT option A"))
src2 = isa["instructions"]["MAD"]["legal"][0]["src2"]
ok &= src2 == ["SRF_A"]
print(f"   MAD src2 = {src2}: " + ("SRF_A only" if src2 == ["SRF_A"] else "NOT SRF_A only"))
print("ok" if ok else "FAIL")
sys.exit(0 if ok else 1)
