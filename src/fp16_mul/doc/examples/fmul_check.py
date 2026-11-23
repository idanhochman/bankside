"""Check the fp16_mul spec: its rules, its worked cases, and its references.

Two models of fp16_mul, written independently of each other:

  - spec_mul:  the rules as the doc states them ([FMUL-5] to [FMUL-8]). A finite
               product is computed exactly as a Fraction and rounded once to
               binary16 by the IEEE 754 definition: the nearest representable
               value, ties to the even significand, and |x| >= 65520 to Inf.
  - model_mul: the informative integer algorithm of the doc ("One way to compute
               it"): 11 x 11-bit significand product, one shift, guard and sticky.

Checks, all pure Python unless marked:

  1. The worked-case table in ../README.md: every row's p equals both models.
  2. Structured classes, model_mul against spec_mul, every pair in each class:
       C1 every special operand (13 of them) against all 65536 patterns, both orders
       C2 every pair of exponent fields 0..30, 12 significands each, both sign cases
       C3 every subnormal (both signs) against 3 significands of every exponent field
       C4 every positive finite non-zero a against the 4 patterns of b nearest each
          of the overflow, min-normal and underflow thresholds (T / a)
       C5 every significand pair whose product is an exact tie at [1, 2) x [1, 2)
          (all 2^20 pairs through model_mul; the ties also against spec_mul)
       C6 random pairs: 200000 uniform over all 2^32, 100000 over finite non-zero
     and every result in C1 to C6 is also checked commutative (p(a, b) = p(b, a)).
  3. With --numpy: the worked cases and C1 to C6 against NumPy float16 (NaN as a
     class, and model_mul's NaN bit-exact 0x7E00).
  4. With --exhaustive (needs NumPy, about 15 minutes): all 2^32 pairs, a
     vectorised model_mul (the variant that normalises a subnormal operand first)
     against NumPy float16, every NaN result 0x7E00, commutativity, and the count
     of results in each class.
  5. With --anemos FILE: the output of anemos_fmul.cpp (ANEMOS's half 2.2.0 on all
     2^32 pairs and on the worked cases) agrees with the doc's ANEMOS statements;
     with --exhaustive as well, its digest of all 2^32 results (NaN as 0x7E00)
     equals the digest of bankside's model.

Run from the repo root:
  .venv/bin/python src/fp16_mul/doc/examples/fmul_check.py
  python3 src/fp16_mul/doc/examples/fmul_check.py --numpy --exhaustive \
      --anemos src/fp16_mul/doc/examples/anemos_fmul.out
  python3 src/fp16_mul/doc/examples/fmul_check.py --print-pairs   # input for anemos_fmul

Exits non-zero if any check fails.
"""

import argparse
import pathlib
import random
import re
import sys
from fractions import Fraction

DOC = pathlib.Path(__file__).resolve().parent.parent / "README.md"

ap = argparse.ArgumentParser()
ap.add_argument("--numpy", action="store_true", help="check against NumPy float16")
ap.add_argument("--exhaustive", action="store_true",
                help="all 2^32 pairs against NumPy (needs NumPy, several minutes)")
ap.add_argument("--anemos", type=pathlib.Path, help="output of anemos_fmul.cpp")
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


# ---------------------------------------------------------------- classes [FMUL-4]

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
    """The exact value of a finite pattern, as a Fraction."""
    e, m = (x >> 10) & 0x1F, x & 0x3FF
    assert e != 31
    v = Fraction(m, 1 << 24) if e == 0 else Fraction(1024 + m, 1024) * Fraction(2) ** (e - 15)
    return -v if x & 0x8000 else v


# ------------------------------------------------- spec_mul: the rules, Fractions

OVERFLOW = Fraction(65520)            # 2^15 * (2 - 2^-11): IEEE 754 7.4, RNE
MIN_SUB = Fraction(1, 1 << 24)        # 2^-24


