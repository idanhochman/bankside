"""Check the ReLU ([TOP-FP-8]) and NaN-result ([TOP-FP-6]) worked cases.

Models, at the bit level:
  - bankside ReLU: a 2:1 multiplexer on the sign bit [TOP-FP-8] (the paper's rule)
  - ANEMOS ReLU:   `in < 0 ? +0 : in` as an IEEE comparison (src/grf.cpp)
  - bankside NaN:  every arithmetic NaN result is 0x7E00 [TOP-FP-6]
  - ANEMOS NaN:    half 2.2.0's rule (src/half.hpp): the first NaN operand with
                   its quiet bit set, or 0x7FFF for an invalid operation

and checks that:
  1. the ReLU and NaN tables in theory_of_operation.md match the models;
  2. over all 65536 inputs the two ReLU rules differ exactly on 0x8000 and
     0xFC01..0xFFFF, as the spec says;
  3. with --anemos FILE: the output of anemos_fp.cpp (ANEMOS's own half.hpp,
     compiled and run) agrees with the ANEMOS models and the tables;
  4. with --numpy: the NumPy column matches NumPy on this host, and
     np.where(np.signbit(x), 0, x) matches [TOP-FP-8] on all 65536 inputs.
     Needs NumPy, which .venv lacks.

Run from the repo root:
  .venv/bin/python src/top/doc/examples/fp_relu_nan.py
  python3 src/top/doc/examples/fp_relu_nan.py --numpy --anemos src/top/doc/examples/anemos_fp.out

Exits non-zero if any check fails.
"""

import argparse
import pathlib
import re
import struct
import sys

DOC = pathlib.Path(__file__).resolve().parent.parent / "theory_of_operation.md"

failures = 0

ap = argparse.ArgumentParser()
ap.add_argument("--anemos", type=pathlib.Path,
                help="output of anemos_fp.cpp, built against ANEMOS's half.hpp")
ap.add_argument("--numpy", action="store_true", help="also run the NumPy checks")
args = ap.parse_args()


def check(cond, msg, detail=()):
    global failures
    print(("ok   " if cond else "FAIL ") + msg)
    for d in detail:
        print("       " + d)
    if not cond:
        failures += 1


def value(bits):
    return struct.unpack("<e", struct.pack("<H", bits))[0]


def is_nan(bits):
    return (bits & 0x7FFF) > 0x7C00


def is_inf(bits):
    return (bits & 0x7FFF) == 0x7C00


def relu_bankside(bits):          # [TOP-FP-8]: sign bit selects +0
    return 0x0000 if bits & 0x8000 else bits


def relu_anemos(bits):            # grf.cpp: in < 0 ? half_cast<half>(0.0) : in
    return 0x0000 if value(bits) < 0 else bits


def invalid(op, a, b):
    if op == "ADD":
        return is_inf(a) and is_inf(b) and (a ^ b) & 0x8000
    return (is_inf(a) and (b & 0x7FFF) == 0) or (is_inf(b) and (a & 0x7FFF) == 0)


def nan_bankside(op, a, b):       # [TOP-FP-6]
    assert is_nan(a) or is_nan(b) or invalid(op, a, b)
    return 0x7E00


def nan_anemos(op, a, b):         # half.hpp detail::signal() / detail::invalid()
    if is_nan(a):
        return a | 0x0200
    if is_nan(b):
        return b | 0x0200
    assert invalid(op, a, b)
    return 0x7FFF


H = r"(0x[0-9A-F]{4})"
doc = DOC.read_text()
relu_rows = [(int(i, 16), int(p, 16), int(n, 16)) for i, p, n in
             re.findall(rf"^\| {H} \| [^|]+ \| {H} \| {H} \|$", doc, re.M)]
nan_rows = [(op, int(a, 16), int(b, 16), int(x, 16), int(y, 16), int(z, 16))
            for op, a, b, x, y, z in
            re.findall(rf"^\| (ADD|MUL) {H}, {H} \| [^|]+ \| {H} \| {H} \| {H} \|$", doc, re.M)]

# 1. The spec's tables against the models.
bad = [f"0x{i:04X}: spec {p:#06x}/{n:#06x}, model {relu_bankside(i):#06x}/{relu_anemos(i):#06x}"
       for i, p, n in relu_rows if (p, n) != (relu_bankside(i), relu_anemos(i))]
