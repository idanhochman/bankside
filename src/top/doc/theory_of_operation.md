# Theory of operation

## Block diagram

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
- **[TOP-FP-6]** Every NaN result is the **canonical quiet NaN 0x7E00**. Payloads
  and signs of NaN inputs are not propagated. **[bankside]**
- **[TOP-FP-7]** No exception flags are kept. **[bankside]**

**Reference.** NumPy's `float16` arithmetic is correctly rounded for `+` and
`×`. NumPy computes in float32 and rounds once more to FP16, and that double
rounding is harmless because float32's 24-bit significand is at least
2 × 11 + 2 bits. So NumPy is a valid oracle, except for NaN bit patterns
([TOP-FP-6]); NaNs are compared as a class.

## ReLU

- **[TOP-FP-8]** MOV with R = 1 applies ReLU per lane through a 2:1 multiplexer on
  the sign bit: if the sign bit is 1 the lane becomes +0 (0x0000), otherwise it
  passes unchanged. **[paper]** (the sign-bit multiplexer).

  As a result, −0 → +0, and any NaN with the sign bit set → +0. ANEMOS
  compares the value against zero instead, so on those two inputs bankside
  **intentionally differs** from ANEMOS. See [verification](../dv/README.md).

## Bank access

- **[TOP-ARCH-6]** The bank operand's address is implicit: the row and column of
  the triggering command. **[paper]** In v1 the testbench supplies these with
  the trigger ([interfaces.md](interfaces.md)).
- **[TOP-ARCH-7]** At most one bank operand per instruction (one column read per
  command). **[paper]** (Table II's MUL and ADD combination counts follow from
  it; see the programmer's guide for MAC/MAD).
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