def round_rne(q):
    """Round a non-zero Fraction once to binary16: nearest, ties to even."""
    sign = 0x8000 if q < 0 else 0
    q = abs(q)
    if q >= OVERFLOW:
        return sign | POS_INF
    # the quantum (spacing of representable values) at q
    if q < Fraction(1, 1 << 14):
        quantum, base = MIN_SUB, 0                 # subnormal range, bits = n
    else:
        e = q.numerator.bit_length() - q.denominator.bit_length()
        if Fraction(2) ** e > q:
            e -= 1
        assert Fraction(2) ** e <= q < Fraction(2) ** (e + 1)
        quantum = Fraction(2) ** (e - 10)
        base = (e + 15) << 10                     # n in [1024, 2048]
        base -= 1024
    n, rem = divmod(q, quantum)                    # q = n * quantum + rem
    n = int(n)
    half = quantum / 2
    if rem > half or (rem == half and n & 1):
        n += 1
    bits = base + n                                # n = 2048 carries into the exponent
    assert bits < POS_INF                          # q < 65520 never rounds to Inf
    return sign | bits


def spec_mul(a, b):
    s = (a ^ b) & 0x8000                           # [FMUL-6]: sign is the XOR
    if is_nan(a) or is_nan(b):
        return CANON_NAN                           # [FMUL-8]
    if (is_inf(a) and is_zero(b)) or (is_zero(a) and is_inf(b)):
        return CANON_NAN                           # invalid, [FMUL-8]
    if is_inf(a) or is_inf(b):
        return s | POS_INF                         # [FMUL-5]
    if is_zero(a) or is_zero(b):
        return s                                   # [FMUL-5]
    r = round_rne(value(a) * value(b))             # [FMUL-7]
    assert (r & 0x8000) == s
    return r


# ---------------------------------------- model_mul: the informative algorithm


def model_mul(a, b):
    s = (a ^ b) & 0x8000
    ea, ma = (a >> 10) & 0x1F, a & 0x3FF
    eb, mb = (b >> 10) & 0x1F, b & 0x3FF
    nan_a, nan_b = ea == 31 and ma != 0, eb == 31 and mb != 0
    inf_a, inf_b = ea == 31 and ma == 0, eb == 31 and mb == 0
    zero_a, zero_b = ea == 0 and ma == 0, eb == 0 and mb == 0
    if nan_a or nan_b or (inf_a and zero_b) or (zero_a and inf_b):
        return CANON_NAN
    if inf_a or inf_b:
        return s | POS_INF
    if zero_a or zero_b:
        return s
    # step 1: significands with the hidden bit, effective exponents
    Ma, Mb = ((ea != 0) << 10) | ma, ((eb != 0) << 10) | mb
    Ea, Eb = max(ea, 1) - 15, max(eb, 1) - 15
    # step 2: P = Ma * Mb, 22 bits; the exact product is P * 2^(E)
    P = Ma * Mb
    E = Ea + Eb - 20
    # step 3: the leading bit's weight, and the quantum of the result
    t = E + P.bit_length() - 1
    q_exp = max(t, -14) - 10
    shift = q_exp - E
    # step 4: keep n = P >> shift (at most 11 bits), round with guard and sticky
    assert shift >= 0, "the doc says the shift is never negative"
    n = P >> shift
    if shift > 0:
        guard = (P >> (shift - 1)) & 1
        sticky = (P & ((1 << (shift - 1)) - 1)) != 0
        if guard and (sticky or (n & 1)):
            n += 1
    # step 5: pack; n = 2048 (or 1024 from a subnormal) carries into the exponent
    if t >= -14:
        bits = ((q_exp + 10 + 15) << 10) + n - 1024
    else:
        bits = n
    if bits >= POS_INF:
        return s | POS_INF                         # overflow, [FMUL-7]
    return s | bits


# ------------------------------------------------------------------- worked cases


def doc_table():
    """The worked-case table: rows of the table whose header has `a`, `b`, `p`."""
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
        if {"`a`", "`b`", "`p`"} <= set(header):
            rows.append(dict(zip(header, cells)))
    return rows


def hexcell(c):
    m = re.fullmatch(r"(0x[0-9A-F]{4})", c.replace("**", ""))
    return int(m.group(1), 16) if m else None


