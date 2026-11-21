# Programmer's guide

The encoding tables here are written from
[`bankside_isa.yaml`](bankside_isa.yaml). If they ever disagree,
the YAML file is right.

## Instruction formats

All instructions are 32 bits. **[paper]** (Table III) for the field layout.

| Bits | 31–28 | 27–25 | 24–22 | 21–19 | 18–16 | 15 | 14–13 | 12 | 11 | 10–8 | 7 | 6–4 | 3 | 2–0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Control** | OPCODE | – | – | – | IMM0 | IMM0 | IMM0 | IMM0 | IMM0 | IMM1 | IMM1 | IMM1 | IMM1 | IMM1 |
| **Data** | OPCODE | DST | SRC0 | – | – | – | – | R | – | DST# | – | SRC0# | – | – |
| **ALU** | OPCODE | DST | SRC0 | SRC1 | SRC2 | A | – | – | – | DST# | – | SRC0# | – | SRC1# |

- Control: **IMM0** is bits 18–11 (8 bits), **IMM1** is bits 10–0 (11 bits).
- **R** is the ReLU flag (data format), **A** the AAM flag (ALU format).
- **DST#, SRC0#, SRC1#** are 3-bit register indices. They are ignored for bank
  operands.
- **[ISA-1]** Unused bits (–) are written as 0 by the assembler and ignored by
  the hardware. **[bankside]**

## Opcodes and operand codes

**[ANEMOS]** for the values.

| Opcode | Instruction | Format | | Code | Operand |
|---|---|---|---|---|---|
| 0 | NOP | control | | 0 | GRF_A |
| 1 | JUMP | control | | 1 | GRF_B |
| 2 | EXIT | control | | 2 | SRF_M |
| 4 | MOV | data | | 3 | SRF_A |
| 5 | FILL | data | | 4 | EVEN_BANK |
| 8 | ADD | ALU | | 5 | ODD_BANK |
| 9 | MUL | ALU | | 6, 7 | reserved |
| 10 | MAD | ALU | | | |
| 11 | MAC | ALU | | | |
| 3, 6, 7, 12–15 | reserved | | | | |

## Illegal instructions

- **[ISA-2]** An instruction is illegal if it uses a reserved opcode, a
  reserved operand code, an operand combination not listed below, or (in v1)
  A = 1. An illegal instruction executes as a one-slot NOP and sets the sticky
  `err_illegal` flag ([interfaces.md](interfaces.md)). **[bankside]**

## Instruction reference