check(len(relu_rows) >= 10 and not bad,
      f"ReLU table: {len(relu_rows)} rows match the sign-bit and value < 0 models", bad)
bad = [f"{op} 0x{a:04X}, 0x{b:04X}: spec {x:#06x}/{y:#06x}, model "
       f"{nan_bankside(op, a, b):#06x}/{nan_anemos(op, a, b):#06x}"
       for op, a, b, x, y, _ in nan_rows if (x, y) != (nan_bankside(op, a, b), nan_anemos(op, a, b))]
check(len(nan_rows) >= 7 and not bad,
      f"NaN table: {len(nan_rows)} rows match [TOP-FP-6] and the half 2.2.0 rule", bad)
differ = sum(1 for op, a, b, _, y, z in nan_rows if y != z)
check(f"on 4 of the 7\n  cases" in doc and differ == 4 and len(nan_rows) == 7,
      f"half 2.2.0 and NumPy (as tabled) differ on {differ} of {len(nan_rows)} NaN cases, as the spec says")

# 2. Exhaustive ReLU comparison.
diff = [x for x in range(1 << 16) if relu_bankside(x) != relu_anemos(x)]
expected = [0x8000] + list(range(0xFC01, 0x10000))
check(diff == expected and "differ on 1024 of the 65536" in doc,
      f"ReLU rules differ on {len(diff)} of 65536 inputs: 0x8000 and 0xFC01..0xFFFF")

# 3. ANEMOS, compiled and run.
if args.anemos:
    run = args.anemos.read_text()
    got_relu = {int(i, 16): int(o, 16) for i, o in re.findall(rf"^RELU {H} -> {H}$", run, re.M)}
    got_nan = {(op, int(a, 16), int(b, 16)): int(r, 16)
               for op, a, b, r in re.findall(rf"^(ADD|MUL) {H} {H} -> {H}$", run, re.M)}
    bad = [f"RELU 0x{i:04X}: run {got_relu.get(i)}, model {relu_anemos(i):#06x}"
           for i, _, n in relu_rows if got_relu.get(i) != relu_anemos(i)]
    bad += [f"{op} 0x{a:04X} 0x{b:04X}: run {got_nan.get((op, a, b))}, table {y:#06x}"
            for op, a, b, _, y, _ in nan_rows if got_nan.get((op, a, b)) != y]
    check(not bad and got_relu and got_nan,
          f"ANEMOS run ({args.anemos.name}): {len(got_relu)} ReLU and {len(got_nan)} "
          "NaN cases match the ANEMOS columns", bad)
else:
    print("skip ANEMOS run (pass --anemos anemos_fp.out)")

# 4. NumPy on this host.
if args.numpy:
    import platform
    import warnings

    import numpy as np
    warnings.simplefilter("ignore")

    def f16(b):
        return np.array([b], dtype=np.uint16).view(np.float16)

    def bits(x):
        return int(np.asarray(x, dtype=np.float16).reshape(1).view(np.uint16)[0])

    host = f"NumPy {np.__version__}, {platform.machine()}"
    bad = []
    for op, a, b, _, _, z in nan_rows:
        r = bits(f16(a) + f16(b) if op == "ADD" else f16(a) * f16(b))
        if r != z:
            bad.append(f"{op} 0x{a:04X}, 0x{b:04X}: {host} gives 0x{r:04X}, table 0x{z:04X}")
    check(not bad and f"NumPy {np.__version__}, x86-64" in doc,
          f"NumPy column matches {host}", bad)
    allx = np.arange(1 << 16, dtype=np.uint32).astype(np.uint16).view(np.float16)
    ref = np.where(np.signbit(allx), np.float16(0), allx).view(np.uint16)
    want = np.array([relu_bankside(x) for x in range(1 << 16)], dtype=np.uint16)
    check(bool((ref == want).all()),
          "np.where(np.signbit(x), 0, x) == [TOP-FP-8] on all 65536 inputs")
    mx = np.maximum(allx, np.float16(0)).view(np.uint16)
    check(int(mx[0x8000]) == 0x8000 and all(is_nan(int(mx[x])) for x in (0x7E00, 0xFE00)),
          f"np.maximum(x, 0): -0 -> 0x{int(mx[0x8000]):04X}, NaNs stay NaN "
          f"({int((mx != want).sum())} inputs differ from [TOP-FP-8])")
else:
    print("skip NumPy (pass --numpy; needs NumPy)")

sys.exit(1 if failures else 0)