cases = []
for r in doc_table():
    a, b, p = hexcell(r["`a`"]), hexcell(r["`b`"]), hexcell(r["`p`"])
    if a is None or b is None or p is None:
        print("FAIL unparsed row", r)
        failures += 1
        continue
    cases.append((r.get("#", "?"), a, b, p, r))

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


exact_ok = 0
print("== 1. Worked cases in README.md")
check(len(cases) >= 30, f"the worked-case table has {len(cases)} rows")
bad = [(n, a, b, p, spec_mul(a, b), model_mul(a, b)) for n, a, b, p, _ in cases
       if not (spec_mul(a, b) == p == model_mul(a, b))]
check(not bad, "every row's p equals spec_mul and model_mul",
      [f"#{n}: 0x{a:04X} x 0x{b:04X}: doc 0x{p:04X}, spec 0x{s:04X}, model 0x{m:04X}"
       for n, a, b, p, s, m in bad])
for n, a, b, p, r in cases:
    if is_nan(a) or is_nan(b) or is_inf(a) or is_inf(b) or is_zero(a) or is_zero(b):
        continue
    col = r.get("Exact product", "").strip("`")
    want = exact_cell(col)
    if want is None:
        check(False, f"#{n}: exact product column {col!r} unparsed")
    elif want != value(a) * value(b):
        check(False, f"#{n}: exact product column {col} is {value(a) * value(b)}")
    else:
        exact_ok += 1
check(exact_ok == sum(1 for c in cases if not any(f(x) for x in c[1:3]
                                                  for f in (is_nan, is_inf, is_zero))),
      f"the exact-product column is right on all {exact_ok} finite non-zero rows")

# ----------------------------------------------------------- structured classes

print("== 2. Structured classes, model_mul against spec_mul")
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
                yield m | 0x8000, (e << 10) | mb | 0x8000


THRESH = {"overflow": OVERFLOW, "min normal": Fraction(1, 1 << 14),
          "underflow": Fraction(1, 1 << 25)}


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
    for a in range(0x0001, 0x7C00):
        va = value(a)
        for t in THRESH.values():
            b0 = f16_floor(t / va)
            if b0 is None:
                b0 = 0
            for b in range(b0 - 1, b0 + 3):
                if 0x0001 <= b <= 0x7BFF:
                    yield a, b


def c6():
    rnd = random.Random(33)
    for _ in range(200000):
        yield rnd.getrandbits(16), rnd.getrandbits(16)
    for _ in range(100000):
        a = rnd.choice([rnd.randrange(0x0001, 0x7C00), rnd.randrange(0x0001, 0x0400)])
        b = rnd.randrange(0x0001, 0x7C00)
        yield a | (rnd.getrandbits(1) << 15), b | (rnd.getrandbits(1) << 15)


def run_class(name, gen, structured_all=None):

    n = 0
    bad = []
    by_cls = {}
    ties = 0
    for a, b in gen:
        n += 1
        s = spec_mul(a, b)
        m = model_mul(a, b)
        if s != m or model_mul(b, a) != m:
            if len(bad) < 5:
                bad.append(f"0x{a:04X} x 0x{b:04X}: spec 0x{s:04X}, model 0x{m:04X}, "
                           f"swapped 0x{model_mul(b, a):04X}")
            continue
        by_cls[cls(m)] = by_cls.get(cls(m), 0) + 1
        if not (is_nan(a) or is_nan(b) or is_inf(a) or is_inf(b) or is_zero(a) or is_zero(b)):
            ex = abs(value(a) * value(b))
            if ex < OVERFLOW:
                if ex < Fraction(1, 1 << 14):
                    qn = ex / MIN_SUB
                else:
                    e = ex.numerator.bit_length() - ex.denominator.bit_length()
                    if Fraction(2) ** e > ex:
                        e -= 1
                    qn = ex / Fraction(2) ** (e - 10)
                if qn.denominator == 2:
                    ties += 1
    summary = ", ".join(f"{k} {v}" for k, v in sorted(by_cls.items()))
    check(not bad, f"{name}: {n} pairs; results: {summary}; "
          f"exact ties {ties}", bad)
    return n


