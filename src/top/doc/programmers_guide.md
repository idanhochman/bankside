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
- **DST#, SRC0#, SRC1#** are 3-bit register indices, one per operand field.
- **[TOP-ISA-1]** Unused bits (–) are written as 0 by the assembler and ignored by
  the hardware. **[bankside]**
- **[TOP-ISA-9]** An index field whose operand is a bank (EVEN_BANK, ODD_BANK)
  selects nothing and is ignored: a bank operand's address comes from the
  trigger ([TOP-ARCH-6]). The one exception is SRC1# of MAD, which also
  indexes the SRF_A addend and so is used even when src1 is a bank
  ([TOP-ISA-20]). **[bankside]**
- **[TOP-ISA-10]** Only MAD uses the SRC2 field. ADD, MUL and MAC ignore it,
  whatever it holds, including a reserved code: their legality
  ([TOP-ISA-2]) doesn't depend on SRC2. **[ANEMOS]** (its decoder reads SRC2
  only for MAD), **[bankside]** (reserved codes there are not illegal).

ANEMOS uses the same opcode, DST, SRC0, SRC1, SRC2 and AAM positions but a
different layout for the rest: its RELU flag is bit 15 (bankside: bit 12) and
its register indices are 5 bits wide, at 14–10, 9–5 and 4–0. bankside follows
the paper's Table III. ANEMOS kernels are translated before they run on
bankside ([verification](../dv/README.md)).

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

- **[TOP-ISA-2]** An instruction is illegal if it uses a reserved opcode, a
  reserved operand code, an operand combination not listed for its opcode (the
  `legal` lists in [`bankside_isa.yaml`](bankside_isa.yaml), written out in the
  instruction reference below), or (in v1) A = 1. An illegal instruction
  executes as a one-slot NOP and sets the sticky `err_illegal` flag
  ([interfaces.md](interfaces.md)). **[bankside]**

A field the instruction ignores ([TOP-ISA-1], [TOP-ISA-9], [TOP-ISA-10], R of
FILL) is not "used", so its value never makes the instruction illegal.

## Instruction reference

