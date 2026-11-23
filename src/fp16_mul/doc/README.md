# fp16_mul: specification

Owner: architect. Readers: everyone. The designer and DV each build from this
alone, so anything they would have to guess belongs here.

Every rule is tagged `[paper]`, `[ANEMOS]` or `[bankside]`, and every rule a
test can check has an ID: `[FMUL-1]`, `[FMUL-2]`, ...

## Overview

`fp16_mul` is one lane of the S3 multiply: a purely combinational IEEE 754
binary16 multiplier. It takes two 16-bit operands and gives their product,
correctly rounded to nearest, ties to even, with subnormals in and out,
overflow to ±Inf, and every NaN result the canonical 0x7E00. It has no clock,
no reset, no state and no other output: no exception flags.

`pcu_datapath` has 16 instances, one per lane, and defines how they connect
([DP-10], [DP-16], [DP-17]); this doc defines the unit's own ports, function
and timing. The rules it carries out are those of the top spec:

| Top rule | What it asks of `fp16_mul` | Here |
|---|---|---|
| [TOP-HIER-3] | one lane, purely combinational: no clock, no reset, no state | [FMUL-1], [FMUL-3], [FMUL-11] |
| [TOP-FP-1] | IEEE 754-2019 binary16 | [FMUL-4] |
| [TOP-FP-2] | correctly rounded, round to nearest, ties to even | [FMUL-7] |
| [TOP-FP-4] | subnormals in and out, no flush to zero; overflow to ±Inf by RNE | [FMUL-4], [FMUL-7] |
| [TOP-FP-5] | 0 × ±Inf = NaN, a NaN operand gives a NaN, the sign is the XOR | [FMUL-5], [FMUL-6] |
| [TOP-FP-6] | every NaN result is 0x7E00 | [FMUL-8] |
| [TOP-FP-7] | no exception flags | [FMUL-9] |

[TOP-ARCH-3]: ../../top/doc/theory_of_operation.md#architecture
[TOP-FP-1]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-FP-2]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-FP-4]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-FP-5]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-FP-6]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-FP-7]: ../../top/doc/theory_of_operation.md#fp16-arithmetic
[TOP-ARCH-9]: ../../top/doc/theory_of_operation.md#register-files
[TOP-HAZ-2]: ../../top/doc/theory_of_operation.md#hazards
[TOP-HAZ-4]: ../../top/doc/theory_of_operation.md#hazards
[TOP-HIER-3]: ../../top/doc/hierarchy.md#fp16-units
[DP-10]: ../../pcu_datapath/doc/README.md#s3-and-s4-the-lanes
[DP-16]: ../../pcu_datapath/doc/README.md#lanes-and-the-fp16-units
[DP-17]: ../../pcu_datapath/doc/README.md#timing
[VER-2]: ../../top/dv/README.md#anemos-kernel-translation-ver-2
[VER-4]: ../../top/dv/README.md#fp16-units