Notation: `GRF_A[i]` is entry *i* of GRF_A; a scalar register used as a vector
operand is broadcast to all 16 lanes; arithmetic is per lane, per
[FP16 arithmetic](theory_of_operation.md#fp16-arithmetic).

### NOP

`NOP n` does nothing for *n* slots. IMM0 = *n*; 0 is treated as 1. **[paper]**
(multi-cycle NOP), **[ANEMOS]** (IMM0 = slot count), **[bankside]** (0 → 1).

### JUMP

`JUMP -off, count` is a backward branch for loops. IMM0 = *off*, the backward
offset; IMM1 = *count*, the number of jumps taken. **[paper]** (syntax, zero
cycles), **[ANEMOS]** (which immediate is which, counting).

- **[ISA-3]** The first time the JUMP is reached, a loop starts: PC ← PC − IMM0,
  and the loop counter ← IMM1 − 1. Each later time it is reached: if the
  counter is non-zero, PC ← PC − IMM0 and the counter decrements; otherwise
  the loop ends and PC ← PC + 1.
- So the jump is taken IMM1 times, and **the loop body runs IMM1 + 1 times**.
  `JUMP -1, 7` runs the instruction above it 8 times. IMM1 = 0 means the JUMP
  is never taken. **[bankside]** (IMM1 = 0)
- **[ISA-4]** A JUMP occupies no slot: it is resolved in S1 and the next
  instruction (the target, or PC + 1) is fetched in the same cycle.
- IMM0 must be between 1 and the JUMP's own PC.

### EXIT

`EXIT` ends the microkernel. **[ISA-5]** PC ← 0 and the loop state is cleared;
it occupies one slot. Instructions already in the pipeline complete. The next
triggering command starts again at CRF[0]. **[ANEMOS]**, **[bankside]**
(clearing the loop state).

### MOV

`MOV dst, src` or `MOV(RELU) dst, src` copies a register or bank column.
**[paper]** (GRF ← GRF/bank, ReLU), **[ANEMOS]** (SRF and bank destinations,
the even/odd pairing, GRF → SRF uses lane 0).

| src → dst | Operation |
|---|---|
| GRF → GRF | vector copy |
| SRF → GRF | scalar broadcast to 16 lanes |
| GRF → SRF | lane 0 of the GRF entry |
| SRF → SRF | scalar copy |
| EVEN_BANK → GRF_A, ODD_BANK → GRF_B | bank load |
| GRF_A → EVEN_BANK, GRF_B → ODD_BANK | bank store |

Any other pair is illegal, including bank ↔ SRF, bank → bank and crossed
pairs such as EVEN_BANK → GRF_B. With R = 1, ReLU ([FP-8]) is applied to the
value on its way.

### FILL

`FILL dst, src` moves data between a bank and the GRF: only the four bank
load/store pairs of MOV are legal. R is ignored. **[Hot Chips]** (FILL exists,
bank ↔ GRF), **[bankside]** (defined as this restricted MOV, since ANEMOS
leaves FILL unimplemented).

### ADD

`ADD dst, src0, src1`: dst ← src0 + src1. **[paper]**

- src0, src1 ∈ {GRF_A, GRF_B, EVEN_BANK, ODD_BANK, SRF_A}; dst ∈ {GRF_A, GRF_B}.
- At most one bank operand, and SRF_A at most once.

### MUL

`MUL dst, src0, src1`: dst ← src0 × src1. **[paper]**

- src0 ∈ {GRF_A, GRF_B, EVEN_BANK, ODD_BANK}; src1 ∈ {GRF_A, GRF_B,
  EVEN_BANK, ODD_BANK, SRF_M}; dst ∈ {GRF_A, GRF_B}.
- At most one bank operand.

### MAD

`MAD dst, src0, src1, SRF_A[j]`: dst ← round(round(src0 × src1) + SRF_A[j]).
**[paper]**

- Operands as for MUL. SRC2 is always SRF_A, and **its index is SRC1#**:
  *j* must equal src1's index (the assembler checks this). If src1 is a bank,
  *j* is still taken from the SRC1# field. The SRC2 field must hold the SRF_A
  code (3); anything else is illegal.

### MAC

`MAC GRF_B[i], src0, src1`: GRF_B[i] ← round(GRF_B[i] + round(src0 × src1)).
**[paper]** (Table II; GRF_B is the only destination).

- src0, src1 as for MUL; dst is GRF_B only. The SRC2 field is ignored.
- The accumulator is read late, in S4, with a bypass ([HAZ-2]). A MAC may
  follow the previous write of its GRF_B entry immediately.
- The paper's Fig. 7 and the Hot Chips slides show `MAC GRF_A, …`, which
  contradicts Table II and the text. bankside treats the figure as an erratum.

### Legal combinations compared with the paper

| Op | bankside | Paper (Table II) | Note |
|---|---|---|---|
| MUL | 32 | 32 | |
| ADD | 40 | 40 | |
| MAC | 16 | 14 | The paper excludes two more source pairs, but doesn't say which. bankside allows them. |
| MAD | 32 | 28 | Same two pairs, × 2 destinations. |
| MOV | 20 pairs (× ReLU on/off) | 24 | bankside adds SRF and bank stores (ANEMOS), the paper counts GRF/bank → GRF |
| FILL | 4 | 12 (Hot Chips) | Restricted to bank ↔ GRF |

## Programming rules

A program that breaks one of these still executes, but its result is not what
was meant. The assembler and the reference model reject it, and an assertion
flags it in simulation ([HAZ-5]).

1. **[HAZ-3]** At least **2 slots between** a write to a GRF/SRF entry and an
   instruction that reads it as a source. The MAC accumulator is exempt
   ([HAZ-4]).
2. **[HAZ-6]** At least **3 slots between** a bank store and a read of the same
   bank column (v1 bank model).
3. **[ISA-6]** One loop at a time: no JUMP inside another loop's body. Loops in
   sequence are fine. **[ANEMOS]** (one loop counter).
4. **[ISA-7]** A JUMP's target, and the instruction after a JUMP, must not be a
   JUMP (each fetch resolves at most one). **[bankside]**
5. **[ISA-8]** PC wraps from 31 to 0. Programs should end with EXIT.
   **[bankside]**
6. **[IF-6]** The host writes register files only while the unit is idle.
   **[bankside]**

## Assembler syntax

```
NOP 2
JUMP -3, 7
EXIT
MOV GRF_A[0], EVEN_BANK
MOV(RELU) EVEN_BANK, GRF_A[0]
FILL GRF_B[1], ODD_BANK
ADD GRF_A[2], EVEN_BANK, SRF_A[0]
MUL GRF_B[3], GRF_A[1], SRF_M[4]
MAD GRF_A[0], ODD_BANK, SRF_M[2], SRF_A[2]
MAC GRF_B[0], EVEN_BANK, SRF_M[0]
```

Operands are in the order DST, SRC0, SRC1 (, SRC2). Comments start with `;`.

## Examples

### GEMV partial sum (no loop)

Adapted from the ANEMOS `mvmT16` kernel. GRF_B[0] holds 16 partial sums, one
per output row. Each bank column holds 16 weights for one input element; that
input element is in an SRF_M entry. The host loads x₀…x₇ into SRF_M[0..7],
runs the kernel, then repeats with the next 8 inputs.

```
MOV GRF_B[0], ODD_BANK              ; load the partial sums
MAC GRF_B[0], EVEN_BANK, SRF_M[0]   ; y += W[:,0] * x0
MAC GRF_B[0], ODD_BANK,  SRF_M[1]
MAC GRF_B[0], EVEN_BANK, SRF_M[2]
MAC GRF_B[0], ODD_BANK,  SRF_M[3]
MAC GRF_B[0], EVEN_BANK, SRF_M[4]
MAC GRF_B[0], ODD_BANK,  SRF_M[5]
MAC GRF_B[0], EVEN_BANK, SRF_M[6]
MAC GRF_B[0], ODD_BANK,  SRF_M[7]
NOP 2                               ; [HAZ-3]: the store reads GRF_B[0]
MOV ODD_BANK, GRF_B[0]              ; store the partial sums
EXIT
```

The MACs run back to back thanks to the accumulator bypass. The store reads
GRF_B[0] as a source, so it needs the 2-slot gap after the last MAC. ANEMOS
doesn't need one, because its MULT and ADD stages are one cycle each.

### ReLU in place over n columns (loop)

```
MOV(RELU) GRF_A[0], EVEN_BANK   ; PC 0  load column k with ReLU
NOP 2                           ; PC 1  [HAZ-3] gap before reading GRF_A[0]
MOV EVEN_BANK, GRF_A[0]         ; PC 2  store column k
JUMP -3, n-1                    ; PC 3  back to PC 0; the body runs n times
EXIT                            ; PC 4
```

Each column takes 4 slots (the JUMP takes none). The host's commands must
match: a read of column *k*, two slots of any command, then a write of column
*k*. Interleaving two columns (GRF_A[0] and GRF_A[1]) fills the NOP slots with
useful work.
