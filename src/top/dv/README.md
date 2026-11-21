# Verification requirements

Simulation runs on [opendv](https://github.com/idanhochman/opendv) (Verilator +
cocotb). A machine-readable testplan, mapping each requirement ID in the spec to
the tests that check it, will sit next to this file (M3). Until then,
[Requirement coverage](#requirement-coverage) below maps every `[TOP-...]` ID
of the spec to the VER items that check it.

The `[VER-n]` IDs are DV's own. The `[TOP-...]` IDs are defined in the spec
([`src/top/doc/`](../doc/README.md)); this file only refers to them.

## Three independent checks

The reference model and the RTL are written from the same reading of the
papers, so a misreading would pass a model-vs-RTL check. Two further checks
don't depend on that reading.

- **[VER-1] RTL vs the bankside reference model: bit-exact.** Compared per
  instruction: every bank write (address and data), every register-file write,
  and `err_illegal`. Final register contents are also checked through the debug
  port.
- **[VER-2] RTL vs ANEMOS** on the kernels both can run (non-AAM). Compared on
  the bank writes, as an ordered sequence of (bank, row, column, data), not
  cycle by cycle, since the translated kernel takes more slots. ANEMOS kernels
  are translated first, as described in
  [ANEMOS kernel translation](#anemos-kernel-translation-ver-2). The known,
  intended differences are listed there too; the comparison masks or excludes
  each of them.
- **[VER-3] Kernels vs plain maths.** Each kernel (GEMV, element-wise ADD/MUL,
  ReLU) is checked against NumPy in two ways:
  - bit-exact against a NumPy FP16 reference doing the same operations in the
    same order (unfused, [TOP-FP-3]: each multiply and each add rounded to
    `float16` on its own)
  - within an FP16 error bound of the exact float64 result, so that the kernel
    computes what it is meant to, not just what the model does

### ANEMOS kernel translation (VER-2)

The two encodings differ ([programmer's guide](../doc/programmers_guide.md#instruction-formats)).
Each ANEMOS instruction word is rewritten field by field into a bankside word,
starting from all zeros. The spec doesn't yet say which ANEMOS index field is
which, nor where ANEMOS puts IMM0 and IMM1; the table assumes the order in
which the spec lists the index fields, and unchanged control fields (#25).

| Field | ANEMOS bits | bankside bits | Translation |
|---|---|---|---|
| OPCODE | 31–28 | 31–28 | copied |
| DST, SRC0, SRC1, SRC2 (operand codes) | 27–25, 24–22, 21–19, 18–16 | same | copied; SRC2 only for MAD, 0 otherwise ([TOP-ISA-10]) |
| A (AAM, ALU format) | 15 | 15 | copied; must be 0 (non-AAM kernels only) |
| R (ReLU, data format) | 15 | 12 | moved |
| DST# | 14–10 (5 bits) | 10–8 (3 bits) | value copied if ≤ 7 |
| SRC0# | 9–5 (5 bits) | 6–4 (3 bits) | value copied if ≤ 7 |
| SRC1# | 4–0 (5 bits) | 2–0 (3 bits) | value copied if ≤ 7 |
| IMM0, IMM1 (control format) | 18–11, 10–0 | 18–11, 10–0 | copied, except JUMP's IMM0 (below) |
| every other bit | – | – | 0 ([TOP-ISA-1]) |

Rules of the translation:

- An index field whose operand is a bank is written as 0 ([TOP-ISA-9]),
  except MAD's SRC1#, which is copied because it is the SRF_A addend index
  ([TOP-ISA-20]). The result is the encoding bankside's assembler would write
  for the same program, so the translated kernel is also a VER-1 stimulus.
- A kernel with an index value above 7, A = 1, a reserved code, or an
  instruction illegal under [TOP-ISA-2] is not translated. FILL kernels are not
  run, since ANEMOS doesn't implement FILL ([TOP-ISA-16]). MAD kernels whose
  SRC2 holds anything but SRF_A are not run until #6 settles [TOP-ISA-19].
- NOPs are inserted wherever [TOP-HAZ-3] needs them, and each JUMP's IMM0 is
  recomputed so that it still targets the same instruction. The translated
  kernel must still fit in the CRF (32 entries) and keep [TOP-ISA-7] and
  [TOP-ISA-14]; otherwise it is not translated.
- The host command stream for bankside is generated from the translated
  kernel: one trigger per bankside slot, with the addresses ANEMOS used for
  the same instruction, and [TOP-HAZ-6] respected.

A kernel that can't be translated is reported by name and skipped, never
silently dropped.

**Intended differences.** The spec records each next to its rule.

| Difference | Rule | bankside | ANEMOS | How VER-2 handles it |
|---|---|---|---|---|
| ReLU of −0 and of NaNs with the sign bit set | [TOP-FP-8] | +0 | compares against zero | masked: lanes whose ReLU input is −0 or a NaN with the sign bit set |
| NaN bit patterns | [TOP-FP-6] | canonical quiet NaN 0x7E00 | may differ | compared as a class (any NaN matches any NaN) |
| `NOP 0` | [TOP-ISA-12] | 1 slot | 256 slots | kernels with `NOP 0` excluded |
| JUMP with IMM1 = 0 | [TOP-ISA-13] | never taken | jumps (counter wraps) | kernels with IMM1 = 0 excluded |
| EXIT and the loop state | [TOP-ISA-5] | cleared | not cleared (PC only) | runs that reach EXIT with `loop_active` = 1 excluded |

The last three change the control flow, not a value, so they can't be masked
per lane; the kernels or runs that hit them are excluded from VER-2 and checked
by VER-1 and VER-7 only. Exclusions are counted and reported with the results.

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
  with ReLU on and off for MOV. Each combination with an SRF source also
  counts as an [TOP-ISA-11] case.
- **[VER-6]** Hazard distances 1 to 4 for every producer/consumer pair,
  including the accumulator bypass ([TOP-HAZ-2]) with each producer type, and
  back-to-back MACs into one GRF_B entry ([TOP-HAZ-4]). Distances below the
  [TOP-HAZ-3] limit are generated only by the VER-10 tests that break the rule
  on purpose; there the result checked is [TOP-HAZ-5]'s.
- **[VER-7]** Control:
  - JUMP with IMM1 = 0 ([TOP-ISA-13]: body runs once, loop state stays clear,
    so a later JUMP starts a loop of its own), 1, and large; each row of the
    loop-state table ([TOP-ISA-3]); zero-slot JUMP ([TOP-ISA-4]); sequential
    loops
  - NOP with IMM0 = 0, 1, > 1 and 255 ([TOP-ISA-12]): the next instruction
    issues on the trigger after the NOP's last slot, and IMM0 = 0 takes one
    slot, like IMM0 = 1
  - EXIT followed by a new run ([TOP-ISA-5]), including EXIT reached inside a
    loop body, so that the next run starts with the loop state clear
  - PC wrap from 31 to 0 ([TOP-ISA-8])
- **[VER-8]** Every class of illegal instruction ([TOP-ISA-2]): reserved
  opcode, reserved operand code in a field the instruction uses, an operand
  combination outside the `legal` lists, and A = 1. A reserved code in a field
  the instruction ignores ([TOP-ISA-10]) is the negative case: not illegal
  (VER-12).
- **[VER-9]** FP16 operand classes (zero, subnormal, normal, Inf, NaN) per
  arithmetic instruction, and the result classes (overflow, subnormal result,
  exact zero, ties).

Code coverage (line, branch, toggle) is collected through opendv as well.

## Assertions

- **[VER-10]** The programming rules [TOP-HAZ-3], [TOP-HAZ-6], [TOP-ISA-6],
  [TOP-ISA-7], [TOP-ISA-14] and [TOP-IF-6] are checked by assertions in
  simulation. Constrained-random programs are generated legal; separate
  directed tests break each rule on purpose, to show the assertion fires.
  - [TOP-ISA-14] is broken both ways: a JUMP with IMM0 = 0, and a JUMP with
    IMM0 greater than its own PC (including any JUMP at PC 0).
  - For [TOP-HAZ-3] and [TOP-HAZ-6] the hardware outcome is specified
    ([TOP-HAZ-5], and old data for [TOP-HAZ-6]), so those tests also check it
    and keep comparing against the model.
  - For [TOP-ISA-6], [TOP-ISA-7], [TOP-ISA-14] and [TOP-IF-6] it is not
    specified yet (#16, to be settled in #9). Those tests check only that the
    assertion fires on the violating instruction, and that the reference model
    reports the same violation. They stop comparing at the violation and check
    nothing the hardware does afterwards.

## Instructions

- **[VER-11] Instruction semantics.** A directed test per instruction checks
  its result against values computed in the test with NumPy `float16`, per
  lane, as well as against the model (VER-1):
  - MOV ([TOP-ISA-15]): every row of its table, with R = 0 and R = 1. GRF
    lanes hold distinct values, so that a wrong lane or a missing broadcast
    shows.
  - FILL ([TOP-ISA-16]): the four bank load/store pairs, with R = 1 as well,
    to show R has no effect.
  - ADD, MUL, MAD, MAC ([TOP-ISA-17], [TOP-ISA-18], [TOP-ISA-19],
    [TOP-ISA-21]): each source kind (GRF, bank, SRF) in each position; MAC
    into several GRF_B entries.
  - SRF broadcast ([TOP-ISA-11]): every SRF source of ADD, MUL, MAD, MAC and
    MOV into a GRF, against GRF operands whose lanes all differ.
  - MAD addend index ([TOP-ISA-20]): with a GRF or SRF_M src1 (SRC1# indexes
    both), and with a bank src1 and SRC1# = 1 to 7, so the addend can't come
    from entry 0 by accident. SRF_A entries hold distinct values.
- **[VER-12] Ignored fields.** Every field the instruction ignores is filled
  with random values, and the result must equal that of the same instruction
  with those fields at 0, with `err_illegal` staying 0:
  - unused bits ([TOP-ISA-1])
  - the index field of a bank operand ([TOP-ISA-9]), but not MAD's SRC1#
    ([TOP-ISA-20])
  - SRC2 of ADD, MUL and MAC, including the reserved codes 6 and 7, which are
    not illegal there ([TOP-ISA-10])
  - R of FILL ([TOP-ISA-16])

  Random programs (see [Stimulus](#stimulus)) also randomise these fields.

## Interface and status

- **[VER-13] Status outputs.** `busy` is checked every cycle against
  [TOP-IF-7]: 1 while an instruction is valid in S1 to S5, a multi-cycle NOP
  has slots left ([TOP-ISA-12]), or `loop_active` = 1 ([TOP-ISA-3]). Directed
  cases: `busy` held across cycles without triggers during a multi-cycle NOP
  and inside a loop; `busy` falling after the last instruction after EXIT
  leaves S5. `err_illegal` is checked sticky until reset ([TOP-ISA-2],
  [TOP-IF-4]). The exact cycles in which `busy` rises and falls depend on #24.
- **[VER-14] Reset, configuration and the bank port.** Reset clears the control
  state ([TOP-IF-4]) and keeps register-file contents ([TOP-ARCH-5]), read back
  through the debug port. A configuration write is visible to `dbg_rd_*` in the
  next cycle ([TOP-IF-5]). The testbench's bank model checks the bank read and
  write timing ([TOP-IF-2], [TOP-IF-3], [TOP-ARCH-8]) and that the addresses
  are the trigger's ([TOP-ARCH-6]). The port selects and indices are pending
  #15.

## Stimulus

- Directed tests per instruction (VER-11), then kernels (GEMV, ADD, MUL, ReLU).
- Constrained-random microkernels: random legal instruction sequences that
  respect the programming rules, random register and bank contents, random
  values in ignored fields (VER-12), and random bubbles between triggers.
  Each run prints its seed and accepts one to reproduce it.

## Requirement coverage

Every requirement ID in the spec, with the VER items that check it. VER-1
(bit-exact against the model) applies to every rule the model implements; it
is listed only where it is the main check.

| ID | Rule | Checked by |
|---|---|---|
| [TOP-ARCH-1] | one bank pair, at most one bank per instruction | VER-5, VER-8 |
| [TOP-ARCH-2] | 16 FP16 lanes | VER-1, VER-11 |
| [TOP-ARCH-3] | DRAM core clock, one instruction per cycle | uncovered by simulation beyond issuing every cycle (VER-6); the 300 MHz target is a PPA result (syn) |
| [TOP-ARCH-4] | one write port per register file | VER-10 ([TOP-IF-6] assertion) |
| [TOP-ARCH-5] | register files not reset | VER-14 |
| [TOP-ARCH-6] | bank address from the trigger | VER-14 |
| [TOP-ARCH-7] | at most one bank operand | VER-5, VER-8 |
| [TOP-ARCH-8] | bank writes in S5, to the store's own trigger | VER-14 |
| [TOP-PIPE-1] | five stages, writes in program order | VER-1, VER-6 |
| [TOP-PIPE-2] | bubbles without triggers | VER-6, random bubbles in [Stimulus](#stimulus) |
| [TOP-PIPE-3] | NOP and JUMP slots | VER-7 |
| [TOP-HAZ-1] | write-through | VER-6 (distance 3) |
| [TOP-HAZ-2] | accumulator bypass | VER-6 |
| [TOP-HAZ-3] | 2 slots between producer and consumer | VER-10 |
| [TOP-HAZ-4] | MAC accumulator exempt | VER-6 |
| [TOP-HAZ-5] | outcome when [TOP-HAZ-3] is broken | VER-10 |
| [TOP-HAZ-6] | 3 slots between bank store and read | VER-10 |
| [TOP-FP-1] | IEEE 754 binary16 | VER-4, VER-9 |
| [TOP-FP-2] | correctly rounded, RNE | VER-4, VER-9 |
| [TOP-FP-3] | MAC and MAD unfused | VER-3, VER-11 |
| [TOP-FP-4] | subnormals, overflow | VER-4, VER-9 |
| [TOP-FP-5] | IEEE special cases | VER-4, VER-9 |
| [TOP-FP-6] | canonical NaN | VER-4, VER-9 (bit-exact against the model; NumPy and ANEMOS compare NaNs as a class) |
| [TOP-FP-7] | no exception flags | uncovered: no port to observe; nothing to test in v1 |
| [TOP-FP-8] | ReLU on the sign bit | VER-5, VER-11, VER-2 (masked) |
| [TOP-ISA-1] | unused bits ignored | VER-12 |
| [TOP-ISA-2] | illegal instructions | VER-8, VER-13 |
| [TOP-ISA-3] | loop state | VER-7, VER-13 |
| [TOP-ISA-4] | JUMP takes no slot | VER-7 |
| [TOP-ISA-5] | EXIT | VER-7 |
| [TOP-ISA-6] | one loop at a time | VER-10 |
| [TOP-ISA-7] | no JUMP at a JUMP's target or after a JUMP | VER-10 |
| [TOP-ISA-8] | PC wrap | VER-7 |
| [TOP-ISA-9] | bank operand index fields ignored | VER-12 |
| [TOP-ISA-10] | only MAD uses SRC2 | VER-12, VER-8 (negative case) |
| [TOP-ISA-11] | SRF broadcast | VER-11, VER-5 |
| [TOP-ISA-12] | NOP slots, IMM0 = 0 as 1 | VER-7, VER-13 |
| [TOP-ISA-13] | IMM1 = 0 never taken | VER-7 |
| [TOP-ISA-14] | JUMP IMM0 between 1 and its PC | VER-10 |
| [TOP-ISA-15] | MOV | VER-11, VER-5 |
| [TOP-ISA-16] | FILL | VER-11, VER-12, VER-5 |
| [TOP-ISA-17] | ADD | VER-11, VER-5 |
| [TOP-ISA-18] | MUL | VER-11, VER-5 |
| [TOP-ISA-19] | MAD | VER-11, VER-5 |
| [TOP-ISA-20] | MAD addend index is SRC1# | VER-11 |
| [TOP-ISA-21] | MAC | VER-11, VER-5 |
| [TOP-IF-1] | one slot per `trig_valid` | VER-7, VER-13 |
| [TOP-IF-2] | bank read timing | VER-14 |
| [TOP-IF-3] | bank write timing | VER-14 |
| [TOP-IF-4] | reset | VER-14, VER-13 |
| [TOP-IF-5] | configuration write timing | VER-14 |
| [TOP-IF-6] | host writes only while idle | VER-10 |
| [TOP-IF-7] | `busy` | VER-13 |

Rules still being settled may change the checks above: #6 ([TOP-ISA-19]
SRC2, the MAC/MAD pairs in VER-5), #7 ([TOP-FP-6], [TOP-FP-8]), #8
([TOP-ARCH-5], [TOP-HAZ-1], [TOP-HAZ-3], [TOP-HAZ-5]), #9 ([TOP-ISA-2],
[TOP-ISA-7], [TOP-ISA-8], [TOP-ISA-12], [TOP-ISA-13], [TOP-ISA-15], and the
outcomes of #16), #10 ([TOP-ARCH-8], [TOP-IF-2], [TOP-IF-3], [TOP-HAZ-6]).