**Sources.** The papers give the unit's place, not its arithmetic. ISCA 2021
(Section III-A) has "a pair of 16 FP16 multipliers and adders" in the 16-wide
SIMD FPU, and Section IV-B makes MULT the third of five pipeline stages; they
say nothing on rounding, subnormals, overflow or NaNs. ANEMOS
(github.com/gem5-X/cnm_framework at `f2d4018`) multiplies one lane in
`src/fp_multiplier.cpp` with the `half` library's `operator*` (half 2.2.0,
`src/half.hpp`), followed by `MULT_STAGES` = 1 register (`src/defs.h`). Its
rounding, subnormal and overflow behaviour is the library's; bankside's
behaviour is the same on every non-NaN result, run on all 2³² pairs
([ANEMOS compared](#anemos-compared)). The top rules cited above settle the
arithmetic; the choices this doc adds for the multiplier are tagged where
they are made and listed under [Choices weighed](#choices-weighed).

The same Section III-A sentence says the multipliers and adders are "each
with 5 stages". bankside reads that as the five-stage pipeline of
Section IV-B, which the units sit in and in which MULT is one stage, not as
five registers inside each multiplier: ANEMOS's model of the paper also has
one register after its multiply (`MULT_STAGES` = 1), and [TOP-HIER-3] places
that register in `pcu_datapath` (the S3/S4 register), not in this unit.

## Ports

- **[FMUL-1]** The ports. No other ports exist: in particular **no clock, no
  reset, no enable, no rounding-mode input and no flag output**
  ([TOP-HIER-3], [FMUL-9]). **[bankside]**

  | Port | Dir | Width | Type | Description |
  |---|---|---|---|---|
  | `a` | in | 16 | `logic [15:0]` | First operand, binary16 bits ([FMUL-4]) |
  | `b` | in | 16 | `logic [15:0]` | Second operand, binary16 bits |
  | `p` | out | 16 | `logic [15:0]` | The product `a` × `b`, binary16 bits ([FMUL-5] to [FMUL-8]); combinational ([FMUL-3]) |

  Bit 15 is the sign, bits 14 to 10 the biased exponent field *e*, bits 9 to
  0 the trailing significand field *m* ([TOP-FP-1]). The module has no
  parameters.

- **[FMUL-2]** **Instances.** `pcu_datapath` has 16 instances,
  `g_lane[l].u_mul` for lane *l* = 0 … 15, seen from `top` as
  `dp.g_lane[l].u_mul` ([DP-16]). Lane *l*'s `a` and `b` are bits
  `[16l+15 : 16l]` of the S2/S3 register's *a* and *b*, and its `p` is lane
  *l* of *x* ([DP-10]). That connection is the parent's; it is restated here
  only to name the ports it uses. Since `p` doesn't depend on which operand
  is on which port ([FMUL-10]), the parent may connect them either way.
  **[bankside]**, **[ANEMOS]** (one multiplier per lane).

## Behaviour

- **[FMUL-3]** **A pure function.** `p` is a function of `a` and `b` alone:
  no clock, no state, no latch, no memory of earlier inputs. For any `a` and
  `b` with no X or Z bit, `p` has no X or Z bit. **[bankside]**, following
  [TOP-HIER-3].

### Operand classes

- **[FMUL-4]** Each operand is in exactly one class, by its bits alone
  ([TOP-FP-1]). Subnormals are operands like any other: no input is flushed
  to zero ([TOP-FP-4]). **[bankside]**

  | Class | *e* | *m* | Value | Patterns, each sign |
  |---|---|---|---|---|
  | zero | 0 | 0 | ±0 | 1 |
  | subnormal | 0 | ≠ 0 | ± *m* · 2⁻²⁴ | 1023 |
  | normal | 1 … 30 | any | ± (1024 + *m*) · 2^(*e* − 25) | 30720 |
  | Inf | 31 | 0 | ±∞ | 1 |
  | NaN | 31 | ≠ 0 | none | 1023 |

  The multiplier does not tell signalling NaNs (*m* bit 9 = 0) from quiet
  ones (*m* bit 9 = 1), nor one payload from another: every NaN operand is
  treated alike ([FMUL-8]).

### The result

- **[FMUL-5]** **Result by operand class.** With *s* = `a[15]` XOR
  `b[15]` ([FMUL-6]); the table is symmetric, so it holds with `a` and `b`
  swapped. **[bankside]**, following [TOP-FP-5] and [TOP-FP-6].

  | `a` \ `b` | zero | subnormal or normal | Inf | NaN |
  |---|---|---|---|---|
  | **zero** | *s* · 0 (0x0000 or 0x8000) | *s* · 0 | **0x7E00** (invalid) | 0x7E00 |
  | **subnormal or normal** | *s* · 0 | [FMUL-7] | *s* · ∞ (0x7C00 or 0xFC00) | 0x7E00 |
  | **Inf** | **0x7E00** (invalid) | *s* · ∞ | *s* · ∞ | 0x7E00 |
  | **NaN** | 0x7E00 | 0x7E00 | 0x7E00 | 0x7E00 |

  A finite non-zero operand times Inf is Inf, whatever its size (the
  smallest subnormal included). A finite operand times zero is zero, whatever
  its size (65504 included).

- **[FMUL-6]** **Sign.** Every result that is not a NaN has sign bit
  `a[15]` XOR `b[15]`: zeros and infinities included, and a finite product
  that rounds to zero keeps it (0x8001 × 0x0001 = 0x8000). A NaN result has
  sign 0 ([FMUL-8]). **[bankside]**, following [TOP-FP-5].

- **[FMUL-7]** **A finite non-zero product is the exact product, rounded
  once.** When both operands are subnormal or normal, `p` is the binary16
  value nearest to the exact real product *v* = value(`a`) × value(`b`),
  over every finite binary16 value (subnormals and ±0 included), with
  **ties to the value whose *m* is even** ([TOP-FP-2]); and when |*v*| ≥
  65520 = 2¹⁵ · (2 − 2⁻¹¹), `p` is *s* · ∞ ([TOP-FP-4], IEEE 754-2019
  clause 4.3.1). There is no other rounding mode and no saturation to
  ±65504. **[ANEMOS]** (half's default, round to nearest), **[bankside]**.

  On a magnitude scale, with *q* the spacing of binary16 values at |*v*|
  (2⁻²⁴ below 2⁻¹⁴, 2^(*E* − 10) in [2^*E*, 2^(*E*+1)) for *E* = −14 … 15):

  | |*v*| | `p` (magnitude) | Cases |
  |---|---|---|
  | ≥ 65520 | Inf, 0x7C00 | [#10, #11, #13, #14](#worked-cases) |
  | [65504, 65520) | 65504, 0x7BFF (the largest finite) | [#9, #12](#worked-cases) |
  | [2⁻¹⁴, 65504) | normal: the nearest multiple of *q*, ties to even *m*; one that rounds up to 2^(*E*+1) is the normal with the next exponent and *m* = 0 | [#1 to #8, #15, #24, #28, #29](#worked-cases) |
  | [2⁻¹⁴ − 2⁻²⁵, 2⁻¹⁴) | 2⁻¹⁴, 0x0400: a subnormal-range value that rounds up to the smallest normal | [#19](#worked-cases) |
  | (2⁻²⁵, 2⁻¹⁴ − 2⁻²⁵) | subnormal: the nearest multiple of 2⁻²⁴, ties to even *m* | [#16 to #18, #20, #22, #23](#worked-cases) |
  | ≤ 2⁻²⁵ | zero (2⁻²⁵ itself is a tie between 0 and 2⁻²⁴, and 0 is even) | [#21, #25 to #27](#worked-cases) |

  Every bound in the table is one of the [FMUL-7] rule's ties or limits, not
  a separate rule; the [script](#how-the-cases-are-checked) checks the
  operand pairs nearest each bound. The products of two binary16 values
  range over |*v*| from 2⁻⁴⁸ to (65504)² ≈ 2³², so a product can overflow,
  land in every part of the table, or underflow to zero.

- **[FMUL-8]** **NaN result.** Every NaN result is exactly **0x7E00**, both for
  a NaN operand (either operand or both, any sign, quiet or signalling, any
  payload) and for zero × Inf in either order and with any signs. No operand
  bit is propagated into a NaN result. **[bankside]**, following [TOP-FP-6],
  settled in #7. ANEMOS propagates the first NaN operand, quietened, and gives
  0x7FFF for zero × Inf ([ANEMOS compared](#anemos-compared)).

- **[FMUL-9]** **No flags and no other outputs.** Invalid, overflow,
  underflow and inexact are not signalled ([TOP-FP-7]); `p` is the only
  output. In particular, IEEE 754's choice of detecting tininess before or
  after rounding changes only the underflow flag, never the result, so it
  doesn't arise here: `p` is fixed by [FMUL-7] alone. **[bankside]**

- **[FMUL-10]** **Commutative, bit for bit.** For every pair, `p` for
  (`a`, `b`) equals `p` for (`b`, `a`), NaN results included. This follows
  from [FMUL-5] to [FMUL-8] (it would not under NaN propagation, which can
  keep the first NaN); it is stated as a rule because [DP-10] relies on it
  and a test can check it. **[bankside]**

### One way to compute it

This section is informative: it shows one structure that meets [FMUL-5] to
[FMUL-8], checked on all 2³² pairs ([how the cases are
checked](#how-the-cases-are-checked)). The designer may build any structure
with the same function.

1. **Unpack.** For each operand: *M* = (*e* ≠ 0) · 1024 + *m*, an 11-bit
   significand with the hidden bit, and *E* = max(*e*, 1) − 15. The value is
   *M* · 2^(*E* − 10). Classify the operands ([FMUL-4]) and select the
   [FMUL-5] special results by a final multiplexer: 0x7E00, *s* · ∞, *s* · 0.
2. **Multiply.** *P* = *M*a × *M*b, 22 bits, exact. The product is
   *P* · 2^(*E*a + *E*b − 20).
3. **Normalise.** The leading 1 of *P* has weight 2^*t*, *t* = *E*a + *E*b
   − 20 + (bit length of *P*) − 1. With two normal operands *P*'s leading 1
   is bit 20 or 21, a one-bit shift; a subnormal operand moves it lower,
   down to bit 10 (lower still with two subnormals, whose product always
   rounds to zero), so a leading-zero count is needed, or the subnormal
   operand is normalised first. The result's quantum is 2^*k* with *k* =
   max(*t*, −14) − 10.
4. **Round.** Keep *n* = *P* shifted right by *k* − (*E*a + *E*b − 20)
   places (11 bits for a normal result, fewer for a subnormal one; the shift
   can reach 24 for the smallest products, which leaves *n* = 0). With *g*
   the first bit shifted out and *st* the OR of the rest, add 1 to *n* when
   *g* AND (*st* OR *n*[0]). The shift is never negative: with a normal
   operand *P* ≥ 1024, and two subnormals give *t* < −14.
5. **Pack.** For *t* ≥ −14, `p` = *s* · ((*k* + 25) · 1024 + *n* − 1024);
   otherwise `p` = *s* · *n*. A rounding carry (*n* = 2048, or 1024 in the
   subnormal range) then lands in the exponent field by itself. A result
   ≥ 0x7C00 is replaced by *s* · ∞.

### Timing

- **[FMUL-11]** **Combinational, one stage.** The only paths are `a` → `p`
  and `b` → `p`; there are no registers and no clock ([FMUL-3]). In the
  pipeline, the unit is the S3 multiply between two `pcu_datapath`
  registers: the S2/S3 register → `a`, `b` → `fp16_mul` → `p` → the choice of
  *x* ([DP-10]) → the S3/S4 register, which must settle within one clock
  period less the register's clock-to-output, that choice and the setup
  ([DP-17]). **[bankside]**, following [TOP-HIER-3].

  The unit is **not** on the one-cycle accumulator loop of [TOP-HAZ-2] and
  [TOP-HAZ-4] (that loop goes through `fp16_add`, [DP-17]), so a slow
  multiplier lengthens only the S3 path. This doc sets no delay budget of its
  own beyond the clock period of [TOP-ARCH-3]: the M2 synthesis run
  measures the unit's delay on ASAP7, and [DP-17]'s S3 path with it.

## Choices weighed

The arithmetic was settled in the top spec ([TOP-FP-2], [TOP-FP-4] to
[TOP-FP-7]; the NaN rule in #7) and the combinational unit in
[TOP-HIER-3]; the options weighed there (a pipelined unit, NaN
propagation) are not repeated here. The choices left to this doc:

| Choice | Options | Where they differ | Chosen |
|---|---|---|---|
| Port names | (a) `a`, `b`, `p`; (b) `op_a`, `op_b`, `res`; (c) suffixed `a_i`, `b_i`, `p_o` | No behaviour differs. (a) uses [DP-10]'s own names (*x* = *a* × *b*; lane *l* of *a* goes to `a`), so the parent's connection reads as its rule; the merged module docs don't suffix ports | (a), [FMUL-1]. **[bankside]** |
| Operand order | (a) a rule that `p` doesn't depend on it ([FMUL-10]); (b) leave it unstated, since it follows from [FMUL-5] to [FMUL-8] | No result differs. Under (a) DV checks it directly, with one swapped sweep, and [DP-10]'s freedom to connect the operands either way rests on a rule of this doc instead of a derivation from four | (a). **[bankside]** |
| Port type | (a) `logic [15:0]`; (b) a shared `fp16_t` typedef in `bankside_pkg` (#53) | No behaviour differs. (b) would make the unit depend on the package for one 16-bit vector; the parent slices `logic` vectors ([DP-16]), and #53 lists no FP16 type | (a), [FMUL-1]. **[bankside]** |
| How the function is specified | (a) the result only ([FMUL-5] to [FMUL-8]), with an informative structure; (b) a mandated structure (significand widths, guard and sticky, the normaliser) | No result differs, by definition. (b) would rule out equivalent designs (a Booth multiplier, subnormal operands normalised before the multiply, a different guard and sticky arrangement) that synthesis may prefer, and DV checks the function either way | (a). **[bankside]** |
| X on the inputs | (a) say nothing beyond [FMUL-3]; (b) require `p` to be all X when an input bit is X | Only in a four-state simulation with an X operand. v1 simulates with Verilator, which is two-state: an entry never written reads as random bits, not X ([TOP-ARCH-9]). (b) is a property of the simulator as much as of the RTL | (a). **[bankside]** |

## Examples

### Worked cases

Each row is one operand pair; `p` is the result [FMUL-5] to [FMUL-8] give,
and the rule column says which. The NumPy column is NumPy 2.5.1 `float16`
on x86-64, run: it agrees with `p` on every row except the NaN bits, which
are the host's ([TOP-FP-6]). The ANEMOS column is ANEMOS's `half` 2.2.0,
run: "same" where it equals `p`. Exact products are written *k* · 2^*e*, in
lowest terms; *q* is the spacing at the product.

| # | `a` | `b` | Values | Exact product | `p` | Rule and what it shows | NumPy | ANEMOS |
|---|---|---|---|---|---|---|---|---|
| 1 | 0x3C00 | 0x3C00 | 1 × 1 | `1` | 0x3C00 | [FMUL-7]: exact | 0x3C00 | same |
| 2 | 0x3E00 | 0x3E00 | 1.5 × 1.5 | `9·2^−2` | 0x4080 | [FMUL-7]: exact, 2.25; *P* has its leading 1 at bit 21, so the exponent goes up by one | 0x4080 | same |
| 3 | 0x4500 | 0xC200 | 5 × −3 | `−15` | 0xCB80 | [FMUL-6]: sign the XOR; exact | 0xCB80 | same |
| 4 | 0x3C01 | 0x3C01 | (1 + 2⁻¹⁰)² | `1050625·2^−20` | 0x3C02 | [FMUL-7]: 1 + 2⁻⁹ + 2⁻²⁰, the 2⁻²⁰ is below half of *q* = 2⁻¹⁰, rounds down | 0x3C02 | same |
| 5 | 0x3C01 | 0x3E00 | (1 + 2⁻¹⁰) × 1.5 | `3075·2^−11` | 0x3E02 | [FMUL-7]: a **tie**, 1.5 + 1.5 *q*, between *m* = 1 (odd) and *m* = 2 (even): rounds **up** to even | 0x3E02 | same |
| 6 | 0x3C03 | 0x3E00 | (1 + 3 · 2⁻¹⁰) × 1.5 | `3081·2^−11` | 0x3E04 | [FMUL-7]: a **tie**, 1.5 + 4.5 *q*, between *m* = 4 (even) and *m* = 5: rounds **down** to even | 0x3E04 | same |
| 7 | 0x3DFF | 0x4001 | 1.4990234375 × 2.001953125 | `1573375·2^−19` | 0x4200 | [FMUL-7]: 3 + 2⁻¹⁰ − 2⁻¹⁹, just below the tie at 3 + *q*/2: rounds down to 3 | 0x4200 | same |
| 8 | 0x3DA8 | 0x3DA8 | 1.4140625² | `32761·2^−14` | 0x4000 | [FMUL-7]: 1.99957…, rounds up to 2: the carry out of *m* raises the exponent | 0x4000 | same |
| 9 | 0x7BFF | 0x3C00 | 65504 × 1 | `65504` | 0x7BFF | [FMUL-7]: the largest finite, exact | 0x7BFF | same |
| 10 | 0x7BFF | 0x3C01 | 65504 × (1 + 2⁻¹⁰) | `2098175·2^−5` | 0x7C00 | [FMUL-7]: 65567.97 ≥ 65520: **overflow** to +Inf, not 65504 | 0x7C00 | same |
| 11 | 0x5FE0 | 0x5810 | 504 × 130 | `65520` | 0x7C00 | [FMUL-7]: exactly 65520, the tie between 65504 (*m* odd) and 2¹⁶: rounds to even, which is past the largest finite, so +Inf | 0x7C00 | same |
| 12 | 0x581C | 0x5FC9 | 131.5 × 498.25 | `524159·2^−3` | 0x7BFF | [FMUL-7]: 65519.875, the largest product below 65520: 65504 | 0x7BFF | same |
| 13 | 0xFBFF | 0x4000 | −65504 × 2 | `−131008` | 0xFC00 | [FMUL-7], [FMUL-6]: overflow to −Inf | 0xFC00 | same |
| 14 | 0x7BFF | 0x7BFF | 65504² | `4290774016` | 0x7C00 | [FMUL-7]: the largest product, 2³² − 2²² + 2¹⁰, overflows | 0x7C00 | same |
| 15 | 0x0400 | 0x3C00 | 2⁻¹⁴ × 1 | `2^−14` | 0x0400 | [FMUL-7]: the smallest normal, exact | 0x0400 | same |
| 16 | 0x0400 | 0x3800 | 2⁻¹⁴ × 0.5 | `2^−15` | 0x0200 | [FMUL-7]: normal × normal gives an exact **subnormal** | 0x0200 | same |
| 17 | 0x0401 | 0x3800 | (2⁻¹⁴ + 2⁻²⁴) × 0.5 | `1025·2^−25` | 0x0200 | [FMUL-7]: a subnormal **tie**, 512.5 *q*: rounds down to *m* = 512 (even) | 0x0200 | same |
| 18 | 0x0403 | 0x3800 | (2⁻¹⁴ + 3 · 2⁻²⁴) × 0.5 | `1027·2^−25` | 0x0202 | [FMUL-7]: a subnormal **tie**, 513.5 *q*: rounds up to *m* = 514 (even) | 0x0202 | same |
| 19 | 0x03FF | 0x3C01 | (1023 · 2⁻²⁴) × (1 + 2⁻¹⁰) | `1048575·2^−34` | 0x0400 | [FMUL-7]: a subnormal operand; 1023.999 *q* rounds up to 1024 *q* = 2⁻¹⁴, the smallest **normal** | 0x0400 | same |
| 20 | 0x0001 | 0x3C00 | 2⁻²⁴ × 1 | `2^−24` | 0x0001 | [FMUL-7]: the smallest subnormal, exact | 0x0001 | same |
| 21 | 0x0001 | 0x3800 | 2⁻²⁴ × 0.5 | `2^−25` | 0x0000 | [FMUL-7]: exactly 2⁻²⁵, the **tie** between 0 and 2⁻²⁴: to 0, the even one (**underflow**) | 0x0000 | same |
| 22 | 0x0001 | 0x3801 | 2⁻²⁴ × (0.5 + 2⁻¹¹) | `1025·2^−35` | 0x0001 | [FMUL-7]: just above 2⁻²⁵: up to the smallest subnormal, not 0 | 0x0001 | same |
| 23 | 0x0003 | 0x3800 | 3 · 2⁻²⁴ × 0.5 | `3·2^−25` | 0x0002 | [FMUL-7]: a **tie**, 1.5 *q*, between *m* = 1 and *m* = 2: up to even | 0x0002 | same |
| 24 | 0x0001 | 0x7BFF | 2⁻²⁴ × 65504 | `2047·2^−19` | 0x1BFF | [FMUL-7]: subnormal × normal gives an exact normal | 0x1BFF | same |
| 25 | 0x03FF | 0x03FF | (1023 · 2⁻²⁴)² | `1046529·2^−48` | 0x0000 | [FMUL-7]: subnormal × subnormal always underflows to 0 | 0x0000 | same |
| 26 | 0x0400 | 0x0400 | 2⁻¹⁴ × 2⁻¹⁴ | `2^−28` | 0x0000 | [FMUL-7]: normal × normal can underflow to 0 | 0x0000 | same |
| 27 | 0x8001 | 0x0001 | −2⁻²⁴ × 2⁻²⁴ | `−2^−48` | 0x8000 | [FMUL-7], [FMUL-6]: the smallest product underflows to **−0**, keeping the sign | 0x8000 | same |
| 28 | 0x0200 | 0x4400 | 2⁻¹⁵ × 4 | `2^−13` | 0x0800 | [FMUL-7]: subnormal × normal gives an exact normal | 0x0800 | same |
| 29 | 0x0001 | 0x6400 | 2⁻²⁴ × 1024 | `2^−14` | 0x0400 | [FMUL-7]: the smallest subnormal × 2¹⁰ is the smallest normal | 0x0400 | same |
| 30 | 0x8000 | 0x3C00 | −0 × 1 | – | 0x8000 | [FMUL-5], [FMUL-6]: −0 | 0x8000 | same |
| 31 | 0x8000 | 0x8000 | −0 × −0 | – | 0x0000 | [FMUL-6]: +0 | 0x0000 | same |
| 32 | 0x0000 | 0xFBFF | +0 × −65504 | – | 0x8000 | [FMUL-5]: zero × the largest finite is zero, sign the XOR | 0x8000 | same |
| 33 | 0x8000 | 0x0001 | −0 × 2⁻²⁴ | – | 0x8000 | [FMUL-5]: zero × a subnormal | 0x8000 | same |
| 34 | 0x7C00 | 0xBC00 | +Inf × −1 | – | 0xFC00 | [FMUL-5]: −Inf | 0xFC00 | same |
| 35 | 0x7C00 | 0x0001 | +Inf × 2⁻²⁴ | – | 0x7C00 | [FMUL-5]: Inf × the smallest subnormal is Inf | 0x7C00 | same |
| 36 | 0xFC00 | 0xFC00 | −Inf × −Inf | – | 0x7C00 | [FMUL-5]: +Inf | 0x7C00 | same |
| 37 | 0x7C00 | 0x0000 | +Inf × +0 | – | 0x7E00 | [FMUL-8]: invalid | 0xFE00 | 0x7FFF |
| 38 | 0x8000 | 0xFC00 | −0 × −Inf | – | 0x7E00 | [FMUL-8]: invalid, in the other order, with signs | 0xFE00 | 0x7FFF |
| 39 | 0x7C01 | 0x3C00 | sNaN × 1 | – | 0x7E00 | [FMUL-8]: a signalling NaN; not propagated or quietened into 0x7E01 | 0x7E01 | 0x7E01 |
| 40 | 0xFE00 | 0x0000 | −qNaN × +0 | – | 0x7E00 | [FMUL-8]: a NaN operand beats the zero; the result's sign is 0 | 0xFE00 | 0xFE00 |
| 41 | 0x7FFF | 0x7C00 | NaN × Inf | – | 0x7E00 | [FMUL-8]: a NaN operand beats the Inf; its payload is dropped | 0x7FFF | 0x7FFF |
| 42 | 0xFC01 | 0xFE02 | −sNaN × −qNaN | – | 0x7E00 | [FMUL-8]: two NaNs, neither kept | 0xFE02 | 0xFE01 |
| 43 | 0xFE02 | 0xFC01 | −qNaN × −sNaN | – | 0x7E00 | [FMUL-8], [FMUL-10]: the same pair swapped gives the same `p`, where both references change | 0xFE01 | 0xFE02 |

### How the cases are checked

One script checks the table and the rules, against two models of this doc
written independently of each other, and against NumPy and ANEMOS:

- **spec_mul**, the rules as [FMUL-5] to [FMUL-8] state them: a finite
  product computed exactly with Python's `fractions.Fraction` and rounded
  once by the IEEE 754 definition (the nearest value, ties to even *m*,
  |*v*| ≥ 65520 to Inf);
- **model_mul**, the five steps of [one way to compute
  it](#one-way-to-compute-it), on integers.

Rerun from the repo root:

```
.venv/bin/python src/fp16_mul/doc/examples/fmul_check.py
python3 src/fp16_mul/doc/examples/fmul_check.py --numpy --exhaustive --anemos src/fp16_mul/doc/examples/anemos_fmul.out
```

The first line needs only the standard library (about two minutes); the
second also needs NumPy, which `.venv` lacks, and takes about 15 minutes of
CPU time for the 2³² sweep. Output:
[examples/fmul_check.out](examples/fmul_check.out), from the second line.
The script exits non-zero if any check fails. What it covers, exactly:

| Check | Pairs | Against | Holds |
|---|---|---|---|
| The worked cases above: `p` and the exact-product column | 43 | spec_mul, model_mul; NumPy and its column (`--numpy`); ANEMOS and its column (`--anemos`) | every row |
| C1: each of 13 special operands (±0, ±Inf, NaNs 0x7C01, 0x7D55, 0x7DFF, 0x7E00, 0x7FFF, 0xFC01, 0xFDFF, 0xFE00, 0xFFFF) with all 65536 patterns, in both orders | 1703936 | model_mul = spec_mul; NumPy (`--numpy`) | every pair |
| C2: every pair of exponent fields 0 … 30, each with 12 values of *m* (0, 1, 2, 0x0AA, 0x155, 0x1FF, 0x200, 0x2AA, 0x300, 0x3FD, 0x3FE, 0x3FF), with equal and with opposite signs | 276768 | the same | every pair |
| C3: every subnormal, both signs, with 3 values of *m* (0, 0x155, 0x3FF) at every exponent field 0 … 30 | 190278 | the same | every pair |
| C4: every positive finite non-zero `a`, with the 4 patterns of `b` nearest each of 65520 / `a`, 2⁻¹⁴ / `a` and 2⁻²⁵ / `a` (the overflow, smallest-normal and underflow bounds of [FMUL-7]), where they are finite and non-zero | 301048 | the same | every pair |
| C5: every exact tie among the 2²⁰ pairs of operands in [1, 2): 1692 with an odd *m* below (round up) and 1675 with an even one (round down, where ties-away would differ) | 3367 | model_mul = spec_mul, and the result's *m* even | every tie |
| C6: 200000 random pairs over all 2³², and 100000 random finite non-zero pairs, both signs, about half of them with a subnormal `a` | 300000 | the same | every pair |
| [FMUL-10] on C1 to C6 | as above | model_mul with the operands swapped | every pair |
| `--exhaustive`: all 2³² pairs | 4294967296 | a vectorised model_mul = NumPy (a NaN as a class); every NaN result 0x7E00; [FMUL-10] | every pair |
| `--anemos`: all 2³² pairs, in [anemos_fmul.cpp](examples/anemos_fmul.cpp) | 4294967296 | ANEMOS's `half` = GCC's `_Float16` conversion of the exact double product; with `--exhaustive`, the digest of each (NaN as 0x7E00) = the model's | every non-NaN result; NaN exactly where [FMUL-5] puts one |

Over all 2³² pairs the results are: zero 58620500, subnormal 479104404,
normal 2948541464, Inf 544713724, NaN 263987204 (the 263987196 pairs with a
NaN operand and the 8 zero × Inf pairs).

NumPy is a valid oracle for the multiply: its `float16` product is formed
in float32, where the 22-bit product of two significands and its exponent
(2⁻⁴⁸ to 2³²) are exact, and then rounded once to binary16. GCC's
`_Float16` from the exact double product is the same single rounding, done
by different code (libgcc). For DV: every check above other than the
NaN bits can use either; the NaN bits are checked against 0x7E00 alone
([TOP-FP-6], [VER-4]).

### ANEMOS compared

ANEMOS's lane multiply is half 2.2.0's `operator*` (`src/fp_multiplier.cpp`,
`mul_res = op1->read() * op2->read()`; integer arithmetic in
`src/half.hpp`, default round to nearest). [anemos_fmul.cpp](examples/anemos_fmul.cpp)
builds it against ANEMOS's own `src/half.hpp` at `f2d4018` and runs every
one of the 2³² pairs, comparing it with `_Float16` as above
([anemos_fmul.out](examples/anemos_fmul.out)):

- On all 4030980092 pairs with a non-NaN result, ANEMOS and the reference
  give the same bits: 0 pairs differ. The program also prints a digest of
  all 2³² results of each, in order, with every NaN replaced by 0x7E00;
  `fmul_check.py --exhaustive --anemos` computes the same digest from
  bankside's model and finds it equal to both. So rounding, ties,
  subnormals, overflow and the signs of zero and Inf are the same in all
  three ([FMUL-5] to [FMUL-7]).
- ANEMOS gives a NaN on exactly the 263987204 pairs where [FMUL-5] does:
  the 263987196 pairs with a NaN operand and the 8 zero × Inf pairs.
- **Intended difference, NaN bits only** ([FMUL-8], [TOP-FP-6]): ANEMOS
  gives 0x7FFF for the 8 zero × Inf pairs, and for a NaN operand the first
  NaN, quietened (1024 distinct patterns over the sweep). bankside gives
  0x7E00 on all of them. [VER-2] compares a NaN against ANEMOS as a class.

Rerun (needs SystemC; 2.3.4 was used; the sweep takes about six minutes):

```
A=<cnm_framework>
g++ -std=c++17 -O2 -I $A/src src/fp16_mul/doc/examples/anemos_fmul.cpp -lsystemc -o <scratch>/anemos_fmul
python3 src/fp16_mul/doc/examples/fmul_check.py --print-pairs \
  | SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fmul > src/fp16_mul/doc/examples/anemos_fmul.out
```
