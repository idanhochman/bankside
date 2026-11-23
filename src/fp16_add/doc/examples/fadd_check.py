"""Check the fp16_add spec: its rules, its worked cases, and its references.

Two models of fp16_add, written independently of each other:

  - spec_add:  the rules as the doc states them ([FADD-5] to [FADD-8]). A finite
               sum is computed exactly as a Fraction and rounded once to binary16
               by the IEEE 754 definition: the nearest representable value, ties
               to the even significand, |v| >= 65520 to Inf, and an exact zero
               sum +0 unless both operands are -0.
  - model_add: the informative integer algorithm of the doc ("One way to compute
               it"): order by magnitude, align with guard, round and sticky bits,
               add or subtract, normalise, round, pack.

Checks, all pure Python unless marked:

  1. The worked-case table in ../README.md: every row's s equals both models, and
     the exact-sum column is right.
  2. Structured classes, model_add against spec_add, every pair in each class:
       C1 every special operand (13 of them) against all 65536 patterns, both orders
       C2 every pair of exponent fields 0..30, 12 significands each, both sign cases
       C3 every subnormal (both signs) against 3 significands of every exponent field
       C4 every positive finite a against the 4 b nearest 65520 - a (overflow), and
          the 5 negative patterns nearest -a (cancellation, x + (-x) included)
       C5 every exact tie between an a in [1, 2) and a b of exponent 2^-1 .. 2^-11,
          same sign (all 2^20 x 11 pairs scanned; the ties through both models)
       C6 random pairs: 200000 uniform over all 2^32, 100000 over finite non-zero
       C7 the pairs whose float32 sum is inexact, near the bounds of the
          double-rounding argument of the doc: a of exponent 2^-1 .. 2^15 with
          m in {0, 1, 0x200, 0x3FF}, every b 13 to 15 binades below, both signs
     and every result in C1 to C7 is also checked commutative (s(a, b) = s(b, a)).
  3. Double rounding, pure Python: on C1 to C7, rounding the exact sum to float32
     first (struct 'f', round to nearest even) and then to binary16 gives
     spec_add's result; and the doc's double-rounding table.
  4. With --numpy: the worked cases and C1 to C7 against NumPy float16 (NaN as a
     class, and model_add's NaN bit-exact 0x7E00).
  5. With --exhaustive (needs NumPy, about 15 minutes): all 2^32 pairs, a
     vectorised model_add against NumPy float16 `+`, against the explicit float32
     path (two roundings) and against the float64 sum converted once (one
     rounding); the count of pairs whose float32 sum is inexact; every NaN result
     0x7E00; commutativity; the count of results in each class.
  6. With --anemos FILE: the output of anemos_fadd.cpp (ANEMOS's half 2.2.0 on all
     2^32 pairs and on the worked cases, and GCC's float and double paths) agrees
     with the doc's statements; with --exhaustive as well, its digests of all 2^32
     results (NaN as 0x7E00) equal the digest of bankside's model.

Run from the repo root:
  .venv/bin/python src/fp16_add/doc/examples/fadd_check.py
  python3 src/fp16_add/doc/examples/fadd_check.py --numpy --exhaustive \
      --anemos src/fp16_add/doc/examples/anemos_fadd.out
  python3 src/fp16_add/doc/examples/fadd_check.py --print-pairs   # input for anemos_fadd

Exits non-zero if any check fails.
"""

import argparse
import pathlib
import random
import re
import struct
import sys
from fractions import Fraction

DOC = pathlib.Path(__file__).resolve().parent.parent / "README.md"

ap = argparse.ArgumentParser()
ap.add_argument("--numpy", action="store_true", help="check against NumPy float16")
ap.add_argument("--exhaustive", action="store_true",
                help="all 2^32 pairs against NumPy (needs NumPy, several minutes)")
ap.add_argument("--anemos", type=pathlib.Path, help="output of anemos_fadd.cpp")
ap.add_argument("--print-pairs", action="store_true",
                help="print the worked-case operand pairs, one 'a b' per line, and exit")
args = ap.parse_args()

failures = 0


def check(cond, msg, detail=()):
    global failures
    print(("ok   " if cond else "FAIL ") + msg)
    for d in detail:
        print("       " + d)
    if not cond:
        failures += 1