CLASSES = [
    ("C1 specials x all 65536, both orders", c1),
    ("C2 all exponent-field pairs x 12 x 12 significands, 2 sign cases", c2),
    ("C3 all subnormals x every exponent field x 3 significands", c3),
    ("C4 every positive finite a x the b nearest 3 thresholds", c4),
    ("C6 random: 200000 uniform, 100000 finite non-zero", c6),
]
for name, gen in CLASSES:
    run_class(name, gen())

# C5: ties at [1, 2) x [1, 2): all 2^22 significand pairs through model_mul, the
# exact ties also through spec_mul.

ties_up = ties_down = 0
bad = []
for ma in range(1024):
    a = 0x3C00 | ma
    Ma = 1024 | ma
    for mb in range(1024):
        b = 0x3C00 | mb
        P = Ma * (1024 | mb)
        sh = 11 if P >> 21 else 10                 # bits below the result's LSB
        rem = P & ((1 << sh) - 1)
        if rem != 1 << (sh - 1):
            continue
        n = P >> sh
        m = model_mul(a, b)
        if m != spec_mul(a, b):
            bad.append(f"0x{a:04X} x 0x{b:04X}")
        if m & 1:                                  # ties to even: LSB 0
            bad.append(f"0x{a:04X} x 0x{b:04X}: tie not to even")
        if n & 1:
            ties_up += 1
        else:
            ties_down += 1
check(not bad and ties_up > 0 and ties_down > 0,
      f"C5 every tie among the 2^20 pairs in [1, 2) x [1, 2): {ties_up + ties_down} ties, "
      f"{ties_up} round up (odd below), {ties_down} round down (even below), all to even",
      bad[:5])

# ------------------------------------------------------------------- NumPy

np = None
if args.numpy or args.exhaustive:
    import numpy as np


def np_mul(a, b):
    """NumPy float16 product of bit arrays, as uint16 bits."""
    x = np.asarray(a, dtype=np.uint16).view(np.float16)
    y = np.asarray(b, dtype=np.uint16).view(np.float16)
    with np.errstate(all="ignore"):
        return (x * y).view(np.uint16)


if args.numpy:
    print(f"== 3. NumPy {np.__version__} float16")
    A = np.array([c[1] for c in cases], dtype=np.uint16)
    B = np.array([c[2] for c in cases], dtype=np.uint16)
    R = np_mul(A, B)
    bad = []
    for (n, a, b, p, r), q in zip(cases, R.tolist()):
        if is_nan(p) != is_nan(q) or (not is_nan(p) and p != q):
            bad.append(f"#{n}: 0x{a:04X} x 0x{b:04X}: doc 0x{p:04X}, NumPy 0x{q:04X}")
        col = r.get("NumPy", "")
        if col and hexcell(col) is not None and hexcell(col) != q:
            bad.append(f"#{n}: NumPy column {col}, NumPy gives 0x{q:04X}")
    check(not bad, "the worked cases equal NumPy (a NaN as a class) and the NumPy column", bad)

    for name, gen in CLASSES:
        pairs = list(gen())
        A = np.array([p[0] for p in pairs], dtype=np.uint16)
        B = np.array([p[1] for p in pairs], dtype=np.uint16)
        R = np_mul(A, B).tolist()
        bad = []
        for (a, b), q in zip(pairs, R):
            m = model_mul(a, b)
            if is_nan(m) != is_nan(q) or (not is_nan(m) and m != q):
                bad.append(f"0x{a:04X} x 0x{b:04X}: model 0x{m:04X}, NumPy 0x{q:04X}")
        check(not bad, f"{name.split()[0]}: model_mul = NumPy on all {len(pairs)} pairs "
              "(NaN as a class)", bad[:5])


