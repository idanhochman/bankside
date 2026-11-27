# fp16_mul: testplan

Owner: DV. Readers: everyone, except the designer while writing RTL.

This plan is written from the spec alone ([`../doc/README.md`](../doc/README.md),
with [`fmul_check.out`](../doc/examples/fmul_check.out)) and from [VER-4]. It
carries out VER-4 for the multiplier. It says what each test applies, what it
compares against, how many vectors it runs and why. The tests and the oracle
environment are written to this plan in #86, and run against the RTL in #74.
Until then nothing below has run against the RTL.

Every requirement ID in `../doc/` appears in [Requirement
coverage](#requirement-coverage), with the tests that check it. A requirement
with no test is listed as uncovered, with the reason.

[VER-4]: ../../top/dv/README.md#fp16-units
[VER-15]: ../../top/dv/README.md#simulation-runs-and-power-up-values
[TOP-FP-6]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-ARCH-9]: ../../top/doc/theory_of_operation.md#register-files
[FMUL-1]: ../doc/README.md#ports
[FMUL-2]: ../doc/README.md#ports
[FMUL-3]: ../doc/README.md#behaviour
[FMUL-4]: ../doc/README.md#operand-classes
[FMUL-5]: ../doc/README.md#the-result
[FMUL-6]: ../doc/README.md#the-result
[FMUL-7]: ../doc/README.md#the-result
[FMUL-8]: ../doc/README.md#the-result
[FMUL-9]: ../doc/README.md#the-result
[FMUL-10]: ../doc/README.md#the-result
[FMUL-11]: ../doc/README.md#timing
[DP-17]: ../../pcu_datapath/doc/README.md#timing

## Requirement coverage