# ---------------------------------------------------------------- classes [FADD-4]

CANON_NAN = 0x7E00
POS_INF = 0x7C00


def is_nan(x):
    return (x & 0x7FFF) > 0x7C00


def is_inf(x):
    return (x & 0x7FFF) == 0x7C00


def is_zero(x):
    return (x & 0x7FFF) == 0


def is_sub(x):
    return (x & 0x7C00) == 0 and (x & 0x3FF) != 0


def cls(x):
    if is_nan(x):
        return "NaN"
    if is_inf(x):
        return "Inf"
    if is_zero(x):
        return "zero"
    if is_sub(x):
        return "subnormal"
    return "normal"


def value(x):
    """The exact value of a finite pattern, as a Fraction (0 for either zero)."""
    e, m = (x >> 10) & 0x1F, x & 0x3FF
    assert e != 31
    v = Fraction(m, 1 << 24) if e == 0 else Fraction(1024 + m, 1024) * Fraction(2) ** (e - 15)
    return -v if x & 0x8000 else v


# ------------------------------------------------- spec_add: the rules, Fractions

OVERFLOW = Fraction(65520)            # 2^15 * (2 - 2^-11): IEEE 754 7.4, RNE
MIN_SUB = Fraction(1, 1 << 24)        # 2^-24


def round_rne(q):
    """Round a non-zero Fraction once to binary16: nearest, ties to even."""
    sign = 0x8000 if q < 0 else 0
    q = abs(q)
    if q >= OVERFLOW:
        return sign | POS_INF
    if q < Fraction(1, 1 << 14):
        quantum, base = MIN_SUB, 0                 # subnormal range, bits = n
    else:
        e = q.numerator.bit_length() - q.denominator.bit_length()
        if Fraction(2) ** e > q:
            e -= 1
        assert Fraction(2) ** e <= q < Fraction(2) ** (e + 1)
        quantum = Fraction(2) ** (e - 10)
        base = ((e + 15) << 10) - 1024             # n in [1024, 2048]
    n, rem = divmod(q, quantum)
    n = int(n)
    half = quantum / 2
    if rem > half or (rem == half and n & 1):
        n += 1
    bits = base + n                                # n = 2048 carries into the exponent
    assert bits < POS_INF
    return sign | bits


def spec_add(a, b):
    if is_nan(a) or is_nan(b):
        return CANON_NAN                           # [FADD-8]
    if is_inf(a) and is_inf(b):
        return a if a == b else CANON_NAN          # [FADD-5]: Inf - Inf is invalid
    if is_inf(a):
        return a
    if is_inf(b):
        return b
    v = value(a) + value(b)
    if v == 0:                                     # [FADD-6]: an exact zero sum
        return 0x8000 if (a == 0x8000 and b == 0x8000) else 0x0000
    r = round_rne(v)                               # [FADD-7]
    assert (r & 0x8000) == (0x8000 if v < 0 else 0)
    return r


# ---------------------------------------- model_add: the informative algorithm