def vec_tables():
    """Per-pattern tables: class, and the significand normalised to 11 bits with its
    exponent (value = TM * 2^(TE - 10)), so a subnormal operand is normalised first."""
    X = np.arange(0x10000, dtype=np.int32)
    e, m = (X >> 10) & 31, X & 0x3FF
    cl = np.where(e == 31, np.where(m != 0, 3, 2), np.where((e == 0) & (m == 0), 0, 1))
    L = np.zeros_like(m)
    for k in range(11):
        L = np.where(m >= (1 << k), k + 1, L)            # bit length of m
    sh = np.where(e == 0, 11 - L, 0)
    TM = np.where(e == 0, m << sh, 1024 | m).astype(np.int32)
    TE = np.where(e == 0, -14 - sh, e - 15).astype(np.int32)
    return cl.astype(np.int8), TM, TE


def vec_model(a, b, tables):
    """model_mul on uint16 arrays, in the variant of step 3 that normalises a
    subnormal operand first: P is then always in [2^20, 2^22)."""
    CLS, TM, TE = tables
    ai, bi = a.astype(np.int32), b.astype(np.int32)
    ca, cb = CLS[ai], CLS[bi]
    s = (ai ^ bi) & 0x8000
    P = TM[ai] * TM[bi]                                     # step 2
    Es = TE[ai] + TE[bi]
    t = Es + (P >> 21)                                      # step 3
    shift = np.minimum(np.maximum(t, -14) - Es + 10, 24)    # >= 10; 24 leaves n = 0
    n = P >> shift                                          # step 4
    g = (P >> (shift - 1)) & 1
    st = (P & ((1 << (shift - 1)) - 1)) != 0
    n += g & (st | (n & 1))
    bits = np.where(t >= -14, ((t + 15) << 10) + n - 1024, n)   # step 5
    bits = np.minimum(bits, POS_INF)
    out = np.where((ca == 1) & (cb == 1), s | bits, s)     # else a zero operand
    out = np.where((ca == 2) | (cb == 2), s | POS_INF, out)
    nan = (ca == 3) | (cb == 3) | ((ca == 2) & (cb == 0)) | ((ca == 0) & (cb == 2))
    out = np.where(nan, CANON_NAN, out)
    return out.astype(np.uint16)