Notation: `GRF_A[i]` is entry *i* of GRF_A, with *i* taken from the operand's
index field; arithmetic is per lane, per
[FP16 arithmetic](theory_of_operation.md#fp16-arithmetic).

- **[TOP-ISA-11]** An SRF entry used as a source of a vector operation (ADD,
  MUL, MAD, MAC, or MOV into a GRF) is broadcast to all 16 lanes.
  **[paper]** (scalar operands), **[ANEMOS]** (MOV SRF → GRF).

### Program counter

- **[TOP-ISA-8]** After an instruction that doesn't set the PC, PC ← PC + 1,
  wrapping from 31 to 0. JUMP and EXIT set the PC themselves ([TOP-ISA-3],
  [TOP-ISA-5]); a multi-cycle NOP holds it until its last slot
  ([TOP-ISA-12]); an illegal instruction advances it like any one-slot
  instruction ([TOP-ISA-2]). **[ANEMOS]** (its PC unit wraps from
  `CRF_ENTRIES − 1` = 31 to 0). Draft 0.1 tagged the wrap **[bankside]**; it
  is the same behaviour.
- Programs should end with EXIT rather than rely on the wrap.

### NOP

`NOP n` does nothing for *n* slots.

- **[TOP-ISA-12]** A NOP occupies IMM0 slots, one per triggering command
  ([TOP-PIPE-3]); IMM0 = 0 occupies one slot, like IMM0 = 1. **[paper]**
  (multi-cycle NOP), **[ANEMOS]** (IMM0 = slot count), **[bankside]** (0 → 1).
  ANEMOS loads its 8-bit NOP counter with IMM0 − 1, so in ANEMOS `NOP 0`
  wraps to 255 and lasts 256 slots.

### JUMP

`JUMP -off, count` is a backward branch for loops. IMM0 = *off*, the backward
offset; IMM1 = *count*, the number of jumps taken. **[paper]** (syntax, zero
cycles), **[ANEMOS]** (which immediate is which, counting).

- **[TOP-ISA-3]** The unit holds one **loop state**: a flag `loop_active` and
  an 11-bit counter `loop_cnt`. Reset ([TOP-IF-4]) and EXIT ([TOP-ISA-5])
  clear both; `loop_cnt` matters only while `loop_active` = 1. When a JUMP is
  fetched, it acts on the loop state as follows:

  | `loop_active` | `loop_cnt` | IMM1 | Meaning | PC ← | `loop_active` ← | `loop_cnt` ← |
  |---|---|---|---|---|---|---|
  | 0 | – | ≥ 1 | first time reached: start the loop | PC − IMM0 | 1 | IMM1 − 1 |
  | 0 | – | 0 | never taken ([TOP-ISA-13]) | PC + 1 | 0 | – |
  | 1 | ≠ 0 | – | jump again | PC − IMM0 | 1 | `loop_cnt` − 1 |
  | 1 | 0 | – | last time: the loop ends | PC + 1 | 0 | – |

  **[ANEMOS]** (its decoder keeps the same two registers, `jmp_act_reg` and
  `jmp_cnt_reg`, with the same transitions), **[bankside]** (the IMM1 = 0
  row). Draft 0.1 said "the first time the JUMP is reached"; that is
  `loop_active` = 0.
- So the jump is taken IMM1 times, and **the loop body runs IMM1 + 1 times**.
  `JUMP -1, 7` runs the instruction above it 8 times.
- **[TOP-ISA-13]** IMM1 = 0 means the JUMP is never taken: the body runs once,
  and the loop state stays clear. **[bankside]** ANEMOS has no such case: it
  loads its 32-bit counter with IMM1 − 1, which wraps to 2³² − 1, and jumps.
- **[TOP-ISA-4]** A JUMP occupies no slot: it is resolved in S1 and the next
  instruction (the target, or PC + 1) is fetched in the same cycle.
  **[paper]**
- **[TOP-ISA-14]** **Programming rule.** IMM0 must be between 1 and the JUMP's
  own PC, so that the target PC − IMM0 is between 0 and PC − 1.
  **[bankside]**

**Worked case.** The loop state through `JUMP -1, 2` (body runs 3 times),
one row per slot. Generated by [examples/loop_trace.py](examples/loop_trace.py).

```
PC 0  MOV GRF_A[0], EVEN_BANK   ; body
PC 1  JUMP -1, 2
PC 2  EXIT
```

| Slot | JUMP fetched (state before → after) | Instruction issued | PC after |
|---|---|---|---|
| 1 | – | PC 0 MOV | 1 |
| 2 | PC 1: active 0 → 1, cnt – → 1, jump to 0 | PC 0 MOV | 1 |
| 3 | PC 1: active 1, cnt 1 → 0, jump to 0 | PC 0 MOV | 1 |
| 4 | PC 1: active 1 → 0, cnt 0, fall through | PC 2 EXIT | 0 |

Two jumps (IMM1 = 2), three MOVs (IMM1 + 1). With `JUMP -1, 0` slot 2 falls
through to EXIT and the MOV runs once ([TOP-ISA-13]); ANEMOS would jump and
keep looping.

### EXIT

`EXIT` ends the microkernel. **[TOP-ISA-5]** PC ← 0 and the loop state
([TOP-ISA-3]) is cleared; it occupies one slot. Instructions already in the
pipeline complete. The next triggering command starts again at CRF[0].
**[ANEMOS]** (PC ← 0), **[bankside]** (clearing the loop state: ANEMOS's
EXIT resets only the PC).

### MOV

`MOV dst, src` or `MOV(RELU) dst, src` copies a register or bank column.
**[paper]** (GRF ← GRF/bank, ReLU), **[ANEMOS]** (SRF and bank destinations,
the even/odd pairing, GRF → SRF uses lane 0).

- **[TOP-ISA-15]** MOV performs, for each legal (src, dst) pair:

  | src → dst | Operation |
  |---|---|
  | GRF → GRF | vector copy |
  | SRF → GRF | scalar broadcast to 16 lanes ([TOP-ISA-11]) |
  | GRF → SRF | lane 0 of the GRF entry |
  | SRF → SRF | scalar copy |
  | EVEN_BANK → GRF_A, ODD_BANK → GRF_B | bank load |
  | GRF_A → EVEN_BANK, GRF_B → ODD_BANK | bank store ([TOP-ARCH-8]) |

  "GRF" is GRF_A or GRF_B and "SRF" is SRF_M or SRF_A, in any combination.
  Any other pair is illegal ([TOP-ISA-2]), including bank ↔ SRF, bank → bank
  and crossed pairs such as EVEN_BANK → GRF_B. With R = 1, ReLU
  ([TOP-FP-8]) is applied to the value on its way.

### FILL

- **[TOP-ISA-16]** `FILL dst, src` moves data between a bank and the GRF
  exactly like MOV with R = 0: only the four bank load/store pairs are legal,
  and R is ignored. **[paper]** (Hot Chips 33: FILL exists, bank ↔ GRF),
  **[bankside]** (defined as this restricted MOV, since ANEMOS leaves FILL
  unimplemented).

### ADD

- **[TOP-ISA-17]** `ADD dst, src0, src1`: dst ← src0 + src1. **[paper]**
  - src0, src1 ∈ {GRF_A, GRF_B, EVEN_BANK, ODD_BANK, SRF_A}; dst ∈ {GRF_A, GRF_B}.
  - At most one bank operand, and SRF_A at most once.

### MUL

- **[TOP-ISA-18]** `MUL dst, src0, src1`: dst ← src0 × src1. **[paper]**
  - src0 ∈ {GRF_A, GRF_B, EVEN_BANK, ODD_BANK}; src1 ∈ {GRF_A, GRF_B,
    EVEN_BANK, ODD_BANK, SRF_M}; dst ∈ {GRF_A, GRF_B}.
  - At most one bank operand.

### MAD

- **[TOP-ISA-19]** `MAD dst, src0, src1, SRF_A[j]`:
  dst ← round(round(src0 × src1) + SRF_A[j]) ([TOP-FP-3]). **[paper]**
  - Operands as for MUL. SRC2 is always SRF_A: the SRC2 field must hold the
    SRF_A code (3); anything else is illegal ([TOP-ISA-2]).
- **[TOP-ISA-20]** The addend's index *j* is always the SRC1# field, whatever
  src1 is. **[ANEMOS]** (its decoder indexes the SRC2 operand with `SRC1_N`),
  **[bankside]** (the assembler rule below).
  - If src1 is a GRF or SRF_M entry, SRC1# is also src1's index, so *j* must
    equal it: the assembler rejects `MAD d, a, SRF_M[2], SRF_A[3]`.
  - If src1 is a bank, SRC1# selects nothing for src1 ([TOP-ISA-9]) and holds
    *j* alone: `MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]` has SRC1# = 5.

### MAC

- **[TOP-ISA-21]** `MAC GRF_B[i], src0, src1`:
  GRF_B[i] ← round(GRF_B[i] + round(src0 × src1)) ([TOP-FP-3]), with *i* =
  DST#. **[paper]** (Table II; GRF_B is the only destination).
  - src0, src1 as for MUL; dst is GRF_B only. The SRC2 field is ignored
    ([TOP-ISA-10]).
- The accumulator is read late, in S4, with a bypass ([TOP-HAZ-2]). A MAC may
  follow the previous write of its GRF_B entry immediately ([TOP-HAZ-4]).
- The paper's Fig. 7 and the Hot Chips slides show `MAC GRF_A, …`, which
  contradicts Table II and the text. bankside treats the figure as an erratum.

### Legal combinations compared with the paper

The bankside counts are computed from the yaml `legal` lists by
[examples/check_isa.py](examples/check_isa.py).

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
was meant. An assertion flags each of them in simulation and the reference
model reports it as an error. The assembler also rejects the program when the
rule can be seen in the program text ([TOP-HAZ-3], [TOP-ISA-6], [TOP-ISA-7],
[TOP-ISA-14]); [TOP-HAZ-6] depends on the addresses the host sends and
[TOP-IF-6] on the host itself, so the assembler can't check those.

What the hardware does when a rule is broken is specified for [TOP-HAZ-3]
([TOP-HAZ-5]) and [TOP-HAZ-6]. For [TOP-ISA-6], [TOP-ISA-7], [TOP-ISA-14] and
[TOP-IF-6] it is not specified yet; tests must not depend on it.

1. [TOP-HAZ-3]: at least **2 slots between** a write to a GRF/SRF entry and an
   instruction that reads it as a source. The MAC accumulator is exempt
   ([TOP-HAZ-4]).
2. [TOP-HAZ-6]: at least **3 slots between** a bank store and a read of the
   same bank column (v1 bank model).
3. **[TOP-ISA-6]** One loop at a time: no JUMP inside another loop's body.
   Loops in sequence are fine. **[ANEMOS]** (one loop counter; [TOP-ISA-3]
   keeps one loop state).
4. **[TOP-ISA-7]** A JUMP's target, and the instruction after a JUMP, must not
   be a JUMP (each fetch resolves at most one). **[bankside]**
5. [TOP-ISA-14]: a JUMP's IMM0 is between 1 and the JUMP's own PC.
6. [TOP-IF-6]: the host writes register files only while `busy` = 0 and
   `trig_valid` = 0.

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
A bank operand has no index. The lines above show the syntax only; they are
not one program (the JUMP would break [TOP-ISA-14] at PC 1).

The assembler writes 0 into every field the instruction ignores: unused bits
([TOP-ISA-1]), the index field of a bank operand other than MAD's SRC1#
([TOP-ISA-9]), SRC2 of ADD, MUL and MAC ([TOP-ISA-10]) and R of FILL.
**[bankside]** Their encodings are checked by
[examples/check_isa.py](examples/check_isa.py).

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
NOP 2                               ; [TOP-HAZ-3]: the store reads GRF_B[0]
MOV ODD_BANK, GRF_B[0]              ; store the partial sums
EXIT
```

The MACs run back to back thanks to the accumulator bypass. The store reads
GRF_B[0] as a source, so it needs the 2-slot gap after the last MAC. ANEMOS
doesn't need one, because its MULT and ADD stages are one cycle each.

### ReLU in place over n columns (loop)

```
MOV(RELU) GRF_A[0], EVEN_BANK   ; PC 0  load column k with ReLU
NOP 2                           ; PC 1  [TOP-HAZ-3] gap before reading GRF_A[0]
MOV EVEN_BANK, GRF_A[0]         ; PC 2  store column k
JUMP -3, n-1                    ; PC 3  back to PC 0; the body runs n times
EXIT                            ; PC 4
```

Each column takes 4 slots (the JUMP takes none). The host's commands must
match: a read of column *k*, two slots of any command, then a write of column
*k*. Interleaving two columns (GRF_A[0] and GRF_A[1]) fills the NOP slots with
useful work.