def model_add(a, b):
    ea, ma = (a >> 10) & 0x1F, a & 0x3FF
    eb, mb = (b >> 10) & 0x1F, b & 0x3FF
    nan_a, nan_b = ea == 31 and ma != 0, eb == 31 and mb != 0
    inf_a, inf_b = ea == 31 and ma == 0, eb == 31 and mb == 0
    if nan_a or nan_b:
        return CANON_NAN
    if inf_a and inf_b:
        return a if ((a ^ b) & 0x8000) == 0 else CANON_NAN
    if inf_a or inf_b:
        return a if inf_a else b
    # step 1: order by magnitude (the 15 low bits compare as the magnitude)
    if (b & 0x7FFF) > (a & 0x7FFF):
        a, b = b, a
    sign = a & 0x8000
    sub = ((a ^ b) & 0x8000) != 0
    ea, ma, eb, mb = (a >> 10) & 0x1F, a & 0x3FF, (b >> 10) & 0x1F, b & 0x3FF
    # unpack: significand with the hidden bit; the exponent field, subnormal as 1
    Ma, Mb = ((ea != 0) << 10) | ma, ((eb != 0) << 10) | mb
    Fa, Fb = max(ea, 1), max(eb, 1)
    if Ma == 0:                                    # both zero: -0 only from -0 + -0
        return a & b & 0x8000
    # step 2: align, three bits below the LSB: guard, round, sticky
    d = Fa - Fb
    X = Ma << 3
    Yw = Mb << 3
    Y = (Yw >> d) | ((Yw & ((1 << d) - 1)) != 0)  # d >= 14 leaves only the sticky bit
    # step 3: add or subtract
    S = X - Y if sub else X + Y
    if S == 0:
        return 0x0000                              # x + (-x) = +0
    # step 4: normalise S into [2^13, 2^14), or stop at the subnormal exponent
    F = Fa
    if S >= 1 << 14:
        S = (S >> 1) | (S & 1)
        F += 1
    while S < 1 << 13 and F > 1:
        S <<= 1
        F -= 1
    # step 5: round to nearest even on guard, round and sticky
    n = S >> 3
    g = (S >> 2) & 1
    st = (S & 3) != 0
    if g and (st or (n & 1)):
        n += 1
    # step 6: pack; n = 2048 (or 1024 from a subnormal) carries into the exponent
    bits = ((F - 1) << 10) + n
    if bits >= POS_INF:
        return sign | POS_INF
    return sign | bits


# ------------------------------------------------------ the float32 path, stdlib


def f32(x):
    """Round a Python float (here always an exact sum) to float32, RNE."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def double_round(a, b):
    """The sum rounded to float32 first, then to binary16: NumPy's path."""
    if is_nan(a) or is_nan(b) or is_inf(a) or is_inf(b):
        return spec_add(a, b)
    v = float(value(a)) + float(value(b))          # exact: at most 40 bits
    w = f32(v)
    if w == 0:
        return spec_add(a, b)                      # exact zero, signs per [FADD-6]
    return round_rne(Fraction(w))


def f32_exact(a, b):
    v = float(value(a)) + float(value(b))
    return f32(v) == v


# ------------------------------------------------------------------- worked cases


def doc_tables():
    """Rows of the tables whose header has `a`, `b` and `s`."""
    rows, header = [], None
    for line in DOC.read_text().splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(line) <= set("|- "):
            continue
        if {"`a`", "`b`", "`s`"} <= set(header):
            rows.append(dict(zip(header, cells)))
    return rows


def hexcell(c):
    m = re.fullmatch(r"(0x[0-9A-F]{4})", c.replace("**", ""))
    return int(m.group(1), 16) if m else None


cases, dr_rows = [], []
for r in doc_tables():
    a, b, s = hexcell(r["`a`"]), hexcell(r["`b`"]), hexcell(r["`s`"])
    if a is None or b is None or s is None:
        print("FAIL unparsed row", r)
        failures += 1
        continue
    (dr_rows if "float32 sum" in r else cases).append((r.get("#", "?"), a, b, s, r))

if args.print_pairs:
    for _, a, b, _, _ in cases:
        print(f"0x{a:04X} 0x{b:04X}")
    sys.exit(0)


def exact_cell(c):
    """'k', 'k/d', 'k·2^e' or '2^e', with an optional leading minus, as a Fraction."""
    m = re.fullmatch(r"(−?)(?:(\d+(?:/\d+)?)(?:·|$))?(?:2\^(−?\d+))?", c)
    if not m or not (m.group(2) or m.group(3)):
        return None
    v = Fraction(m.group(2)) if m.group(2) else Fraction(1)
    if m.group(3):
        v *= Fraction(2) ** int(m.group(3).replace("−", "-"))
    return -v if m.group(1) else v


def finite(x):
    return not (is_nan(x) or is_inf(x))


print("== 1. Worked cases in README.md")
check(len(cases) >= 40, f"the worked-case table has {len(cases)} rows")
bad = [(n, a, b, s, spec_add(a, b), model_add(a, b)) for n, a, b, s, _ in cases
       if not (spec_add(a, b) == s == model_add(a, b))]
check(not bad, "every row's s equals spec_add and model_add",
      [f"#{n}: 0x{a:04X} + 0x{b:04X}: doc 0x{s:04X}, spec 0x{p:04X}, model 0x{m:04X}"
       for n, a, b, s, p, m in bad])