if args.exhaustive:
    print("== 4. All 2^32 pairs: vectorised model_mul against NumPy float16")

    Ball = np.arange(0x10000, dtype=np.uint32).astype(np.uint16)
    STEP = 16
    tables = vec_tables()
    mism = 0
    examples = []
    counts = {"zero": 0, "subnormal": 0, "normal": 0, "Inf": 0, "NaN": 0}
    nan_bits_ok = True
    noncomm = 0
    K = np.uint64(0x9E3779B97F4A7C15)
    digest = 0
    for a0 in range(0, 0x10000, STEP):
        A = np.repeat(np.arange(a0, a0 + STEP, dtype=np.uint32).astype(np.uint16), 0x10000)
        B = np.tile(Ball, STEP)
        M = vec_model(A, B, tables)
        Q = np_mul(A, B)
        mn = (M & 0x7FFF) > 0x7C00
        qn = (Q & 0x7FFF) > 0x7C00
        diff = (mn != qn) | (~mn & (M != Q))
        k = int(diff.sum())
        if k:
            mism += k
            for i in np.nonzero(diff)[0][:3]:
                examples.append(f"0x{int(A[i]):04X} x 0x{int(B[i]):04X}: model 0x{int(M[i]):04X}, "
                                f"NumPy 0x{int(Q[i]):04X}")
        if mn.any() and not (M[mn] == CANON_NAN).all():
            nan_bits_ok = False
        mag = M & 0x7FFF
        counts["NaN"] += int(mn.sum())
        counts["Inf"] += int((mag == 0x7C00).sum())
        counts["zero"] += int((mag == 0).sum())
        counts["subnormal"] += int(((mag > 0) & (mag < 0x0400)).sum())
        counts["normal"] += int(((mag >= 0x0400) & (mag < 0x7C00)).sum())
        # the digest of anemos_fmul.cpp: sum of (r + 1) * ((a << 16 | b) * K + 1) mod 2^64
        idx = (A.astype(np.uint64) << np.uint64(16)) | B.astype(np.uint64)
        w = idx * K + np.uint64(1)
        digest = (digest + int(np.sum((M.astype(np.uint64) + np.uint64(1)) * w,
                                      dtype=np.uint64))) % (1 << 64)
        # commutativity: the same pairs with the operands swapped
        Ms = vec_model(B, A, tables)
        noncomm += int((Ms != M).sum())
    total = sum(counts.values())
    check(total == 1 << 32, f"{total} pairs")
    check(mism == 0, f"vectorised model_mul = NumPy on every pair (NaN as a class): "
          f"{mism} differ", examples[:5])
    check(nan_bits_ok, "every NaN result of the model is 0x7E00")
    check(noncomm == 0, f"p(a, b) = p(b, a) bit for bit on every pair: {noncomm} differ")
    model_digest = digest
    print(f"       digest of the model's results: {model_digest}")
    print("       result classes: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    n_nan_pat = 2 * 1023
    n_nonnan = 0x10000 - n_nan_pat
    exp_nan = (1 << 32) - n_nonnan ** 2 + 8
    check(counts["NaN"] == exp_nan,
          f"NaN results = pairs with a NaN operand + the 8 Inf x 0 pairs = {exp_nan}")

# ------------------------------------------------------------------- ANEMOS

if args.anemos:
    print(f"== 5. ANEMOS half 2.2.0, from {args.anemos.name}")
    kv, diffs, case_out, inv_bits = {}, [], {}, {}
    for line in args.anemos.read_text().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "differ" and len(f) > 2:
            diffs.append(line)
        elif f[0] == "case":
            case_out[(int(f[1], 16), int(f[2], 16))] = int(f[3], 16)
        elif f[0] == "nan_invalid_bits":
            inv_bits[int(f[1], 16)] = int(f[2])
        else:
            kv[f[0]] = int(f[1])
    check(kv.get("pairs") == 1 << 32, f"ANEMOS ran all 2^32 pairs: {kv.get('pairs')}")
    n_nonnan = 0x10000 - 2046
    exp_nan = (1 << 32) - n_nonnan ** 2 + 8
    check(kv.get("differ") == 0 and not diffs,
          f"ANEMOS = the reference on every non-NaN result: {kv.get('differ')} differ", diffs[:5])
    check(kv.get("nan_both") == exp_nan,
          f"ANEMOS gives a NaN exactly where the spec does: {kv.get('nan_both')} = {exp_nan}")
    if args.exhaustive:
        check(kv.get("digest_anemos") == model_digest,
              "ANEMOS's 2^32 results, NaN as 0x7E00, have the digest of bankside's model: "
              f"{kv.get('digest_anemos')}")
        check(kv.get("digest_ref") == model_digest,
              "so do the _Float16 reference's: " + str(kv.get("digest_ref")))
    check(inv_bits == {0x7FFF: 8}, f"ANEMOS's NaN for Inf x 0 (8 pairs) is 0x7FFF: {inv_bits}")
    check(kv.get("nan_operand_distinct_bits", 0) > 1,
          f"ANEMOS's NaN for a NaN operand is not one pattern: "
          f"{kv.get('nan_operand_distinct_bits')} distinct patterns (propagated)")
    # the worked cases: same as the spec except NaN bits; the doc's ANEMOS column
    bad = []
    for n, a, b, p, r in cases:
        q = case_out.get((a, b))
        if q is None:
            bad.append(f"#{n}: not in the ANEMOS output")
            continue
        if is_nan(p) != is_nan(q) or (not is_nan(p) and p != q):
            bad.append(f"#{n}: 0x{a:04X} x 0x{b:04X}: spec 0x{p:04X}, ANEMOS 0x{q:04X}")
        col = r.get("ANEMOS", "")
        want = hexcell(col) if hexcell(col) is not None else (p if col == "same" else None)
        if want != q:
            bad.append(f"#{n}: ANEMOS column {col!r}, ANEMOS gives 0x{q:04X}")
    check(not bad, "every worked case matches ANEMOS's run and the ANEMOS column", bad)

print("PASS" if failures == 0 else f"{failures} check(s) FAILED")
sys.exit(1 if failures else 0)
