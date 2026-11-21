# Theory of operation

## Block diagram

The blocks below are split into modules in [hierarchy.md](hierarchy.md).

```
            triggering command (one per slot)
                     │
  host cfg ──►┌──────▼──────┐
  writes      │  CRF  32×32 │──► fetch/decode ── PC, loop counter, NOP counter
              └─────────────┘          │
                                       ▼ control
  ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────┐
  │ GRF_A 8×256  │ │ GRF_B 8×256  │ │ SRF_M 8×16│ │ SRF_A 8×16│
  └──────┬───────┘ └──────┬───────┘ └─────┬─────┘ └─────┬─────┘
         └────────┬───────┴───────────────┴─────────────┘
                  ▼ operand switch (+ bank read data)
          ┌───────────────┐   ┌───────────────┐
          │ 16 × FP16 MUL │──►│ 16 × FP16 ADD │◄── GRF_B accumulator
          └───────────────┘   └───────┬───────┘    (late read + bypass)
                                      ▼
                       write-back: GRF / SRF / bank write port
```

## Architecture

- **[TOP-ARCH-1]** One unit serves one bank pair, EVEN_BANK and ODD_BANK, and
  accesses at most one of them per instruction. **[paper]**
- **[TOP-ARCH-2]** The datapath has 16 lanes of IEEE 754 binary16 (FP16), 256 bits
  in total, which is one DRAM column access. **[paper]**
- **[TOP-ARCH-3]** The clock is the DRAM core clock (300 MHz target). One
  column-command slot (tCCD_L = 4 tCK at 1.2 GHz) equals one unit clock, so the
  unit must accept one instruction per cycle. **[paper]**

### Register files

| Register file | Size | Read ports | Notes |
|---|---|---|---|
| CRF | 32 × 32-bit | 1 (fetch) | The microkernel. **[paper]** |
| GRF_A | 8 × 256-bit | 2 (S2) | Paired with the even bank. **[paper]** |
| GRF_B | 8 × 256-bit | 2 (S2) + 1 (S4, accumulator) | Paired with the odd bank; MAC accumulates here. **[paper]** |
| SRF_M | 8 × 16-bit | 1 (S2) | Scalar multiplier operand, broadcast to all 16 lanes. **[paper]** |
| SRF_A | 8 × 16-bit | 1 (S2) | Scalar addend, broadcast to all 16 lanes. **[paper]** |

- **[TOP-ARCH-4]** Each register file has one write port, used by stage S5 and, when
  the unit is idle (`busy = 0` and `trig_valid = 0`, [TOP-IF-6]), by the host
  configuration port. **[bankside]**
- **[TOP-ARCH-5]** Register-file contents are **not reset**. Only control state (PC,
  the loop state of [TOP-ISA-3], NOP counter, pipeline valid bits,
  `err_illegal`) is reset ([TOP-IF-4]). Programs
  must write a register before reading it. The reference model tracks
  uninitialised entries and reports a read of one as an error. **[bankside]**
  The register files are about 4.6 kbit of state, so not resetting them saves
  area.

## Pipeline

Five stages. **[paper]** for the stages and their order; **[bankside]** for
what is read and written in each.

| Stage | Name | What happens |
|---|---|---|
| S1 | Fetch/decode | Read CRF[PC] and decode. Resolve JUMP (zero slots). Issue the bank read request. |
| S2 | Operand | Bank read data arrives. Read GRF/SRF source operands (everything except the MAC accumulator). MOV applies ReLU here when R = 1 (FILL ignores R, [TOP-ISA-16]). |
| S3 | MULT | 16 FP16 multipliers (MUL, MAD, MAC). Other instructions pass through. |
| S4 | ADD | 16 FP16 adders (ADD, MAD, MAC). MAC reads its accumulator here. Others pass through. |
| S5 | Write-back | Write the GRF or SRF, or drive the bank write port. |

- **[TOP-PIPE-1]** Every instruction passes through all five stages in order. An
  instruction that doesn't use MULT or ADD carries its value through that
  stage unchanged. This keeps every write in S5 and in program order.
  **[bankside]**
- **[TOP-PIPE-2]** The pipeline is clocked continuously. A cycle with no triggering
  command inserts a bubble; instructions already in flight keep moving and
  complete. **[bankside]**
- **[TOP-PIPE-3]** A multi-cycle NOP occupies one slot per triggering command for
  IMM0 slots (one slot if IMM0 = 0, [TOP-ISA-12]). JUMP occupies no slot
  ([TOP-ISA-4]). **[paper]** (zero-cycle JUMP), **[ANEMOS]** (NOP count).

### Timing of one instruction

Instruction *i* issued in cycle *c*:

| cycle | c | c+1 | c+2 | c+3 | c+4 |
|---|---|---|---|---|---|
| stage | S1 | S2 | S3 | S4 | S5 |
| events | fetch, decode, bank request | bank data, read sources | multiply | add, read accumulator | write |

## Hazards

The unit **cannot stall**. Each instruction is triggered by a host command at a
fixed rate, and nothing tells the host to wait. Dependencies are therefore
handled by forwarding where the published kernels need it, and by a
programming rule everywhere else. **[bankside]**

- **[TOP-HAZ-1]** Register files are **write-through**: a read in S2 in the same
  cycle as an S5 write to the same entry returns the new value. **[bankside]**
- **[TOP-HAZ-2]** **Accumulator bypass.** MAC reads its accumulator GRF_B[DST#] in
  S4, not S2. If the instruction in S5 in that cycle writes the same GRF_B
  entry, the accumulator is taken from the S5 result instead of the register
  file. This applies whatever the producer is (MAC, ADD, MUL, MAD, MOV or FILL).
  **[bankside]**
- **[TOP-HAZ-3]** **Programming rule for source operands.** An instruction must not
  read a GRF or SRF entry as a source (anything read in S2) if that entry is
  written by an instruction issued fewer than **3 slots** earlier. In other
  words, at least 2 slots must separate the producer from the consumer.
  **[bankside]**
- **[TOP-HAZ-4]** The MAC accumulator has no such rule: a MAC may follow any
  producer of its GRF_B entry immediately. **[bankside]**

### Why the distance is 3

Producer *P* issued at cycle *c* writes in S5, cycle *c+4*. Consumer *C* issued
*k* slots later:

| Consumer reads in | at cycle | needs | so |
|---|---|---|---|
| S2 (sources) | c+k+1 | c+k+1 ≥ c+4 (write-through, [TOP-HAZ-1]) | k ≥ 3 |
| S4 (MAC accumulator) | c+k+3 | k = 1: bypass from S5 ([TOP-HAZ-2]); k ≥ 2: register file | k ≥ 1 |

Bubbles only add cycles between producer and consumer, so counting in slots is
always safe.

Back-to-back MACs into one GRF_B entry, as in the published GEMV kernels,
therefore run at one per cycle. The bypass forms a one-cycle loop through the
FP16 adder, so the adder must fit in one clock period.

### What happens when a rule is broken

- **[TOP-HAZ-5]** The hardware still does something defined: the S2 read returns
  whatever the register file holds in that cycle (the old value). An SVA
  assertion flags it in simulation, the reference model raises an error, and
  the assembler rejects the program. **[bankside]**

## FP16 arithmetic

- **[TOP-FP-1]** Format: IEEE 754-2019 binary16. **[paper]** (FP16), **[bankside]**
  (full IEEE behaviour).
- **[TOP-FP-2]** MUL and ADD are each **correctly rounded**, with
  round-to-nearest, ties-to-even. **[ANEMOS]** (its `half.hpp` defaults),
  **[bankside]**
- **[TOP-FP-3]** MAC and MAD are **unfused**: two roundings. **[ANEMOS]**
  (measured bit-exact), matching the paper's separate MULT and ADD stages.
  - MAC: `acc ← round(acc + round(a × b))`
  - MAD: `d ← round(round(a × b) + c)`
- **[TOP-FP-4]** Subnormals are supported as inputs and outputs (no flush to zero).
  Overflow rounds to ±Inf according to RNE. **[bankside]**
- **[TOP-FP-5]** Special cases follow IEEE 754: 0 × ±Inf = NaN, Inf − Inf = NaN,
  any NaN input gives a NaN result, x + (−x) = +0, (−0) + (−0) = −0, and the
  sign of a product is the XOR of the operand signs. **[bankside]**
- **[TOP-FP-6]** Every NaN that MUL, ADD, MAC or MAD produces is the
  **canonical quiet NaN 0x7E00** (sign 0, exponent all ones, significand
  `10 0000 0000`). This holds whatever made the result a NaN: a NaN operand of
  either sign, quiet or signalling, with any payload, or an invalid operation
  (0 × ±Inf, Inf − Inf). The payloads and signs of NaN operands are not
  propagated. In MAC and MAD it holds at each of the two roundings of
  [TOP-FP-3]: a NaN product is 0x7E00, and so is the sum it then feeds.
  **[bankside]**. The papers say nothing about NaNs. ANEMOS doesn't settle
  them either; it inherits them from its FP16 library (see
  [NaN results compared](#nan-results-compared) for why it isn't followed as
  the tiebreaker). Data movement keeps NaNs as they are ([TOP-FP-9]).
- **[TOP-FP-7]** No exception flags are kept. **[bankside]**

**Reference.** NumPy's `float16` arithmetic is correctly rounded for `+` and
`×`. NumPy computes in float32 and rounds once more to FP16, and that double
rounding is harmless because float32's 24-bit significand is at least
2 × 11 + 2 bits. So NumPy is a valid oracle, except for NaN bit patterns:
NumPy's NaN bits come from the host's floating-point unit and differ from
[TOP-FP-6] (see the NumPy column below), so NumPy can only tell that a result
is a NaN. The bit pattern of a NaN result is fixed by [TOP-FP-6] alone.

### NaN results compared

The cases below are each FP16 operation on the bits shown (`a + b` or
`a × b`, with *a* first). The bankside column is [TOP-FP-6]. The ANEMOS
column is the `half` library that its SystemC model computes with (half 2.2.0,
`src/half.hpp` at ANEMOS commit `f2d4018`), compiled and run. The NumPy column
is NumPy 2.5.1 `float16` on x86-64, run. Both alternatives propagate an input
NaN, as IEEE 754-2019 recommends:

| Operation | Case | bankside ([TOP-FP-6]) | ANEMOS (half 2.2.0) | NumPy 2.5.1, x86-64 |
|---|---|---|---|---|
| ADD 0x7C00, 0xFC00 | Inf − Inf (invalid) | 0x7E00 | 0x7FFF | 0xFE00 |
| MUL 0x0000, 0x7C00 | 0 × Inf (invalid) | 0x7E00 | 0x7FFF | 0xFE00 |
| ADD 0xFE00, 0x3C00 | negative quiet NaN + 1 | 0x7E00 | 0xFE00 | 0xFE00 |
| MUL 0x7C01, 0x3C00 | signalling NaN × 1 | 0x7E00 | 0x7E01 | 0x7E01 |
| ADD 0x7E01, 0xFE02 | two NaNs | 0x7E00 | 0x7E01 | 0xFE02 |
| ADD 0xFE02, 0x7E01 | the same, swapped | 0x7E00 | 0xFE02 | 0x7E01 |
| ADD 0x3C00, 0xFE02 | NaN second | 0x7E00 | 0xFE02 | 0xFE02 |

What the cases show:

- The two propagating references disagree with each other on 4 of the 7
  cases. For an invalid operation half returns 0x7FFF and x86 returns its
  negative default NaN (0xFE00). With two NaN operands half keeps the first and
  x86 NumPy the second. So propagation would not give bankside a bit-exact
  oracle either: a NaN would still be compared as a class against one of them.
- Under propagation the result of an instruction with two NaN operands
  depends on which operand reaches which adder or multiplier input. The bankside
  spec doesn't otherwise fix that order (ADD and MUL are commutative), and it
  would have to for MAC's accumulator and MAD's addend too. With [TOP-FP-6] the
  order never shows.
- A canonical NaN is one constant on the unit's output multiplexer.
  Propagation needs a NaN detector on each operand, a 16-bit selection between
  the operands and a forced quiet bit, per lane, in each of the 32 FP16 units.
  Both are small; the canonical NaN is the smaller.
- IEEE 754-2019 recommends ("should") but does not require that a NaN result
  carry an input NaN's payload, and it doesn't specify a NaN's sign, so
  [TOP-FP-6] is conforming ([TOP-FP-1]). RISC-V's F and Zfh extensions make the
  same choice (the canonical NaN is 0x7E00 in half precision).

Why ANEMOS isn't the tiebreaker here: its NaN bits are not a choice its model
makes but a property of whichever FP16 library is compiled in. Its SystemC
model uses half, with the rules in the table (the first NaN operand, quietened;
0x7FFF for an invalid operation). Its HLS path (`__SYNTHESIS__`) uses
the AC datatypes' `ac_ieee_float16` instead, whose NaN rule we haven't checked. The
draft's choice stands: **[bankside]**.

For DV: against ANEMOS ([VER-2]) and NumPy ([VER-4]) a NaN result can only
be compared as a class, as the verification plan already says. Because
[TOP-FP-6] fixes the pattern, a NaN result can in addition be checked bit-exact
against 0x7E00, both in the RTL-versus-model comparison ([VER-1]) and on the
FP16 units on their own.

## ReLU

- **[TOP-FP-8]** MOV with R = 1 applies ReLU to each lane by its sign bit
  (bit 15) alone: if the sign bit is 1 the lane becomes +0 (0x0000), and if it
  is 0 the lane passes unchanged ([TOP-FP-9]). The exponent and significand are
  not looked at. **[paper]**: ISCA 2021, Section III-C, implements ReLU as "a
  2-to-1 multiplexer controlled by the sign bit of a given input value".

  ANEMOS instead compares the value with zero: `in < 0 ? half_cast<half>(0.0)
  : in` (`src/grf.cpp`, ANEMOS commit `f2d4018`). That comparison is false for
  −0 and for every NaN, so ANEMOS passes them through unchanged. The paper
  states the mechanism, so the paper is followed; the tiebreaker isn't needed.
  (The same paper paragraph also says ReLU "returns zero if a given input value
  is a negative number"; −0 and NaNs aren't negative numbers, and the
  multiplexer sentence is the one that defines what happens to them.) bankside
  therefore **intentionally differs** from ANEMOS on −0 and on NaNs with the
  sign bit set, and only there: the two rules differ on 1024 of the 65536 input
  patterns, 0x8000 and 0xFC01 to 0xFFFF. [VER-2] masks them.

- **[TOP-FP-9]** MOV with R = 0 and FILL copy each lane's 16 bits unchanged,
  NaNs included: a signalling NaN stays signalling, and a NaN's sign and payload
  are kept. With R = 1, MOV changes a lane only as [TOP-FP-8] says, so a NaN
  with the sign bit clear also passes bit for bit. [TOP-FP-6] applies to
  arithmetic results only. **[bankside]**. ANEMOS also copies the bits (the
  run below shows 0x7C01 and 0xFC01 kept by its MOV(RELU) path).

### ReLU compared

Each input is one lane of a `MOV(RELU)`. The ANEMOS column is its `grf.cpp`
expression on the half 2.2.0 type, compiled and run:

| Input | Class | bankside ([TOP-FP-8]) | ANEMOS (value < 0) |
|---|---|---|---|
| 0x3C00 | +1 | 0x3C00 | 0x3C00 |
| 0xBC00 | −1 | 0x0000 | 0x0000 |
| 0x0000 | +0 | 0x0000 | 0x0000 |
| 0x8000 | −0 | 0x0000 | 0x8000 |
| 0x8001 | smallest negative subnormal | 0x0000 | 0x0000 |
| 0x7C00 | +Inf | 0x7C00 | 0x7C00 |
| 0xFC00 | −Inf | 0x0000 | 0x0000 |
| 0x7E00 | positive quiet NaN | 0x7E00 | 0x7E00 |
| 0x7C01 | positive signalling NaN | 0x7C01 | 0x7C01 |
| 0xFE00 | negative quiet NaN | 0x0000 | 0xFE00 |
| 0xFC01 | negative signalling NaN | 0x0000 | 0xFC01 |

Where the options differ in a program: a kernel that loads a column holding
−0 or a negative NaN with `MOV(RELU) GRF_A[0], EVEN_BANK` and stores it back
writes 0x0000 in bankside and the input unchanged in ANEMOS. Combined with
[TOP-FP-6], a NaN that bankside's own arithmetic produces is always 0x7E00,
whose sign bit is clear, so it survives a later ReLU as a NaN in both models;
only NaNs with the sign bit set that come from the bank or the host are
cleared to +0.

A NumPy reference for ReLU (as in [VER-3]) has to use the sign bit too, for
example `np.where(np.signbit(x), np.float16(0), x)`, which matches
[TOP-FP-8] on all 65536 patterns. `np.maximum(x, 0)` does not: it returns
0x8000 for −0 and passes NaNs through.

The cases are checked by [examples/fp_relu_nan.py](examples/fp_relu_nan.py),
and the ANEMOS and NumPy columns come from runs it compares against
([examples/README.md](examples/README.md)).

## Bank access

- **[TOP-ARCH-6]** The bank operand's address is implicit: the row and column of
  the triggering command. **[paper]** In v1 the testbench supplies these with
  the trigger ([interfaces.md](interfaces.md)).
- **[TOP-ARCH-7]** At most one bank operand per instruction (one column read per
  command). **[paper]** (Table II's MUL and ADD combination counts follow from
  it; for MAC and MAD see [TOP-ISA-22] in the
  [programmer's guide](programmers_guide.md#legal-combinations-compared-with-the-paper)).
- **[TOP-ARCH-8]** Bank writes (MOV/FILL to a bank) are driven in S5, to the address
  of the instruction's own triggering command. **[bankside]**, v1 only; v2
  revisits this against the real DRAM write timing.
- **[TOP-HAZ-6]** **Programming rule for bank columns.** In v1, an instruction
  must not read a bank column (same bank, row and column) that a bank store
  issued fewer than **4 slots** earlier writes. In other words, at least 3
  slots must separate the store from the read. If the rule is broken the read
  returns the old data. The write is driven in S5 (cycle c+4); a later read is
  requested in S1 and sampled by the bank at the end of that cycle, and the v1
  bank applies writes before reads on the same clock edge ([TOP-IF-3]), so
  k ≥ 4. **[bankside]**