exact_ok, n_finite = 0, 0
for n, a, b, s, r in cases:
    if not (finite(a) and finite(b)):
        continue
    n_finite += 1
    col = r.get("Exact sum", "").strip("`")
    want = exact_cell(col)
    if want is None:
        check(False, f"#{n}: exact sum column {col!r} unparsed")
    elif want != value(a) + value(b):
        check(False, f"#{n}: exact sum column {col} is {value(a) + value(b)}")
    else:
        exact_ok += 1
check(exact_ok == n_finite, f"the exact-sum column is right on all {exact_ok} finite rows")
bad = [n for n, a, b, s, _ in cases if model_add(b, a) != s]
check(not bad, "every row gives the same s with the operands swapped", bad)

# ----------------------------------------------------------- structured classes

print("== 2. Structured classes, model_add against spec_add")
SPECIALS = [0x0000, 0x8000, 0x7C00, 0xFC00,                       # zeros, Infs
            0x7C01, 0x7D55, 0x7DFF, 0x7E00, 0x7FFF,               # +NaNs: sNaN, qNaN
            0xFC01, 0xFDFF, 0xFE00, 0xFFFF]                       # -NaNs
SIGS = [0x000, 0x001, 0x002, 0x0AA, 0x155, 0x1FF, 0x200, 0x2AA, 0x300, 0x3FD, 0x3FE, 0x3FF]


def c1():
    for x in SPECIALS:
        for y in range(0x10000):
            yield x, y
            yield y, x


def c2():
    for ea in range(31):
        for eb in range(31):
            for ma in SIGS:
                for mb in SIGS:
                    a, b = (ea << 10) | ma, (eb << 10) | mb
                    yield a, b
                    yield a | 0x8000, b


def c3():
    for m in range(1, 0x400):
        for e in range(31):
            for mb in (0x000, 0x155, 0x3FF):
                yield m, (e << 10) | mb
                yield m | 0x8000, (e << 10) | mb


def f16_floor(v):
    """The largest positive finite pattern whose value is <= v (v > 0), or None."""
    lo, hi = 0x0001, 0x7BFF
    if value(lo) > v:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if value(mid) <= v:
            lo = mid
        else:
            hi = mid - 1
    return lo


def c4():
    for a in range(0x0000, 0x7C00):
        t = OVERFLOW - value(a)                    # the overflow bound
        if 0 < t <= 65504:
            b0 = f16_floor(t)
            for b in range(b0 - 1, b0 + 3):
                if 0x0000 <= b <= 0x7BFF:
                    yield a, b
        for b in range(a - 2, a + 3):              # cancellation: b near -a
            if 0x0000 <= b <= 0x7BFF:
                yield a, b | 0x8000


def c6():
    rnd = random.Random(34)
    for _ in range(200000):
        yield rnd.getrandbits(16), rnd.getrandbits(16)
    for _ in range(100000):
        a = rnd.choice([rnd.randrange(0x0001, 0x7C00), rnd.randrange(0x0001, 0x0400)])
        b = rnd.randrange(0x0001, 0x7C00)
        yield a | (rnd.getrandbits(1) << 15), b | (rnd.getrandbits(1) << 15)


def c7():
    for ea in range(14, 31):                       # 2^-1 .. 2^15
        for ma in (0x000, 0x001, 0x200, 0x3FF):
            a = (ea << 10) | ma
            for k in (13, 14, 15):
                eb = ea - k
                for mb in range(0x400):
                    b = (eb << 10) | mb if eb >= 1 else mb
                    yield a, b
                    yield a, b | 0x8000


def run_class(name, gen):
    n = 0
    bad, dr_bad = [], []
    by_cls = {}
    inexact32 = 0
    for a, b in gen:
        n += 1
        s = spec_add(a, b)
        m = model_add(a, b)
        if s != m or model_add(b, a) != m:
            if len(bad) < 5:
                bad.append(f"0x{a:04X} + 0x{b:04X}: spec 0x{s:04X}, model 0x{m:04X}, "
                           f"swapped 0x{model_add(b, a):04X}")
            continue
        by_cls[cls(m)] = by_cls.get(cls(m), 0) + 1
        if finite(a) and finite(b):
            if not f32_exact(a, b):
                inexact32 += 1
                if double_round(a, b) != s and len(dr_bad) < 5:
                    dr_bad.append(f"0x{a:04X} + 0x{b:04X}")
    summary = ", ".join(f"{k} {v}" for k, v in sorted(by_cls.items()))
    check(not bad, f"{name}: {n} pairs; results: {summary}", bad)
    check(not dr_bad, f"{name.split()[0]}: {inexact32} pairs with an inexact float32 sum; "
          "rounding it again to binary16 gives spec_add on every one", dr_bad)
    return inexact32


