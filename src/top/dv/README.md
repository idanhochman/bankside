# Verification requirements

Simulation runs on [opendv](https://github.com/idanhochman/opendv) (Verilator +
cocotb). A machine-readable testplan, mapping each requirement ID in the spec to
the tests that check it, will sit next to this file (M3). Until then,
[Requirement coverage](#requirement-coverage) below maps every `[TOP-...]` ID
of the spec to the VER items that check it, or says why it is uncovered.

The `[VER-n]` IDs are DV's own. The `[TOP-...]` IDs are defined in the spec
([`src/top/doc/`](../doc/README.md)); this file only refers to them.
[check_testplan.py](check_testplan.py) checks that the coverage table lists
every ID the spec defines, and no other; that every VER item the spec or the
table cites is defined here once; and that every relative link and anchor in
this file resolves. Rerun it from the repo root after a spec or testplan
change: `.venv/bin/python src/top/dv/check_testplan.py` (exits non-zero on a
failure).

## Three independent checks

The reference model and the RTL are written from the same reading of the
papers, so a misreading would pass a model-vs-RTL check. Two further checks
don't depend on that reading.

- **[VER-1] RTL vs the bankside reference model: bit-exact.** Compared per
  instruction: every bank write (address and data), every register-file write,
  and `err_illegal`. Final register contents are also checked through the debug
  port. NaN results are compared bit for bit like any other value: [TOP-FP-6]
  fixes them to 0x7E00. The model is described under
  [Reference model](#reference-model).
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
    `float16` on its own). ReLU in that reference is the sign-bit rule of
    [TOP-FP-8], `np.where(np.signbit(x), np.float16(0), x)`, not
    `np.maximum(x, 0)`, which returns 0x8000 for −0 and passes NaNs through,
    and so differs from [TOP-FP-8] on 1024 of the 65536 inputs
    ([theory of operation](../doc/theory_of_operation.md#relu-compared)).
    NumPy's NaN bit patterns are the host's, so a NaN in NumPy's result is
    checked as "the RTL gives exactly 0x7E00" ([TOP-FP-6]), never against
    NumPy's bits.
  - within an FP16 error bound of the exact float64 result, so that the kernel
    computes what it is meant to, not just what the model does

### Reference model

The bankside reference model is Python, written from the spec, and bit-exact.
It is cycle-level: it takes the same per-cycle sequence of triggers, resets
and configuration writes as the RTL, so it predicts the cycle-dependent rules
([TOP-HAZ-5], [TOP-HAZ-7], [TOP-IF-7], [TOP-IF-8], [TOP-ISA-24]) and not only
the final state. FP16 arithmetic is NumPy `float16`, one rounding per
operation ([TOP-FP-3]), with every NaN result replaced by 0x7E00
([TOP-FP-6]); data movement copies bits ([TOP-FP-9]).

- **Written flags.** The model keeps a *written* flag per register-file entry
  (CRF, GRF_A, GRF_B, SRF_M, SRF_A), set by an S5 write or by a configuration
  write that takes effect ([TOP-IF-10]) and never cleared, not by reset either
  ([TOP-ARCH-5]). It reports as an error any program read of an entry whose
  flag is clear: an S2 source read, a MAC accumulator read in S4, or the CRF
  entry of an executed slot. Debug reads ([TOP-IF-11]) are not reported. The
  model doesn't predict the value read ([TOP-ARCH-9]), so the VER-1 comparison
  stops at that error.
- **Broken programming rules.** A broken [TOP-HAZ-3], [TOP-HAZ-6],
  [TOP-ISA-6], [TOP-ISA-7] or [TOP-IF-6] is also reported, but each has a
  defined outcome ([programming rules](../doc/programmers_guide.md#programming-rules)),
  which the model applies, and the VER-1 comparison goes on. A test that
  breaks a rule on purpose (VER-10) expects exactly the reports it provokes;
  any other report fails the test.
- **Illegal instructions** ([TOP-ISA-2], including a JUMP outside
  [TOP-ISA-14]) are not model errors: they are legal behaviour with a defined
  outcome ([TOP-ISA-24]), compared like any other.

### ANEMOS kernel translation (VER-2)

The two encodings differ only in the data and ALU formats; the control format
is identical
([programmer's guide](../doc/programmers_guide.md#anemoss-layout)). Each
ANEMOS instruction word is rewritten field by field into a bankside word,
starting from all zeros:

| Field | ANEMOS bits | bankside bits | Translation |
|---|---|---|---|
| OPCODE | 31–28 | 31–28 | copied |
| DST, SRC0, SRC1 (operand codes) | 27–25, 24–22, 21–19 | same | copied |
| SRC2 (operand code) | 18–16 | 18–16 | MAD: copied, and must be SRF_A ([TOP-ISA-23]); MAC: set to GRF_B (1), as bankside's assembler writes it ([TOP-ISA-1]); ADD, MUL: 0 ([TOP-ISA-10]) |
| A (AAM, ALU format) | 15 | 15 | copied; must be 0 (non-AAM kernels only) |
| R (ReLU, data format) | 15 | 12 | moved |
| DST# | 14–10 (5 bits) | 10–8 (3 bits) | value copied if ≤ 7 |
| SRC0# | 9–5 (5 bits) | 6–4 (3 bits) | value copied if ≤ 7 |
| SRC1# | 4–0 (5 bits) | 2–0 (3 bits) | ALU format: value copied if ≤ 7; data format (MOV, FILL): 0, since bankside leaves bits 2–0 unused there |
| IMM0, IMM1 (control format) | 18–11, 10–0 | 18–11, 10–0 | copied, except JUMP's IMM0 (below); NOP's IMM1 and EXIT's IMM0 and IMM1 written as 0 ([TOP-ISA-25]) |
| every other bit | – | – | 0 ([TOP-ISA-1]) |

Rules of the translation:

- An index field whose operand is a bank is written as 0 ([TOP-ISA-9]),
  except MAD's SRC1#, which is copied because it is the SRF_A addend index
  ([TOP-ISA-20]). The result is the encoding bankside's assembler would write
  for the same program, MAC's SRC2 = 1 included, so the translated kernel is
  also a VER-1 stimulus. ANEMOS's own MAC words carry SRC2 = 0; both decoders
  ignore the field, so the rewrite changes no behaviour, only the word.
- A kernel is not translated if it has an index value above 7, A = 1, a
  reserved code, or an instruction illegal under [TOP-ISA-2] (a MAD whose
  SRC2 isn't SRF_A, [TOP-ISA-23]; a JUMP whose IMM0 is 0 or above its PC,
  [TOP-ISA-26]), or if it breaks [TOP-ISA-6] or [TOP-ISA-7]. Kernels that
  hit one of the control or ANEMOS-only differences below are not translated
  either.
- NOPs are inserted wherever [TOP-HAZ-3] (2 slots between a register write
  and a source read) or [TOP-HAZ-6] (3 slots between a bank store and a read
  of its column) needs them, and each JUMP's IMM0 is recomputed so that it
  still targets the same instruction. The translated kernel must still fit in
  the CRF (32 entries) and keep [TOP-ISA-7] and [TOP-ISA-14]; otherwise it is
  not translated.
- The host command stream for bankside is generated from the translated
  kernel: one trigger per bankside slot, with the addresses ANEMOS used for
  the same instruction. The commands ANEMOS spends on JUMP fetches have no
  bankside slot and are dropped ([TOP-ISA-4]). Inserted NOP slots get
  random addresses, which they don't use.
- ANEMOS is run with one command per cycle, so that its NOP, which counts
  cycles from its fetch and drops the commands in between, lasts the same
  number of commands as bankside's ([TOP-ISA-12]).

A kernel that can't be translated is reported by name with the reason and
skipped, never silently dropped. Exclusions are counted and reported with the
results.

**Intended differences.** Every row of the
[differences table](../doc/programmers_guide.md#differences-from-anemos) of
the programmer's guide, plus the FP16 ones of the
[theory of operation](../doc/theory_of_operation.md#fp16-arithmetic). The
spec records each next to its rule.

| Difference | Rule | How VER-2 handles it |
|---|---|---|
| Field layout | [programmer's guide](../doc/programmers_guide.md#anemoss-layout) | translated (table above) |
| ReLU of −0 and of NaNs with the sign bit set | [TOP-FP-8] | masked: lanes whose ReLU input is 0x8000 or 0xFC01 to 0xFFFF |
| `MOV(RELU)` into an SRF or a bank: ANEMOS ignores R | [TOP-ISA-30] | masked: lanes whose input has the sign bit set (for GRF → SRF, lane 0) |
| NaN bit patterns: 0x7E00 against ANEMOS's `half` library | [TOP-FP-6] | compared as a class (any NaN matches any NaN) |
| Commands per JUMP fetch: 0 against 1 | [TOP-ISA-4] | translated: ANEMOS's JUMP-fetch commands are dropped from bankside's stream; the comparison is of bank writes, not commands |
| `NOP n`: ANEMOS counts *n* cycles and drops commands meanwhile | [TOP-ISA-12] | ANEMOS run with one command per cycle; `NOP 0` (1 slot against 256) excluded |
| JUMP with IMM1 = 0 | [TOP-ISA-13] | excluded |
| JUMP with IMM0 = 0 or above its PC | [TOP-ISA-26] | excluded (illegal in bankside, not translated) |
| JUMP at a JUMP's target or after a JUMP | [TOP-ISA-27] | excluded (breaks [TOP-ISA-7]) |
| Nested loops: one loop state in both | [TOP-ISA-28] | no difference; excluded anyway (breaks [TOP-ISA-6]) and checked by VER-1 and VER-10 |
| EXIT and the loop state | [TOP-ISA-5] | runs that reach EXIT with `loop_active` = 1 excluded |
| Illegal words: no check in ANEMOS | [TOP-ISA-2], [TOP-ISA-24] | excluded (not translated) |
| MAD's addend other than SRF_A: legal in ANEMOS, illegal in bankside | [TOP-ISA-23] | excluded (not translated) |
| MAC's SRC2 as assembled: GRF_A (0) against GRF_B (1) | [TOP-ISA-1], [TOP-ISA-10] | translated to 1; no behaviour differs |
| MAD with a bank src0 and src1 = GRF_B: ANEMOS's decoder reads GRF_B at a stale index (an ANEMOS bug) | [TOP-ISA-19] ([MAD](../doc/programmers_guide.md#mad)) | excluded |
| FILL: not implemented in ANEMOS | [TOP-ISA-16] | FILL kernels not run |
| Configuration write while running: applied (and ORed with an S5 write) in ANEMOS, ignored in bankside | [TOP-IF-8] | not exercised: VER-2 host streams write only while idle ([TOP-IF-6]) |
| `err_illegal` and `busy`: no ANEMOS counterpart | [TOP-ISA-2], [TOP-IF-7] | not compared; checked by VER-1 and VER-13 |
| Index values 8 to 31 | [programmer's guide](../doc/programmers_guide.md#anemoss-layout) | excluded (not translated) |
| Register files on reset: ANEMOS clears them, bankside keeps them | [TOP-ARCH-5], [TOP-ARCH-9] | not compared: a kernel that reads an entry it never wrote breaks [TOP-ARCH-5]; the model reports it ([reference model](#reference-model)) and the kernel is excluded |
| Write-through: ANEMOS's reads return the stored value | [TOP-HAZ-1] | translated: bankside's gap slots are inserted ([TOP-HAZ-3]); the comparison doesn't depend on cycles |
| GRF_B read ports: ANEMOS ORs the accumulator index into port 1's | [TOP-ARCH-10] | excluded: kernels in which an instruction issued 1 or 2 ANEMOS commands after a MAC reads a GRF_B source at an index other than that MAC's DST# |
| When MOV and bank stores write: in ANEMOS's decode cycle, ahead of older pipelined writes | [TOP-PIPE-1] | excluded: kernels in which a MOV from a register is issued 1 to 3 ANEMOS commands after a bank load or an arithmetic instruction that writes the same register entry, so that ANEMOS could apply the two writes out of order (case H of the [theory of operation](../doc/theory_of_operation.md#worked-cases-all-writes-in-s5)) |
| Bank read after a bank store to its column: bankside needs 4 slots, ANEMOS's own distance is unknown | [TOP-HAZ-6] | translated with the 4-slot gap; ANEMOS kernels that read a column fewer than 4 commands after storing to it are excluded |

The masks are per lane and follow the value. The model marks a lane as
masked where a masked difference applies, and the mark travels with it: a
lane-wise operation with a masked operand lane gives a masked result lane, a
GRF → SRF move takes lane 0's mark, an SRF broadcast of a masked entry marks
all 16 lanes, a bank store keeps the marks with the column, and a write of an
unmasked value clears them. Bank writes are compared on their unmasked lanes,
and the count of masked lanes is reported.

The control differences change the control flow, not a value, so they can't be
masked per lane; the kernels or runs that hit them are excluded from VER-2 and
checked by VER-1 and VER-7 only. The command windows of the GRF_B-port and
[TOP-PIPE-1] rows come from ANEMOS's code as the spec reads it (read, not
run), each with one command of margin. The window of the bank row is
bankside's own distance, since ANEMOS's is unknown.

## FP16 units

- **[VER-4]** `fp16_mul` and `fp16_add` are verified on their own, before
  integration, against NumPy `float16` (a valid oracle, see
  [theory of operation](../doc/theory_of_operation.md#fp16-arithmetic)). Each
  is one combinational lane ([TOP-HIER-3]), so a test applies two operands and
  reads the result with no clock:
  - directed: ±0, ±Inf, NaNs, the smallest and largest subnormals and
    normals, results that overflow, underflow or are exactly halfway between
    two FP16 values (RNE ties)
  - random: a large sweep of operand pairs, weighted towards the special
    classes; the size depends on simulation speed (all 2³² pairs if a fast
    harness makes it practical)
  - non-NaN results are compared bit for bit with NumPy. A NaN result is
    checked bit-exact against 0x7E00 ([TOP-FP-6]): NumPy only says that the
    result is a NaN, and its bits are the host's. Every NaN operand class
    (quiet and signalling, either sign, several payloads, in either operand
    and in both) and both invalid operations (0 × ±Inf, Inf − Inf) are among
    the directed cases.

## Functional coverage

- **[VER-5]** Every legal (opcode, DST, SRC0, SRC1) combination
  ([programmer's guide](../doc/programmers_guide.md#legal-combinations-compared-with-the-paper)),
  with ReLU on and off for MOV. The bins, per opcode, are those of the yaml
  `legal` lists: ADD 40, MUL 32, MAC 16, MAD 32, MOV 20 pairs × R = 40,
  FILL 4.
  - MAC and MAD include the two same-file source pairs, (GRF_A, GRF_A) and
    (GRF_B, GRF_B) ([TOP-ISA-22]), each with two different entries as sources
    as well as the same entry twice: 2 bins for MAC, 4 for MAD (2
    destinations). They are part of the 16 and 32, not extra.
  - SRC2 is not a bin dimension. For MAD it has a single legal value, SRF_A
    ([TOP-ISA-23]); the other values are illegal classes (VER-8). For ADD,
    MUL and MAC it is ignored ([TOP-ISA-10]) and randomised by VER-12. R of
    FILL is ignored and randomised the same way.
  - Each combination with an SRF source also counts as an [TOP-ISA-11] case.
- **[VER-6]** Hazard distances:
  - register sources: distances 1 to 4 for every producer/consumer pair,
    including the accumulator bypass ([TOP-HAZ-2]) with each producer type,
    and back-to-back MACs into one GRF_B entry ([TOP-HAZ-4]). Distance 3 is
    the write-through case ([TOP-HAZ-1]).
  - bank columns: a store and then a read of its column 4 and 5 slots apart
    ([TOP-HAZ-6]), for each bank, the read being a load and an ALU bank
    source; distance 4 is the same-edge case, store applied first
    ([TOP-IF-3]).
  - GRF_B's three read ports ([TOP-ARCH-10]): a MAC, then 2 slots later an
    instruction that reads two GRF_B sources (`ADD GRF_A[0], GRF_B[1],
    GRF_B[2]`, and the MUL equivalent), so that all three ports read in one
    cycle at three different entries, with and without an S5 write to one of
    them in that cycle. Sharing a port, as ANEMOS does, would read a wrong
    entry here.

  Distances below the [TOP-HAZ-3] and [TOP-HAZ-6] limits are generated only
  by the VER-10 tests that break the rules on purpose.
- **[VER-7]** Control:
  - JUMP with IMM1 = 0 ([TOP-ISA-13]: body runs once, loop state stays clear,
    so a later JUMP starts a loop of its own), 1, and large; each row of the
    loop-state table ([TOP-ISA-3]); zero-slot JUMP ([TOP-ISA-4]); sequential
    loops; a JUMP with IMM0 = its PC (target 0) and IMM0 = 1, the two ends of
    [TOP-ISA-14]
  - NOP with IMM0 = 0, 1, > 1 and 255 ([TOP-ISA-12]): the next instruction
    issues on the trigger after the NOP's last slot, and IMM0 = 0 takes one
    slot, like IMM0 = 1. A NOP's slots are counted in triggers, not cycles:
    bubbles inside a NOP (case Q of [TOP-IF-7]) don't use up its slots
  - EXIT followed by a new run ([TOP-ISA-5]), including EXIT reached inside a
    loop body, so that the next run starts with the loop state clear
  - PC wrap from 31 to 0 ([TOP-ISA-8])
  - every slot is one pipeline entry ([TOP-PIPE-4]): an instruction, an
    illegal word, EXIT, each NOP slot and the `NOP 1` slot of [TOP-ISA-27];
    a JUMP makes none. Observed through `busy` (VER-13).
- **[VER-8]** Every class of illegal instruction ([TOP-ISA-2]):
  - a reserved opcode (3, 6, 7, 12 to 15)
  - a reserved operand code (6, 7) in a field the instruction uses
  - an operand combination outside the `legal` lists
  - A = 1
  - a MAD whose SRC2 is anything but SRF_A: the 7 values 0, 1, 2, 4, 5, 6
    and 7, the reserved codes included ([TOP-ISA-23])
  - a JUMP whose IMM0 is out of range ([TOP-ISA-14], [TOP-ISA-26]). This
    class depends on the JUMP's position: IMM0 = 0 at several PCs, IMM0 =
    PC + 1 and 255 at several PCs, and every JUMP at PC 0 (IMM0 = 0 and
    IMM0 ≥ 1). Also a JUMP out of range reached from another JUMP, so that it
    is held over by [TOP-ISA-27] and is illegal in the next slot.

  For each, the outcome of [TOP-ISA-24] is checked: one slot, no
  register-file write, `bank_rd_en` = 0 in its S1 cycle and no `bank_wr_en`
  in its S5 cycle, the loop state and NOP counter unchanged (also inside a
  loop body), PC ← PC + 1, the instructions before it complete, and the next
  trigger issues PC + 1. The timing of `err_illegal` is VER-13's.

  Negative cases, which must stay legal with `err_illegal` = 0: a reserved
  code in a field the instruction ignores ([TOP-ISA-10]), any value in the
  ignored IMM fields of NOP and EXIT ([TOP-ISA-25]), and any SRC2 of a MAC.
  MAC has no SRC2 illegal class: the hardware ignores the field
  ([TOP-ISA-10]). These are checked by VER-12.
- **[VER-9]** FP16 operand classes (zero, subnormal, normal, Inf, NaN) per
  arithmetic instruction, and the result classes (overflow, subnormal result,
  exact zero, ties, NaN).

Code coverage (line, branch, toggle) is collected through opendv as well.

## Assertions and broken rules

- **[VER-10]** The programming rules [TOP-HAZ-3], [TOP-HAZ-6], [TOP-ISA-6],
  [TOP-ISA-7], [TOP-ISA-14] and [TOP-IF-6] are checked by assertions in
  simulation. Constrained-random programs are generated legal; separate
  directed tests break each rule on purpose, to show the assertion fires on
  the violating instruction and on no other. Every broken rule has a defined
  outcome
  ([programming rules](../doc/programmers_guide.md#programming-rules)), so
  these tests also check that outcome, and keep comparing against the model
  after the violation (VER-1):
  - [TOP-HAZ-3] broken: the read returns the newest write to the entry whose
    S5 cycle is the read's cycle or earlier ([TOP-HAZ-5]). The expected value
    is predicted from the cycles of the trigger sequence, not from the slot
    count. Directed: cases B (an older write in flight) and C (a bubble, which
    gives the in-order result although the rule is broken in slots) of the
    [theory of operation](../doc/theory_of_operation.md#what-happens-when-a-rule-is-broken),
    and k = 1 and 2 with no bubbles.
  - [TOP-HAZ-6] broken: the bank read returns the newest store to its column
    whose S5 cycle is the read's S1 cycle or earlier, else the bank's earlier
    contents ([TOP-HAZ-7]), predicted from cycles in the same way. Directed:
    cases F (an older store in flight) and G (a bubble), and k = 1 to 3 with
    no bubbles.
  - [TOP-ISA-6] broken: one loop state for every JUMP ([TOP-ISA-28]).
    Directed: case 8 of the
    [programmer's guide](../doc/programmers_guide.md#when-a-jump-rule-is-broken),
    run for a fixed number of slots and then reset.
  - [TOP-ISA-7] broken: the second JUMP waits one `NOP 1` slot
    ([TOP-ISA-27]): no write, no bank access, no loop-state change,
    `err_illegal` stays 0. Directed: case 9 (a JUMP after a JUMP) and a JUMP
    at a JUMP's target.
  - [TOP-ISA-14] broken: the JUMP is illegal ([TOP-ISA-26]); its outcome is
    checked as a VER-8 class. The assertion fires as well.
  - [TOP-IF-6] broken: the configuration write is ignored ([TOP-IF-8]);
    checked by VER-14.

## Instructions

- **[VER-11] Instruction semantics.** A directed test per instruction checks
  its result against values computed in the test with NumPy `float16`, per
  lane, as well as against the model (VER-1):
  - MOV ([TOP-ISA-15]): every row of its table, with R = 0 and R = 1. GRF
    lanes hold distinct values, so that a wrong lane or a missing broadcast
    shows.
  - MOV from a GRF into an SRF ([TOP-ISA-29]): from GRF_A and GRF_B into
    SRF_M and SRF_A, with 16 distinct lanes, so that only lane 0 (bits 15–0)
    can arrive.
  - `MOV(RELU)` into each kind of destination ([TOP-ISA-30]): a GRF (all 16
    lanes), a bank (all 16 lanes, in `bank_wr_data`) and an SRF (the one
    value, after lane 0 is selected for GRF → SRF: lane 0 negative with the
    other lanes positive, and lane 0 positive with the other lanes negative).
  - FILL ([TOP-ISA-16]): the four bank load/store pairs, with R = 1 as well,
    to show R has no effect.
  - Bits through data movement ([TOP-FP-9]): every NaN pattern (both signs,
    quiet and signalling, all 1023 non-zero significands: 2046 patterns, 16
    per vector) through MOV with R = 0 (GRF → GRF, a bank load and store,
    GRF → SRF, SRF → GRF and SRF → SRF), through `MOV(RELU)` (a NaN with the
    sign bit clear passes bit for bit, one with it set becomes 0x0000) and
    through FILL (load and store, R = 0 and 1). Each must arrive bit for bit
    unchanged, except as [TOP-FP-8] says; it must not become 0x7E00.
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
  as the assembler writes it (those fields at 0, and MAC's SRC2 at 1), with
  `err_illegal` staying 0:
  - unused bits ([TOP-ISA-1])
  - the index field of a bank operand ([TOP-ISA-9]), but not MAD's SRC1#
    ([TOP-ISA-20])
  - SRC2 of ADD, MUL and MAC, every value from 0 to 7, including the reserved
    codes 6 and 7, which are not illegal there ([TOP-ISA-10]). For MAC this
    covers the assembler's GRF_B (1), ANEMOS's GRF_A (0) and every other
    value: each runs the same MAC.
  - IMM1 of NOP, and IMM0 and IMM1 of EXIT ([TOP-ISA-25])
  - R of FILL ([TOP-ISA-16])

  Random programs (see [Stimulus](#stimulus)) also randomise these fields.

## Interface and status

- **[VER-13] Status outputs.**
  - `busy` is checked in every cycle against [TOP-IF-7], predicted by the
    model from the trigger sequence, the resets, the NOP slots left and the
    loop state alone. Its exact edges: from idle, the first trigger in cycle
    *f* leaves `busy` = 0 in cycle *f* and makes it 1 from *f* + 1; after
    the last trigger, in cycle *l*, `busy` = 1 in *l* + 1 to *l* + 4 and 0
    from *l* + 5, unless NOP slots or a loop remain, in which case it stays
    1 until reset; and it is 0 from the cycle after a cycle with `rst_n` = 0.
    Directed: the worked cases of [TOP-IF-7] and
    [busy_trace.py](../doc/examples/busy_trace.py): P (the basic rise and
    fall), Q (bubbles inside a NOP), R (`busy` held by `loop_active` through
    bubbles inside a loop), S (the fall counts every slot, the NOP and EXIT
    entries too, [TOP-PIPE-4]) and T (the host stops inside a loop and resets
    it). Case P shows `busy` = 0 in the cycle of the first trigger, so a
    combinational path from `trig_valid` fails it; case S shows that a slot
    which writes nothing still keeps `busy` up.
  - `err_illegal` ([TOP-ISA-24]): 0 during the S1 cycle of the illegal
    instruction and 1 from the next cycle on; sticky through later legal
    instructions, EXIT and new runs; 0 from the cycle after a cycle with
    `rst_n` = 0 ([TOP-IF-4]). A held-over JUMP's `NOP 1` slot ([TOP-ISA-27])
    leaves it at 0.
- **[VER-14] Reset, configuration, debug and the bank port.**
  - Reset clears the control state ([TOP-IF-4]), also from inside a loop and
    inside a multi-cycle NOP, with entries in flight, and keeps the
    register-file contents ([TOP-ARCH-5]), read back through the debug port.
  - Configuration writes ([TOP-IF-5], [TOP-IF-9], [TOP-IF-10]): every select
    (0 to 7) with every index (0 to 31), while idle. A write to a valid entry
    takes `cfg_wr_data[W−1:0]`, and the bits above *W* are ignored (written
    as ones, read back as zeros). Select 4, 5 or 6, or an index of 8 to 31
    for a GRF or SRF, changes no entry of any file; in particular index *i*
    ≥ 8 leaves entry *i* mod 8 unchanged. Nothing is flagged.
  - Debug reads ([TOP-IF-11]): every select and index, zero-extended above
    *W*, and 0 for an unused select or an out-of-range index.
  - A debug read in the cycle of a write ([TOP-IF-12]) shows the value being
    written, for an S5 write of a running program and for a configuration
    write that takes effect, and the stored value from the next cycle on.
    A configuration write that is ignored ([TOP-IF-8], [TOP-IF-10]) is not
    shown.
  - Ignored configuration writes ([TOP-IF-8]): a write in a cycle with
    `busy` = 1 or `trig_valid` = 1 changes no entry, for every select,
    including the CRF while a program runs. The worked case of [TOP-IF-8]
    is a directed test: after a run's last trigger in cycle *c*, a write in
    cycle *c* + 2 and one in *c* + 4 are ignored, and one in *c* + 5 takes
    effect. A variant ends the run with a register write instead of EXIT, so
    that the write in *c* + 4 falls in that slot's S5 cycle: the S5 write
    goes ahead and the configuration write doesn't, also when both name the
    same entry. Also a write in the cycle of the first trigger, where
    `busy` is still 0 but `trig_valid` = 1. The [TOP-IF-6] assertion fires
    on each ignored write (VER-10), and nothing is flagged on the ports.
  - The bank model is the testbench's two banks, as the
    [theory of operation](../doc/theory_of_operation.md#the-v1-bank) gives
    them ([TOP-IF-2], [TOP-IF-3]): it samples `bank_rd_*` at the end of a
    cycle with `bank_rd_en` = 1 and drives `bank_rd_data` for the whole of
    the next cycle, and random data in every other cycle, so that a sample
    in the wrong cycle shows; it writes `bank_wr_data` at the end of a cycle
    with `bank_wr_en` = 1; it accepts a read and a write in the same cycle,
    to the same bank or not; and when both name the same column on the same
    edge it applies the write first, so the read returns the written data.
    It ignores `bank_rd_*` and `bank_wr_*` while their enable is 0.
  - The bank checks: `bank_rd_en` = 1 exactly in the S1 cycle of an
    instruction with a bank source, with `bank_rd_sel` the bank named and the
    address that cycle's trigger's ([TOP-ARCH-6]); `bank_wr_en` = 1 exactly
    in the S5 cycle of a bank store, to the bank its dst names and the
    address of its own trigger ([TOP-ARCH-8]), tested with different columns
    on the later triggers and with no trigger in the store's S5 cycle.

## Simulation runs and power-up values

- **[VER-15]** Register-file entries have no reset and no initial value, so
  an entry never written holds its power-up value ([TOP-ARCH-9]). As
  [TOP-ARCH-9] requires, every simulation:
  - builds the model with `--x-initial unique` (Verilator's default), and
  - runs it with `+verilator+rand+reset+2` and `+verilator+seed+<seed>`, so
    that each run gives every register-file bit a random power-up value
    drawn from the run's seed. Verilator's run-time default
    (`+verilator+rand+reset+0`) would make every unwritten entry read as 0,
    so no run may use it.
  - prints its seed, and accepts one to reproduce the run. The Verilator seed
    and the cocotb seed of the stimulus are the same number, so one seed
    reproduces both.

  A directed power-up test reads every entry of every file through the debug
  port before any write, and checks that the values are not all 0, that they
  differ between two seeds, that each read of an entry returns the same bits
  on every port (a program read too) until the entry is first written, and
  that a reset doesn't change them. A test that reads an unwritten entry on
  purpose checks only that stability; the model reports the read
  ([reference model](#reference-model)), and the VER-1 comparison stops
  there.

  **Known opendv gap.** opendv at `a30684a` can't do this today. Its
  simulator call (`opendv/simulator.py`) runs cocotb's `runner.test()`
  without `plusargs`, and its yaml has only `sim.build_args`, so no run-time
  plusarg reaches the simulator. Its seed reaches cocotb (as
  `COCOTB_RANDOM_SEED`), but not Verilator as `+verilator+seed`: cocotb
  2.1.0's Verilator runner doesn't turn the seed into a plusarg. So every
  opendv run uses Verilator's run-time default, and unwritten entries read as
  0. The fix belongs in opendv, and the user has been told; bankside does not
  work around it (no build-time substitute, no `initial` values, no wrapper
  script around opendv). Until it is fixed, VER-15 and the power-up test are
  unverified, and a test can pass with a missing load that random power-up
  values would catch.

## Structure

- **[VER-16]** The tests run on `top` as the opendv toplevel
  ([TOP-HIER-10]), with the ports and widths of
  [interfaces.md](../doc/interfaces.md). A structural test reaches each
  instance of [TOP-HIER-1] by its spec name through the cocotb handle
  (`ctrl`, `ctrl.dec`, `dp`, `crf`, `grf_a`, `grf_b`, `srf_m`, `srf_a`) and
  fails if one is missing. The lane instances inside `dp` are named by
  `pcu_datapath`'s doc, not yet written, and are left out until it is. The
  rest of the hierarchy rules are structure, not behaviour, and are checked
  in each module's own testplan (`src/<module>/dv/`) once the module exists
  (#12); the [coverage table](#requirement-coverage) says which.

## Stimulus

- Directed tests per instruction (VER-11), then kernels (GEMV, ADD, MUL, ReLU).
- Constrained-random microkernels: random legal instruction sequences that
  respect the programming rules, random register and bank contents, random
  values in ignored fields (VER-12), and random bubbles between triggers.
  Each run prints its seed and accepts one to reproduce it (VER-15).
- The host writes configuration only while `busy` = 0 and `trig_valid` = 0
  ([TOP-IF-6]), except in the VER-10 and VER-14 tests that break the rule on
  purpose. Every register-file entry a program reads, and every CRF entry it
  executes, is written first ([TOP-ARCH-5]), except in the VER-15 tests.
- `trig_valid` is held at 0 in cycles with `rst_n` = 0, and the bank-port
  checks are off in those cycles, until #41 settles what the unit does with a
  trigger during reset.

## Requirement coverage

Every requirement ID in the spec, with the VER items that check it, or
"uncovered" and why. VER-1 (bit-exact against the model) applies to every rule
the model implements; it is listed only where it is the main check.

| ID | Rule | Checked by |
|---|---|---|
| [TOP-ARCH-1] | one bank pair, at most one bank per instruction | VER-5, VER-8 |
| [TOP-ARCH-2] | 16 FP16 lanes | VER-1, VER-11 |
| [TOP-ARCH-3] | DRAM core clock, one instruction per cycle | VER-6 (issuing every cycle); the 300 MHz target is uncovered by simulation: it is a PPA result (syn) |
| [TOP-ARCH-4] | one write port per register file | VER-10 ([TOP-IF-6] assertion), VER-14 (a configuration write never meets an S5 write) |
| [TOP-ARCH-5] | register files not reset | VER-14, VER-15 |
| [TOP-ARCH-6] | bank address from the trigger | VER-14 |
| [TOP-ARCH-7] | at most one bank operand | VER-5, VER-8 |
| [TOP-ARCH-8] | bank writes in S5, to the store's own trigger | VER-14 |
| [TOP-ARCH-9] | power-up value of an entry never written | VER-15 (blocked by the opendv gap); the model's written flags ([reference model](#reference-model)) |
| [TOP-ARCH-10] | read ports: GRF_B 3, the others 1 or 2 | VER-6 (three GRF_B reads in one cycle) |
| [TOP-PIPE-1] | five stages, every write in S5, in program order | VER-1, VER-6 |
| [TOP-PIPE-2] | bubbles without triggers | VER-6, random bubbles in [Stimulus](#stimulus) |
| [TOP-PIPE-3] | NOP and JUMP slots | VER-7 |
| [TOP-PIPE-4] | every slot is one pipeline entry | VER-7, VER-13 (cases P to T; S shows that a slot which writes nothing still counts) |
| [TOP-HAZ-1] | write-through | VER-6 (distance 3), VER-14 (debug read in the cycle of a write) |
| [TOP-HAZ-2] | accumulator bypass | VER-6 |
| [TOP-HAZ-3] | 2 slots between producer and consumer | VER-10 |
| [TOP-HAZ-4] | MAC accumulator exempt | VER-6 |
| [TOP-HAZ-5] | outcome when [TOP-HAZ-3] is broken | VER-10 (cases B, C) |
| [TOP-HAZ-6] | 3 slots between bank store and read | VER-6 (distances 4, 5), VER-10 |
| [TOP-HAZ-7] | outcome when [TOP-HAZ-6] is broken | VER-10 (cases F, G) |
| [TOP-FP-1] | IEEE 754 binary16 | VER-4, VER-9 |
| [TOP-FP-2] | correctly rounded, RNE | VER-4, VER-9 |
| [TOP-FP-3] | MAC and MAD unfused | VER-3, VER-11 |
| [TOP-FP-4] | subnormals, overflow | VER-4, VER-9 |
| [TOP-FP-5] | IEEE special cases | VER-4, VER-9 |
| [TOP-FP-6] | canonical NaN 0x7E00 | VER-4 and VER-1 (bit-exact against 0x7E00), VER-9, VER-3; VER-2 compares NaNs as a class |
| [TOP-FP-7] | no exception flags | uncovered: there is no port to observe, so nothing to test in v1 |
| [TOP-FP-8] | ReLU on the sign bit | VER-5, VER-11, VER-3 (sign-bit NumPy reference), VER-2 (masked) |
| [TOP-FP-9] | MOV and FILL copy lane bits, NaNs included | VER-11 |
| [TOP-ISA-1] | unused bits ignored; the assembler writes 0, and GRF_B in MAC's SRC2 | VER-12 |
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
| [TOP-ISA-14] | JUMP IMM0 between 1 and its PC | VER-8, VER-10 (assertion), VER-7 (the two ends) |
| [TOP-ISA-15] | MOV | VER-11, VER-5 |
| [TOP-ISA-16] | FILL | VER-11, VER-12, VER-5 |
| [TOP-ISA-17] | ADD | VER-11, VER-5 |
| [TOP-ISA-18] | MUL | VER-11, VER-5 |
| [TOP-ISA-19] | MAD | VER-11, VER-5 |
| [TOP-ISA-20] | MAD addend index is SRC1# | VER-11 |
| [TOP-ISA-21] | MAC | VER-11, VER-5 |
| [TOP-ISA-22] | MAC and MAD: the 16 source pairs of MUL | VER-5 (same-file pair bins), VER-8 |
| [TOP-ISA-23] | MAD's SRC2 must be SRF_A | VER-8 |
| [TOP-ISA-24] | an illegal instruction is a one-slot NOP; `err_illegal` timing | VER-8, VER-13 |
| [TOP-ISA-25] | NOP, JUMP, EXIT: ignored IMM fields never illegal | VER-12, VER-8 (negative case) |
| [TOP-ISA-26] | a JUMP with IMM0 out of range is illegal | VER-8 |
| [TOP-ISA-27] | a JUMP reached from a JUMP waits one `NOP 1` slot | VER-10, VER-8 (held-over illegal JUMP), VER-13 |
| [TOP-ISA-28] | one loop state for every JUMP | VER-10 |
| [TOP-ISA-29] | lane numbering; GRF → SRF takes lane 0 | VER-11 |
| [TOP-ISA-30] | R applies on every MOV pair | VER-11, VER-2 (masked) |
| [TOP-IF-1] | one slot per `trig_valid` | VER-7, VER-13 |
| [TOP-IF-2] | bank read timing | VER-14 |
| [TOP-IF-3] | bank write timing; write first on the same edge | VER-14, VER-6 (bank distance 4) |
| [TOP-IF-4] | reset | VER-14, VER-13 |
| [TOP-IF-5] | configuration write timing | VER-14 |
| [TOP-IF-6] | host writes only while idle | VER-10 |
| [TOP-IF-7] | `busy` | VER-13 |
| [TOP-IF-8] | a configuration write that breaks [TOP-IF-6] is ignored | VER-14 |
| [TOP-IF-9] | select codes | VER-14 |
| [TOP-IF-10] | which configuration writes take effect | VER-14 |
| [TOP-IF-11] | what a debug read returns | VER-14 |
| [TOP-IF-12] | a debug read in the cycle of a write | VER-14 |
| [TOP-HIER-1] | the v1 modules, instance names and prefixes | VER-16 (instance names); the prefixes are uncovered by simulation: they are names in the docs |
| [TOP-HIER-2] | stage ownership: S1 in `pcu_ctrl`, S2 to S5 in `pcu_datapath` | uncovered at top: no program sees which module holds a stage register; checked by the `pcu_ctrl` and `pcu_datapath` testplans (#30, #32) |
| [TOP-HIER-3] | `fp16_mul` and `fp16_add`: one lane, combinational | VER-4 |
| [TOP-HIER-4] | `pcu_regfile`: combinational, write-through, one write port, no reset | VER-6, VER-14, VER-15 at top; every port of the module in the `pcu_regfile` testplan (#35) |
| [TOP-HIER-5] | the accumulator bypass is `grf_b`'s write-through | VER-6 checks the behaviour ([TOP-HAZ-2]); the way it is built is uncovered at top, since no program tells it apart ([hierarchy](../doc/hierarchy.md#choices-weighed)) |
| [TOP-HIER-6] | write-port select | VER-14 |
| [TOP-HIER-7] | debug read select; tied off for synthesis | VER-14; the tie-off is uncovered by simulation: it is a syn result |
| [TOP-HIER-8] | `busy` is the OR of `ctrl`'s and `dp`'s | VER-13 at top; each term in the `pcu_ctrl` and `pcu_datapath` testplans (#30, #32) |
| [TOP-HIER-9] | one shared SystemVerilog package | uncovered: a rule on where types live, with no behaviour to simulate; checked in design review |
| [TOP-HIER-10] | no wrapper: `top` is the unit | VER-16 |

Open spec work that may change the checks above: #27 (the zero-slot JUMP fetch
and the CRF's read ports, settled with `pcu_ctrl` in #30) may change
[TOP-ISA-27] and with it the VER-10 and VER-8 cases built on it; #41 (a
trigger during reset) may add a VER-14 case and lift the reset rule in
[Stimulus](#stimulus). The child modules' docs (#30 to #35) add their own IDs,
which go in their own testplans.