| Requirement | What it asks | Test(s) | Status |
|---|---|---|---|
| [FMUL-1] | ports `a`, `b`, `p`, 16 bits each; no clock, reset, enable, mode or flag port; no parameters | `test_ports`; `opendv lint fp16_mul_wide` (an extra, missing, mis-sized or mis-directed port fails it, [Harness](#harness)) | planned. **No parameters** is uncovered: the lint check doesn't catch a parameter (confirmed on a stub), and cocotb shows a parameter and an internal `localparam` alike, as a constant handle, so a test can't tell them apart. Design review checks it; `test_ports` logs any constant handles it finds |
| [FMUL-2] | 16 instances `g_lane[l].u_mul` in `pcu_datapath`, lane slicing | none here | **uncovered here**: the parent's connection. The `pcu_datapath` unit testplan (M4) and VER-16 at `top` check it |
| [FMUL-3] | `p` is a function of `a` and `b` alone: no state, latch or memory; no X/Z out for 2-state inputs | `test_no_state`; every test checks its first vector at power-up and applies its vectors in an order shuffled by the seed; the `opendv lint` gate, where an inferred latch should be a LATCH warning (not yet tried on a stub) | planned. **The X/Z part is uncovered**: Verilator is 2-state, so no simulation here can show an X or Z |
| [FMUL-4] | five operand classes, by bits alone; no flush to zero; sNaN and qNaN alike | `test_class_matrix`, `test_subnormals`, `test_nan_classes` | planned |
| [FMUL-5] | result by operand class, both orders | `test_class_matrix`, `test_specials`, `test_worked_cases` (#30 to #43) | planned |
| [FMUL-6] | sign is `a[15]` XOR `b[15]` on every non-NaN result; NaN sign 0 | `test_class_matrix` (every class pair, all four sign combinations), `test_worked_cases` (#3, #13, #27, #30 to #34, #36, #40), every oracle comparison (bit for bit) | planned |
| [FMUL-7] | the exact product rounded once, RNE, subnormals, overflow at 65520 | `test_worked_cases` (#1 to #29), `test_ties`, `test_bounds`, `test_exponent_grid`, `test_subnormals`, `test_sweep`, `test_exhaustive` | planned |
| [FMUL-8] | every NaN result is exactly 0x7E00 | `test_nan_classes`, `test_specials`, `test_worked_cases` (#37 to #43); the [NaN rule](#the-nan-comparison) in every comparison | planned |
| [FMUL-9] | no flags or other outputs | `test_ports` and the lint check (`p` is the only output). That the result follows from [FMUL-7] alone is shown by every result check | planned |
| [FMUL-10] | `p(a, b)` = `p(b, a)` bit for bit, NaN included | `test_swapped` (no oracle: the two results compared with each other); `test_worked_cases` #42 against #43, and every row run swapped; `test_specials` and `test_exhaustive` run both orders | planned |
| [FMUL-11] | combinational, one stage; paths `a`, `b` to `p` only; S3 timing | Every test reads `p` with no clock anywhere (none exists, [FMUL-1]); `test_no_state` | partly planned. **The delay is uncovered here**: it belongs to the M2 synthesis run on ASAP7 (designer, `syn/`) and to [DP-17]'s S3 path in `pcu_datapath` |
| [VER-4] | unit verified alone against NumPy `float16`: directed specials, a weighted random sweep, NaNs bit-exact against 0x7E00, every NaN operand class | all tests below | planned. VER-4's Inf − Inf case is `fp16_add`'s |

## Harness

`fp16_mul` has no clock ([FMUL-1]). A test sets `a` and `b`, waits 1 ns of
simulated time (`Timer(1, "ns")`) so that Verilator evaluates the logic, and
reads `p`. There is no clock, reset or handshake anywhere in the testbench.

**Clockless driving, confirmed.** A throwaway run, not committed, checked that
opendv 0.1.2 can drive a clockless combinational toplevel. It used my own stub
with `fp16_mul`'s port shape (`p = a ^ b`), not the bankside RTL. Its results:

- 200000 vectors applied and checked one at a time, PASS: 13000 to 16000
  vectors/s in one simulator process (Verilator 5.052, cocotb 2.1.0).
- With a 1024-lane stub (each lane its own `a`, `b` and `p` slice, 16 bits
  each), driving and reading the lanes together as one wide integer per step
  and checking them with NumPy, PASS: 0.52M vectors/s. 4096 lanes gave
  0.60M/s, and 256 lanes gave 0.38M/s.
- The FST dump of a clockless run reads with `waves list` (`a`, `b`, `p`).
- NumPy 2.5.1 is in the opendv image, the same version the spec's NumPy
  column used. `OPENDV_SEED` and `COCOTB_RANDOM_SEED` both equal the seed.
- `regress` runs each cocotb test function in a module as its own test, in its
  own process.

These rates come from a stub. The real multiplier costs more per evaluation.
#74 measures the rates on the RTL and may change the lane count. That would
change run times only, not which pairs are covered.

**Two opendv targets**, both instantiating the designer's `rtl/fp16_mul.f`:

| Target | Toplevel | Where | For |
|---|---|---|---|
| `fp16_mul` | `fp16_mul` itself | `src/fp16_mul/opendv.yaml`, tests in `dv/tests/` | the unit as the toplevel: ports, small directed sets, the random sweeps |
| `fp16_mul_wide` | `fp16_mul_wide`, a DV wrapper of 1024 instances | `src/fp16_mul/dv/wide/` (`opendv.yaml`, the wrapper `.sv`, a filelist that pulls in `-F ../../rtl/fp16_mul.f`), listed in the root `opendv.yaml` | the large structured sets and the exhaustive slices, at about 40 times the single-lane rate |

The wrapper's ports are `a`, `b` and `p`, each 16 × 1024 bits. Instance *l*
takes bits `[16l+15 : 16l]` of each, connected by name as `.a()`, `.b()` and
`.p()` only. Every lane gets its own operands and is checked on its own, so a
wiring slip in the wrapper shows up as mismatches. It can't hide a bug.

The wrapper also checks [FMUL-1] structurally. `opendv lint fp16_mul_wide`
runs `verilator -Wall`, where the wrapper connects exactly `a`, `b` and `p`.
The same throwaway run linted such a wrapper around deliberately wrong stubs
(opendv 0.1.2, Verilator 5.052). Each wrong port failed lint:

| Stub's ports | Lint result |
|---|---|
| `a`, `b`, `p`, 16 bits | clean |
| an extra input `clk` | PINMISSING warning, fails |
| an extra output `inv` | PINMISSING warning, fails |
| no `b` | PINNOTFOUND error |
| `p` 15 bits | WIDTHTRUNC warning, fails |
| `p` an input | UNDRIVEN warning, fails |
| `a` an output | ASSIGNIN error |
| a parameter `W` = 16 | clean: **not caught** |

#86 repeats these on the review page.

## The oracle

- **NumPy `float16`, one rounding.** The expected `p` is
  `(a.view(np.float16) * b.view(np.float16)).view(np.uint16)` on `uint16`
  arrays, under `np.errstate(all="ignore")`. The spec shows why this is a
  valid oracle: the product is formed exactly in float32 and rounded once to
  binary16 ([how the cases are checked](../doc/README.md#how-the-cases-are-checked)).
  It agrees with the spec's own models on all 2³² pairs, with NaN treated as a
  class.
- **Not the RTL, not the spec's scripts.** The oracle code is DV's, in
  `dv/env/`. It doesn't import `doc/examples/fmul_check.py`. The stimulus sets
  copied from the spec's check table (C1 to C5) are built from that table's
  text and checked against its printed counts (below).
- **A second expected value on the worked cases.** `test_worked_cases`
  compares `p` both with the oracle and with the literal `p` column of the
  spec's table, so an oracle fault can't pass on those rows.
- **Oracle self-check, with no RTL** (#86): a script in `dv/env/`, run with
  plain Python and no simulator, checks:
  - the oracle against the 43 worked cases: their `p` column, with the NaN
    rule, and their NumPy column, raw bits included, so the image's NumPy
    behaves like the one the spec used;
  - the C1 to C5 stimulus builders against the pair counts and result-class
    counts in `fmul_check.out`, e.g. C1: 1703936 pairs, Inf 253952, NaN
    1196032, zero 253952. This checks that the test applies the sets the
    spec describes.

  Each cocotb test also reruns the 43-row check before its first vector, which
  takes a few milliseconds. A broken oracle then fails loudly instead of
  agreeing with a broken RTL.

### The NaN comparison

NumPy says only *whether* a result is a NaN. Its NaN bits are the host's
(0xFE00 for 0 × Inf, a propagated payload otherwise; see the NumPy column of
worked cases #37 to #43). So, per [TOP-FP-6] and [FMUL-8]:

- if the oracle's result is a NaN (exponent field 31, *m* ≠ 0), the expected
  bits are exactly **0x7E00**, and `p` must equal 0x7E00 bit for bit;
- otherwise `p` must equal the oracle's bits exactly. In particular, +0 and −0
  are told apart, as are +Inf and −Inf.

So a NaN class match isn't enough: 0x7E01, 0xFE00 or 0x7FFF fails, and so does
a NaN where the oracle has a number, or a number where it has a NaN. A failure
prints `a`, `b`, `p`, the expected bits and the oracle's raw bits, the lane
(wide target), the seed and the opendv `rerun:` line.

## Directed tests

Each directed test is deterministic in *what* it applies. The seed shuffles
the order of the vectors and, on the wide target, which lane each pair lands
in. So every seed gives a different sequence (for [FMUL-3]), and a failure
still replays from its seed. Pair counts are ordered pairs (one vector each).

| Test | Target | Stimulus | Pairs | Checks | IDs |
|---|---|---|---|---|---|
| `test_ports` | `fp16_mul` | Signal handles `a`, `b` and `p` exist and are 16 bits wide. No toplevel handle is named `clk`, `clock`, `rst`, `rst_n`, `reset`, `en`, `enable`, `flags`, `invalid`, `overflow`, `underflow` or `inexact`. cocotb also sees internal signals and can't tell a port's direction, so the [lint check](#harness) is the real check of the port list. One vector (#1) | 1 | as stated | FMUL-1, FMUL-9 |
| `test_worked_cases` | `fp16_mul` | The spec's 43 worked cases, each in the given order and swapped | 86 | `p` = the spec's `p` column **and** the oracle; #42 and #43 give the same `p` | FMUL-5 to FMUL-8, FMUL-10 |
| `test_class_matrix` | `fp16_mul` | 13 operands, each with both signs (26): zero 0x0000; subnormals 0x0001 (smallest), 0x0155, 0x03FF (largest); normals 0x0400 (smallest), 0x3C00, 0x3E00, 0x7BFF (largest); Inf 0x7C00; NaNs 0x7C01, 0x7DFF (sNaN), 0x7E00, 0x7FFF (qNaN). Every ordered pair | 676 | the oracle; and, separately from it, the result's class and sign from the [FMUL-5] table and [FMUL-6], coded directly (so the class check doesn't rest on NumPy) | FMUL-4, FMUL-5, FMUL-6, FMUL-8 |
| `test_ties` | `fp16_mul` | Every exact tie of these families: C5's 3367 ties in [1, 2) × [1, 2) (1692 with odd *m* below, 1675 with even, the counts asserted); the 1024 subnormal-range ties *x* × 0x3800 for every odd *m* with *x* subnormal or in [2⁻¹⁴, 2⁻¹³), each with both signs of *x* (2048); every pair with exact product 65520 (352) or 2⁻²⁵ (24), each with four sign combinations (1504) | 6919 | the oracle; and, separately from it, the result's *m* is even (0 and Inf count as even) | FMUL-7, FMUL-6 |
| `test_no_state` | `fp16_mul` | The 43 worked-case pairs, each applied right after each of 16 predecessor pairs (a NaN operand, 0 × Inf, ±Inf, ±0, 65504², the smallest subnormal product, a tie, …, and the pair itself) | 43 × 16 = 688 sequences, 1376 vectors | the same `p` whatever came before, and = the oracle; the first vector of every test, at power-up, is checked like any other | FMUL-3, FMUL-11 |
| `test_specials` | `fp16_mul_wide` | C1: each of the spec's 13 special operands (±0, ±Inf, NaNs 0x7C01, 0x7D55, 0x7DFF, 0x7E00, 0x7FFF, 0xFC01, 0xFDFF, 0xFE00, 0xFFFF) against all 65536 patterns, in both orders | 1703936 | the oracle; result classes = `fmul_check.out` C1 | FMUL-5, FMUL-8, FMUL-10 |
| `test_nan_classes` | `fp16_mul_wide` | Every NaN pattern (2046: quiet and signalling, both signs, every payload) against 16 non-NaN operands (±0, ±0x0001, ±0x0155, ±0x03FF, ±0x0400, ±0x3C00, ±0x7BFF, ±Inf) in both orders (65472), and every NaN against every NaN (4186116) | 4251588 | the oracle with the NaN rule: every result 0x7E00 | FMUL-4, FMUL-8, VER-4 |
| `test_exponent_grid` | `fp16_mul_wide` | C2: every pair of exponent fields 0 … 30, each with 12 values of *m* (0, 1, 2, 0x0AA, 0x155, 0x1FF, 0x200, 0x2AA, 0x300, 0x3FD, 0x3FE, 0x3FF), with equal and opposite signs | 276768 | the oracle; result classes = C2 | FMUL-7, FMUL-6 |
| `test_subnormals` | `fp16_mul_wide` | C3: every subnormal, both signs, with *m* in {0, 0x155, 0x3FF} at every exponent field 0 … 30 | 190278 | the oracle; result classes = C3 | FMUL-4, FMUL-7 |
| `test_bounds` | `fp16_mul_wide` | C4: every positive finite non-zero `a`, with the 4 patterns of `b` nearest each of 65520/`a`, 2⁻¹⁴/`a` and 2⁻²⁵/`a`, where finite and non-zero | 301048 | the oracle; result classes = C4 | FMUL-7 |

**The worked cases by what they show** (all 43 are in `test_worked_cases`):

| Rows | What |
|---|---|
| #1 to #3 | exact products; #2 has the product's leading 1 at bit 21; #3 the sign |
| #4 to #8 | rounding: below half (#4), ties up to even (#5) and down to even (#6), just below a tie (#7), a carry into the exponent (#8) |
| #9 to #14 | the overflow bound: 65504 exact (#9), overflow (#10, #13, #14), the tie at exactly 65520 to Inf (#11), the largest product below 65520 to 65504 (#12) |
| #15 to #29 | the normal and subnormal range: exact subnormal (#16), subnormal ties (#17, #18, #23), rounding up to the smallest normal (#19, #29), the 2⁻²⁵ tie to 0 (#21) and just above it (#22), underflow to 0 (#25, #26) and to −0 (#27), subnormal × normal to a normal (#24, #28) |
| #30 to #36 | zeros and infinities: −0 and +0 (#30 to #33), Inf by the smallest subnormal (#35), −Inf (#34), ±Inf (#36) |
| #37, #38 | invalid: 0 × Inf in both orders, with signs, to 0x7E00 (NumPy gives 0xFE00) |
| #39 to #43 | NaN operands: sNaN not quietened into 0x7E01 (#39), −qNaN beats zero (#40), the payload dropped (#41), two NaNs (#42) and the same pair swapped (#43) |

## Sweeps

| Test | Target | Per seed | Per default regression (8 seeds) | Estimated time per seed |
|---|---|---|---|---|
| `test_sweep` | `fp16_mul` | 2¹⁸ = 262144 weighted random pairs | 2.1M | about 20 s |
| `test_swapped` | `fp16_mul` | 2¹⁷ = 131072 weighted random pairs, each applied as (`a`, `b`) and then (`b`, `a`): 262144 vectors | 1.0M pairs | about 20 s |
| `test_exhaustive` | `fp16_mul_wide` | one slice of 2²⁴ = 16777216 pairs | 8 slices, 134M pairs, 3.1% of 2³² | about 35 s |

Time estimates are from the stub rates under [Harness](#harness). A full
default regression of both targets is then about 15 minutes of CPU, about
4 minutes on a 4-core host, plus the builds.

**`test_sweep`, weighted random.** Each operand is drawn by class, with these
weights:

| Draw | Weight |
|---|---|
| any of the 65536 patterns, uniform | 20% |
| normal: random sign, *e* in 1 … 30, *m* uniform | 40% |
| subnormal: random sign, *m* in 1 … 1023 | 15% |
| *e* in 0 … 30 with *m* from C2's 12 edge values | 10% |
| ±0, ±Inf, NaN (random sign and payload) | 5% each |

Then 20% of the pairs are replaced by a constructed pair. The `a` is a random
finite non-zero operand. The `b` is one of the 4 patterns nearest 65520/`a`,
2⁻¹⁴/`a` or 2⁻²⁵/`a` (C4's construction, around a random `a`), or the pair is
a tie from `test_ties`' families, with `a`'s exponent moved by a random amount
where the product stays a tie. The uniform 20% keeps every pattern possible,
so the weighting can't exclude anything.

The test also checks its own stimulus. It fails if fewer than 1% of its results
fall in any of the five classes (zero, subnormal, normal, Inf, NaN), or in
either sign of each non-NaN class, or if fewer than 0.5% of its pairs are exact
ties. So the weighting can't drift until a class goes unseen.

**`test_swapped`** ([FMUL-10]): the same draws. Each pair is applied in both
orders, and the two `p` are compared with each other, bit for bit and with no
oracle. This is the "one swapped sweep" of the spec's choice table. A NaN must
match too (both 0x7E00). The two results are also checked against the oracle.

**`test_exhaustive`, all 2³² pairs in 256 slices.** Slice *k* = `OPENDV_SEED`
mod 256 covers every `a` in [256*k*, 256*k* + 255] against every `b`. The
results are checked against the oracle with the NaN rule. An ordinary
regression runs 8 random slices. The full sweep is one command:

```bash
src/common/util/opendv regress 'fp16_mul_wide:test_exhaustive' --seed-list $(seq 0 255)
```

Estimated at about 2.5 hours of CPU, or about 40 minutes on 4 workers. It is
run once in #74 and again on every RTL change to `fp16_mul`, and the review
page records the run. Every ordered pair is checked against a symmetric
expected value (NaN → 0x7E00), so the full run also proves [FMUL-10] on every
pair.

**Why these sizes.**

- All 2³² pairs on the single-lane toplevel would take about 80 CPU-hours at
  14000 vectors/s. That isn't practical for any regression.
- The 1024-lane wrapper brings this to about 2.5 CPU-hours, practical for a
  deliberate full run but too long for every regression and for CI. So the full
  run is opt-in, and each regression takes 8 random slices.
- The structured sets (`test_specials` to `test_bounds`, 6.7M pairs, about 15 s
  on the wide target) run every time. They cover every operand class
  pair, every exponent pair, every subnormal and every rounding bound
  deliberately, not by chance.
- The single-lane sweeps are kept small (2¹⁸ per seed, so each test stays
  under half a minute). Their job is random class mixes and random vector
  orders on the real toplevel, not volume.
- More seeds (`--seeds N`) scale every sweep linearly, with no change to the
  tests.

## Seeds and reproducibility

- Every test reads its randomness from cocotb's `random`, which opendv seeds,
  or from `OPENDV_SEED`. No test picks its own seed. Every failure prints the
  seed and the `rerun:` line.
- The root `opendv.yaml`'s power-up settings ([TOP-ARCH-9], [VER-15]) apply to
  both targets. `fp16_mul` has no state, so the power-up values should change
  nothing. A first-vector failure that comes and goes with the seed points at
  hidden state ([FMUL-3]).
- One cocotb test function per test module, named like the module
  (`tests/test_ties.py` holds `test_ties`). That way `opendv targets`, `run`
  and `regress` all show the same names.

## Review pages (in #86)

Pages go in `dv/doc/`, with GTKWave images and markers (the waves skill). Each
page shows a run where the check fails on purpose.

| Page | Shows | Deliberate failure |
|---|---|---|
| worked cases and the NaN rule | a few worked cases (#5, #11, #21, #37, #39) on `a`, `b` and `p`, with markers on each vector and its check | one expected bit flipped in a copy of the table; the NaN rule loosened to a class match, then a stub that gives 0x7E01 for #39 is caught by the real rule |
| the wide harness | a toy trace: 4 pairs, the lanes they land in for a seed, the packed integers, the oracle and the per-lane check | a stub wrapper with two lanes swapped |
| sweeps and exhaustive slices | the seed → slice mapping, the class-count self-check, the results of the full 256-slice run | a weighting that removes subnormals trips the class-count check |
| ports and lint | `opendv lint fp16_mul_wide` on the RTL, and on throwaway stubs with an extra port, a 15-bit `p` and an inverted direction | the three stubs |

## Not covered, or not yet verified

- [FMUL-3]'s X/Z clause, [FMUL-1]'s "no parameters" and [FMUL-11]'s delay are
  uncovered here, as the table above says. [FMUL-2] belongs to the parent.
- Everything in this plan is unverified until #86 writes it and #74 runs it.
  The run times are estimates from a stub.
- An RTL-against-ANEMOS check isn't run at unit level. The spec ran ANEMOS's
  `half` on all 2³² pairs and found it equal to NumPy on every non-NaN result
  ([ANEMOS compared](../doc/README.md#anemos-compared)), so a full pass
  against NumPy implies agreement with ANEMOS outside NaN bits. VER-2 compares
  them at kernel level.

- `env/`: the verification environment (the oracle and its self-check, the
  stimulus builders).
- `tests/`: the cocotb tests on the `fp16_mul` target.
- `wide/`: the `fp16_mul_wide` target (the wrapper and its tests).
- `doc/`: review pages.