CLASSES = [
    ("C1 specials x all 65536, both orders", c1),
    ("C2 all exponent-field pairs x 12 x 12 significands, 2 sign cases", c2),
    ("C3 all subnormals x every exponent field x 3 significands", c3),
    ("C4 every positive finite a x the b nearest 65520 - a and nearest -a", c4),
    ("C6 random: 200000 uniform, 100000 finite non-zero", c6),
    ("C7 inexact float32 sums: a in 2^-1..2^15 x b 13 to 15 binades below", c7),
]
inexact_by_class = {}
for name, gen in CLASSES:
    inexact_by_class[name.split()[0]] = run_class(name, gen())
check(inexact_by_class["C7"] > 0, "C7 has inexact float32 sums, so it tests the argument")

# C5: every exact tie between a in [1, 2) and b = (1024 + mb) * 2^(-d-10), d = 1..11,
# same sign. In units of b's quantum the exact sum is T = Ma * 2^d + Mb; the result's
# quantum is 2^(bitlength(T) - 11) units.
ties_up = ties_down = 0
bad = []
for d in range(1, 12):
    for ma in range(1024):
        a = 0x3C00 | ma
        base = (1024 | ma) << d
        for mb in range(1024):
            T = base + (1024 | mb)
            sh = T.bit_length() - 11
            if (T & ((1 << sh) - 1)) != 1 << (sh - 1):
                continue
            b = ((15 - d) << 10) | mb
            m = model_add(a, b)
            if m != spec_add(a, b) or m != model_add(b, a):
                bad.append(f"0x{a:04X} + 0x{b:04X}")
            if m & 1:
                bad.append(f"0x{a:04X} + 0x{b:04X}: tie not to even")
            if (T >> sh) & 1:
                ties_up += 1
            else:
                ties_down += 1
check(not bad and ties_up > 0 and ties_down > 0,
      f"C5 every tie of a in [1, 2) + b in [2^-11, 1), same sign: {ties_up + ties_down} ties, "
      f"{ties_up} round up (odd below), {ties_down} round down (even below), all to even",
      bad[:5])

# ------------------------------------------------- 3. the double-rounding table

print("== 3. Double rounding: the doc's table")


def round_bits(v, p):
    """Round a non-zero Fraction to p significant bits, RNE, any exponent."""
    sgn = -1 if v < 0 else 1
    v = abs(v)
    e = v.numerator.bit_length() - v.denominator.bit_length()
    if Fraction(2) ** e > v:
        e -= 1
    q = Fraction(2) ** (e - p + 1)
    n, rem = divmod(v, q)
    n = int(n)
    if rem > q / 2 or (rem == q / 2 and n & 1):
        n += 1
    return sgn * n * q


check(len(dr_rows) >= 4, f"the double-rounding table has {len(dr_rows)} rows")
bad = []
for n, a, b, s, r in dr_rows:
    v = value(a) + value(b)
    w = Fraction(f32(float(v)))
    if spec_add(a, b) != s or double_round(a, b) != s:
        bad.append(f"#{n}: s")
    col32 = r["float32 sum"].strip("`")
    exact32 = col32.startswith("exact")
    if exact32 != (w == v):
        bad.append(f"#{n}: float32 column says exact={exact32}, is {w == v}")
    if not exact32 and exact_cell(col32) != w:
        bad.append(f"#{n}: float32 column {col32}, float32 sum is {w}")
    col12 = r.get("Through 12 bits", "")
    if col12:
        got = round_rne(round_bits(v, 12))
        if hexcell(col12) != got:
            bad.append(f"#{n}: 12-bit column {col12}, gives 0x{got:04X}")
