# Verification requirements

Simulation runs on [opendv](https://github.com/idanhochman/opendv) (Verilator +
cocotb). A machine-readable testplan, mapping each requirement ID in the spec to
the tests that check it, will sit next to this file.

## Three independent checks

The reference model and the RTL are written from the same reading of the
papers, so a misreading would pass a model-vs-RTL check. Two further checks
don't depend on that reading.

- **[VER-1] RTL vs the bankside reference model: bit-exact.** Compared per
  instruction: every bank write (address and data), every register-file write,
  and `err_illegal`. Final register contents are also checked through the debug
  port.
- **[VER-2] RTL vs ANEMOS** on the kernels both can run (non-AAM). Compared on
  the bank writes. ANEMOS kernels are translated first: register-index fields
  differ (5-bit vs 3-bit), and NOPs are inserted where [HAZ-3] needs them.
  Known, intended differences, which the comparison masks:
  - ReLU of −0 and of NaNs with the sign bit set ([FP-8])
  - NaN bit patterns ([FP-6]): compared as a class
- **[VER-3] Kernels vs plain maths.** Each kernel (GEMV, element-wise ADD/MUL,
  ReLU) is checked against NumPy in two ways:
  - bit-exact against a NumPy FP16 reference doing the same operations in the
    same order (unfused, [FP-3])
  - within an FP16 error bound of the exact float64 result, so that the kernel
    computes what it is meant to, not just what the model does

## FP16 units

- **[VER-4]** `fp16_mul` and `fp16_add` are verified on their own, before
  integration, against NumPy `float16` (a valid oracle, see
  [theory of operation](../doc/theory_of_operation.md#fp16-arithmetic)):
  - directed: ±0, ±Inf, NaNs, the smallest and largest subnormals and
    normals, results that overflow, underflow or are exactly halfway between
    two FP16 values (RNE ties)
  - random: a large sweep of operand pairs, weighted towards the special
    classes; the size depends on simulation speed (all 2³² pairs if a fast
    harness makes it practical)

## Functional coverage

- **[VER-5]** Every legal (opcode, SRC0, SRC1, DST) combination
  ([programmer's guide](../doc/programmers_guide.md#legal-combinations-compared-with-the-paper)),
  with ReLU on and off for MOV.
- **[VER-6]** Hazard distances 1 to 4 for every producer/consumer pair,
  including the accumulator bypass ([HAZ-2]) with each producer type.
- **[VER-7]** Control: JUMP with IMM1 = 0, 1, and large; sequential loops; NOP
  with IMM0 = 0, 1 and > 1; EXIT followed by a new run; PC wrap.
- **[VER-8]** Every class of illegal instruction ([ISA-2]).
- **[VER-9]** FP16 operand classes (zero, subnormal, normal, Inf, NaN) per
  arithmetic instruction, and the result classes (overflow, subnormal result,
  exact zero, ties).

Code coverage (line, branch, toggle) is collected through opendv as well.

## Assertions

- **[VER-10]** The programming rules [HAZ-3], [HAZ-6], [ISA-6], [ISA-7] and
  [IF-6] are checked by assertions in simulation. Constrained-random programs
  are generated legal; separate directed tests break each rule on purpose, to
  show the assertion fires.

## Stimulus

- Directed tests per instruction, then kernels (GEMV, ADD, MUL, ReLU).
- Constrained-random microkernels: random legal instruction sequences that
  respect the programming rules, random register and bank contents, and random
  bubbles between triggers.