check(not bad, "every row: s, the float32 sum column, the 12-bit column", bad)

# ------------------------------------------------------------------- NumPy

np = None
if args.numpy or args.exhaustive:
    import numpy as np


def np_add(a, b):
    """NumPy float16 sum of bit arrays, as uint16 bits."""
    x = np.asarray(a, dtype=np.uint16).view(np.float16)
    y = np.asarray(b, dtype=np.uint16).view(np.float16)
    with np.errstate(all="ignore"):
        return (x + y).view(np.uint16)


if args.numpy:
    print(f"== 4. NumPy {np.__version__} float16")
    A = np.array([c[1] for c in cases], dtype=np.uint16)
    B = np.array([c[2] for c in cases], dtype=np.uint16)
    R = np_add(A, B)
    bad = []
    for (n, a, b, s, r), q in zip(cases, R.tolist()):
        if is_nan(s) != is_nan(q) or (not is_nan(s) and s != q):
            bad.append(f"#{n}: 0x{a:04X} + 0x{b:04X}: doc 0x{s:04X}, NumPy 0x{q:04X}")
        col = r.get("NumPy", "")
        if hexcell(col) != q:
            bad.append(f"#{n}: NumPy column {col}, NumPy gives 0x{q:04X}")
    check(not bad, "the worked cases equal NumPy (a NaN as a class) and the NumPy column", bad)

    for name, gen in CLASSES:
        pairs = list(gen())
        A = np.array([p[0] for p in pairs], dtype=np.uint16)
        B = np.array([p[1] for p in pairs], dtype=np.uint16)
        R = np_add(A, B).tolist()
        bad = []
        for (a, b), q in zip(pairs, R):
            m = model_add(a, b)
            if is_nan(m) != is_nan(q) or (not is_nan(m) and m != q):
                bad.append(f"0x{a:04X} + 0x{b:04X}: model 0x{m:04X}, NumPy 0x{q:04X}")
        check(not bad, f"{name.split()[0]}: model_add = NumPy on all {len(pairs)} pairs "
              "(NaN as a class)", bad[:5])


BITLEN = None


def vec_model(a, b):
    """model_add on uint16 arrays: the same six steps."""
    ai, bi = a.astype(np.int64), b.astype(np.int64)
    swap = (bi & 0x7FFF) > (ai & 0x7FFF)
    x = np.where(swap, bi, ai)                              # step 1: |x| >= |y|
    y = np.where(swap, ai, bi)
    sign = x & 0x8000
    sub = ((x ^ y) & 0x8000) != 0
    ex, mx, ey, my = (x >> 10) & 31, x & 0x3FF, (y >> 10) & 31, y & 0x3FF
    Mx = np.where(ex != 0, 1024 | mx, mx)
    My = np.where(ey != 0, 1024 | my, my)
    Fx, Fy = np.maximum(ex, 1), np.maximum(ey, 1)
    d = np.minimum(Fx - Fy, 15)                             # step 2: align
    X, Yw = Mx << 3, My << 3
    Y = (Yw >> d) | ((Yw & ((1 << d) - 1)) != 0)
    S = np.where(sub, X - Y, X + Y)                         # step 3
    carry = S >= (1 << 14)                                  # step 4: normalise
    S = np.where(carry, (S >> 1) | (S & 1), S)
    F = Fx + carry
    L = BITLEN[S]
    sh = np.clip(14 - L, 0, None)
    sh = np.minimum(sh, F - 1)
    S = S << sh
    F = F - sh
    n = S >> 3                                              # step 5: round
    g = (S >> 2) & 1
    st = (S & 3) != 0
    n = n + (g & (st | (n & 1)))
    bits = np.minimum(((F - 1) << 10) + n, POS_INF)         # step 6: pack
    out = np.where(S == 0, 0, sign | bits)
    out = np.where((Mx == 0) & (My == 0), x & y & 0x8000, out)   # zero + zero
    nan_x = (ex == 31) & (mx != 0)
    nan_y = (ey == 31) & (my != 0)
    inf_x = (ex == 31) & (mx == 0)
    inf_y = (ey == 31) & (my == 0)
    out = np.where(inf_x, x, out)                           # |x| >= |y|: x is the Inf
    out = np.where(inf_x & inf_y & sub, CANON_NAN, out)
    out = np.where(nan_x | nan_y, CANON_NAN, out)
    return out.astype(np.uint16)


if args.exhaustive:
    print("== 5. All 2^32 pairs: vectorised model_add against NumPy float16")
    BITLEN = np.zeros(1 << 15, dtype=np.int64)
    for k in range(15):
        BITLEN[1 << k:] = k + 1
    Ball = np.arange(0x10000, dtype=np.uint32).astype(np.uint16)
    Bf32 = Ball.view(np.float16).astype(np.float32)
    Bf64 = Ball.view(np.float16).astype(np.float64)
    STEP = 16
    mism = {"NumPy +": 0, "float32 path": 0, "float64 once": 0}
    examples = []
    counts = {"zero": 0, "subnormal": 0, "normal": 0, "Inf": 0, "NaN": 0}
    neg_zero = pos_zero = 0
    nan_bits_ok = True
    noncomm = 0
    inexact32 = 0
    K = np.uint64(0x9E3779B97F4A7C15)
    digest = 0

    def differs(M, Q):
        mn = (M & 0x7FFF) > 0x7C00
        qn = (Q & 0x7FFF) > 0x7C00
        return (mn != qn) | (~mn & (M != Q))

    for a0 in range(0, 0x10000, STEP):
        A = np.repeat(np.arange(a0, a0 + STEP, dtype=np.uint32).astype(np.uint16), 0x10000)
        B = np.tile(Ball, STEP)
        M = vec_model(A, B)
        x16 = A.view(np.float16)
        Af32 = x16.astype(np.float32)
        Af64 = x16.astype(np.float64)
        B32, B64 = np.tile(Bf32, STEP), np.tile(Bf64, STEP)
        with np.errstate(all="ignore"):
            s32 = Af32 + B32
            s64 = Af64 + B64                                # exact
            refs = {"NumPy +": np_add(A, B),
                    "float32 path": s32.astype(np.float16).view(np.uint16),
                    "float64 once": s64.astype(np.float16).view(np.uint16)}
        fin = np.isfinite(s64)
        inexact32 += int((fin & (s32.astype(np.float64) != s64)).sum())
        for key, Q in refs.items():
            df = differs(M, Q)
            k = int(df.sum())
            if k:
                mism[key] += k
                for i in np.nonzero(df)[0][:3]:
                    examples.append(f"{key}: 0x{int(A[i]):04X} + 0x{int(B[i]):04X}: "
                                    f"model 0x{int(M[i]):04X}, ref 0x{int(Q[i]):04X}")
        mn = (M & 0x7FFF) > 0x7C00
        if mn.any() and not (M[mn] == CANON_NAN).all():
            nan_bits_ok = False
        mag = M & 0x7FFF
        counts["NaN"] += int(mn.sum())
        counts["Inf"] += int((mag == 0x7C00).sum())
        counts["zero"] += int((mag == 0).sum())
        counts["subnormal"] += int(((mag > 0) & (mag < 0x0400)).sum())
        counts["normal"] += int(((mag >= 0x0400) & (mag < 0x7C00)).sum())
        neg_zero += int((M == 0x8000).sum())
        pos_zero += int((M == 0x0000).sum())
        # the digest of anemos_fadd.cpp: sum of (r + 1) * ((a << 16 | b) * K + 1) mod 2^64
        idx = (A.astype(np.uint64) << np.uint64(16)) | B.astype(np.uint64)
        w = idx * K + np.uint64(1)
        digest = (digest + int(np.sum((M.astype(np.uint64) + np.uint64(1)) * w,
                                      dtype=np.uint64))) % (1 << 64)
        noncomm += int((vec_model(B, A) != M).sum())
    total = sum(counts.values())
    check(total == 1 << 32, f"{total} pairs")
    for key, k in mism.items():
        check(k == 0, f"vectorised model_add = {key} on every pair (NaN as a class): {k} differ",
              [e for e in examples if e.startswith(key)][:5])
    check(inexact32 > 0, f"{inexact32} pairs have an inexact float32 sum (the double rounding "
          "of NumPy's path happens), and the float32 path still equals the model on all")
    check(nan_bits_ok, "every NaN result of the model is 0x7E00")
    check(noncomm == 0, f"s(a, b) = s(b, a) bit for bit on every pair: {noncomm} differ")
    check(neg_zero == 1, f"-0 is the result of exactly one pair, -0 + -0: {neg_zero}")
    print(f"       +0 results: {pos_zero}")
    model_digest = digest
    print(f"       digest of the model's results: {model_digest}")
    print("       result classes: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    n_nonnan = 0x10000 - 2 * 1023
    exp_nan = (1 << 32) - n_nonnan ** 2 + 2
    check(counts["NaN"] == exp_nan,
          f"NaN results = pairs with a NaN operand + the 2 Inf - Inf pairs = {exp_nan}")

# ------------------------------------------------------------------- ANEMOS

if args.anemos:
    print(f"== 6. ANEMOS half 2.2.0, from {args.anemos.name}")
    kv, diffs, case_out, inv_bits = {}, [], {}, {}
    for line in args.anemos.read_text().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] in ("differ", "dr_differ") and len(f) > 2:
            diffs.append(line)
        elif f[0] == "case":
            case_out[(int(f[1], 16), int(f[2], 16))] = int(f[3], 16)
        elif f[0] == "nan_invalid_bits":
            inv_bits[int(f[1], 16)] = int(f[2])
        else:
            kv[f[0]] = int(f[1])
    check(kv.get("pairs") == 1 << 32, f"ANEMOS ran all 2^32 pairs: {kv.get('pairs')}")
    n_nonnan = 0x10000 - 2046
    exp_nan = (1 << 32) - n_nonnan ** 2 + 2
    check(kv.get("differ") == 0 and not [d for d in diffs if d.startswith("differ")],
          f"ANEMOS = the one-rounding reference on every non-NaN result, signs of zero "
          f"included: {kv.get('differ')} differ", diffs[:5])
    check(kv.get("nan_both") == exp_nan,
          f"ANEMOS gives a NaN exactly where the spec does: {kv.get('nan_both')} = {exp_nan}")
    check(kv.get("ref_neg_zero_results") == 1,
          f"the reference gives -0 on exactly one pair: {kv.get('ref_neg_zero_results')}")
    check(kv.get("f32_inexact", 0) > 0 and kv.get("dr_differ") == 0
          and kv.get("dr_nan_mismatch") == 0,
          f"GCC float path: {kv.get('f32_inexact')} inexact float sums, "
          f"{kv.get('dr_differ')} results differ from one rounding")
    if args.exhaustive:
        check(kv.get("f32_inexact") == inexact32,
              f"the same count of inexact float32 sums as NumPy's: {inexact32}")
        for key in ("digest_anemos", "digest_ref", "digest_ref32"):
            check(kv.get(key) == model_digest,
                  f"{key}: the 2^32 results, NaN as 0x7E00, have the digest of "
                  f"bankside's model: {kv.get(key)}")
    check(inv_bits == {0x7FFF: 2}, f"ANEMOS's NaN for Inf - Inf (2 pairs) is 0x7FFF: {inv_bits}")
    check(kv.get("nan_operand_distinct_bits", 0) > 1,
          f"ANEMOS's NaN for a NaN operand is not one pattern: "
          f"{kv.get('nan_operand_distinct_bits')} distinct patterns (propagated)")
    bad = []
    for n, a, b, s, r in cases:
        q = case_out.get((a, b))
        if q is None:
            bad.append(f"#{n}: not in the ANEMOS output")
            continue
        if is_nan(s) != is_nan(q) or (not is_nan(s) and s != q):
            bad.append(f"#{n}: 0x{a:04X} + 0x{b:04X}: spec 0x{s:04X}, ANEMOS 0x{q:04X}")
        col = r.get("ANEMOS", "")
        want = hexcell(col) if hexcell(col) is not None else (s if col == "same" else None)
        if want != q:
            bad.append(f"#{n}: ANEMOS column {col!r}, ANEMOS gives 0x{q:04X}")
    check(not bad, "every worked case matches ANEMOS's run and the ANEMOS column", bad)

print("PASS" if failures == 0 else f"{failures} check(s) FAILED")
sys.exit(1 if failures else 0)
