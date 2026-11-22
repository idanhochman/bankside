# pcu_decode: specification

Owner: architect. Readers: everyone. The designer and DV each build from this
alone, so anything they would have to guess belongs here.

Every rule is tagged `[paper]`, `[ANEMOS]` or `[bankside]`, and every rule a
test can check has an ID: `[DEC-1]`, `[DEC-2]`, ...

## Overview

`pcu_decode` is the instruction decoder. It is **combinational**: one 32-bit
instruction word in; out come an **illegal** flag, the **bank read** the word
makes, and the **decoded instruction** (`dec_instr_t`), which `pcu_ctrl`
loads into the S1/S2 register for `pcu_datapath`. Everything it does is
read from [bankside_isa.yaml](../../top/doc/bankside_isa.yaml), the source of
truth for the encoding.

Its parent is `pcu_ctrl` (instance `dec`, [TOP-HIER-1]). How it connects
there, which word it is given and what is done with its outputs, is defined
by the parent, in [CTRL-15], [CTRL-8], [CTRL-11] and [CTRL-12] of
[`pcu_ctrl`'s doc](../../pcu_ctrl/doc/README.md#pcu_decode), not here. What
`pcu_datapath` takes from the decoded instruction is [DP-6] of
[`pcu_datapath`'s doc](../../pcu_datapath/doc/README.md#the-issue-bundle). The rules
this module carries out are those of the top spec:

| Top rule | What it asks of `pcu_decode` | Here |
|---|---|---|
| [TOP-ISA-1] | unused bits are ignored | [DEC-6], [DEC-13] |
| [TOP-ISA-2] | the illegal words, but for the JUMP range check | [DEC-5], [DEC-7] |
| [TOP-ISA-9], [TOP-ISA-20] | a bank operand's index is ignored, except MAD's SRC1# | [DEC-6], [DEC-13] |
| [TOP-ISA-10] | SRC2 of ADD, MUL and MAC ignored, even a reserved code | [DEC-6], [DEC-8] |
| [TOP-ISA-15] to [TOP-ISA-23] | the legal combinations of each instruction, and what each field means | [DEC-7], [DEC-13] |
| [TOP-ISA-24] | an illegal word has no effect | [DEC-9] |
| [TOP-ISA-25] | NOP's IMM1 and EXIT's IMM0, IMM1 ignored, never illegal | [DEC-6] |
| [TOP-ISA-26] | the JUMP range check needs the PC: it is `pcu_ctrl`'s ([CTRL-7]) | [DEC-6] |
| [TOP-ARCH-7] | at most one bank source | [DEC-7], [DEC-10] |
| [TOP-HIER-9] | the decoded type in the shared package | [DEC-11], [DEC-15] |

[TOP-ARCH-3]: ../../top/doc/theory_of_operation.md#architecture
[TOP-ARCH-6]: ../../top/doc/theory_of_operation.md#bank-access
[TOP-ARCH-7]: ../../top/doc/theory_of_operation.md#bank-access
[TOP-ISA-1]: ../../top/doc/programmers_guide.md#instruction-formats
[TOP-ISA-2]: ../../top/doc/programmers_guide.md#illegal-instructions
[TOP-ISA-9]: ../../top/doc/programmers_guide.md#instruction-formats
[TOP-ISA-10]: ../../top/doc/programmers_guide.md#instruction-formats
[TOP-ISA-12]: ../../top/doc/programmers_guide.md#nop
[TOP-ISA-15]: ../../top/doc/programmers_guide.md#mov
[TOP-ISA-16]: ../../top/doc/programmers_guide.md#fill
[TOP-ISA-17]: ../../top/doc/programmers_guide.md#add
[TOP-ISA-18]: ../../top/doc/programmers_guide.md#mul
[TOP-ISA-19]: ../../top/doc/programmers_guide.md#mad
[TOP-ISA-20]: ../../top/doc/programmers_guide.md#mad
[TOP-ISA-21]: ../../top/doc/programmers_guide.md#mac
[TOP-ISA-22]: ../../top/doc/programmers_guide.md#legal-combinations-compared-with-the-paper
[TOP-ISA-23]: ../../top/doc/programmers_guide.md#mad
[TOP-ISA-24]: ../../top/doc/programmers_guide.md#illegal-instructions
[TOP-ISA-25]: ../../top/doc/programmers_guide.md#illegal-instructions
[TOP-ISA-26]: ../../top/doc/programmers_guide.md#when-a-jump-rule-is-broken
[TOP-HIER-1]: ../../top/doc/hierarchy.md#modules
[TOP-HIER-2]: ../../top/doc/hierarchy.md#who-owns-which-stage
[TOP-HIER-9]: ../../top/doc/hierarchy.md#shared-package-and-the-wrapper
[CTRL-7]: ../../pcu_ctrl/doc/README.md#fetch-and-the-zero-slot-jump
[CTRL-8]: ../../pcu_ctrl/doc/README.md#fetch-and-the-zero-slot-jump
[CTRL-9]: ../../pcu_ctrl/doc/README.md#what-a-slot-does
[CTRL-11]: ../../pcu_ctrl/doc/README.md#bank-read-request
[CTRL-12]: ../../pcu_ctrl/doc/README.md#the-issue-bundle
[CTRL-15]: ../../pcu_ctrl/doc/README.md#pcu_decode
[CTRL-16]: ../../pcu_ctrl/doc/README.md#timing
[DP-6]: ../../pcu_datapath/doc/README.md#the-issue-bundle
[DP-10]: ../../pcu_datapath/doc/README.md#s3-and-s4-the-lanes
[DP-11]: ../../pcu_datapath/doc/README.md#s3-and-s4-the-lanes
[VER-5]: ../../top/dv/README.md

**Sources.** The papers give the encoding (ISCA 2021, Table III, checked by
the top spec's [paper_table3.py](../../top/doc/examples/paper_table3.py)) and
the legal combinations as counts (Table II), but not a decoder, so the rules
here are **[bankside]** unless marked, each carrying out the top rule it
cites. ANEMOS (github.com/gem5-X/cnm_framework at `f2d4018`,
`src/instr_decoder.cpp`; read, not run) has a decoder in the same place:
`comb_method` cuts the word into its fields, sets every control signal to
its inactive default, then switches on the opcode and drives only the
signals of the case it finds, so an opcode with no case drives nothing. It
reads SRC2 only in its `OP_MAD` case, and its `OP_FILL` case is empty.
bankside differs from it on purpose in three ways: ANEMOS has no legality
check, so an illegal operand combination may partly execute (the
[programmer's guide](../../top/doc/programmers_guide.md#illegal-instructions)
traces one), where bankside flags the word and makes it do nothing
([DEC-9]); ANEMOS's decoder also holds the PC-side state (the loop state and
the NOP counter), which bankside keeps in `pcu_ctrl` ([CTRL-15]); and ANEMOS
drives the select lines of every unit, per stage, where bankside's decoder
gives one decoded instruction that travels with its entry ([TOP-HIER-2]).

## Parameters

- **[DEC-1]** `pcu_decode` has **no parameters**. Every width is fixed by
  the ISA: a 32-bit word in, the 22-bit `dec_instr_t` out. **[bankside]**

## Ports

- **[DEC-2]** The ports. No other ports exist: in particular no clock and no
  reset. **[bankside]**

  | Port | Dir | Width | Type | Timing | Description |
  |---|---|---|---|---|---|
  | `instr` | in | 32 | `logic [31:0]` | – | The instruction word |
  | `illegal` | out | 1 | `logic` | combinational from `instr` ([DEC-16]) | The word is illegal ([DEC-5]); never 1 for a JUMP ([DEC-6]) |
  | `bank_rd` | out | 1 | `logic` | combinational | The word is legal and reads a bank ([DEC-10]) |
  | `bank_sel` | out | 1 | `logic` | combinational | The bank it reads: 0 = EVEN_BANK, 1 = ODD_BANK; 0 while `bank_rd` = 0 |
  | `dec_instr` | out | 22 | `dec_instr_t` | combinational | The decoded instruction ([DEC-11] to [DEC-14]) |

  `bank_sel` has the encoding of `pcu_ctrl`'s `bank_rd_sel` port, so
  `pcu_ctrl` can pass it straight on ([CTRL-11]). Every output has a
  defined value for every one of the 2^32 words: there is no don't-care
  output bit.

## Behaviour

In short, for one word:

```
opcode reserved                      -> illegal = 1, bank_rd = 0, bank_sel = 0, dec_instr = DEC_NOP
NOP, JUMP, EXIT (any other bits)     -> illegal = 0, bank_rd = 0, bank_sel = 0, dec_instr = DEC_NOP
MOV ... MAC, not a legal combination,
  or A = 1 (ALU format)              -> illegal = 1, bank_rd = 0, bank_sel = 0, dec_instr = DEC_NOP
MOV ... MAC, legal                   -> illegal = 0, bank_rd/bank_sel from its bank source,
                                        dec_instr = its fields, the ones it ignores 0
```

The block is a summary; where it and a rule seem to differ, the rule is
right.

### Reading the word

- **[DEC-3]** **Combinational.** Every output is a function of `instr` alone:
  no state, no clock, no latch. The same word gives the same outputs in every
  cycle. **[bankside]**

- **[DEC-4]** **Fields.** The opcode is bits 31–28 in every format. The
  opcode selects the instruction and its format (the yaml's `instructions`:
  `format`), and every other field is read at the bit range the yaml's
  `formats` gives for that format; nothing else is read. Field names below
  are the yaml's (`dst`, `src0`, `src1`, `src2`, `aam`, `relu`, `dst_idx`,
  `src0_idx`, `src1_idx`, `imm0`, `imm1`); the guide writes them DST, SRC0,
  SRC1, SRC2, A, R, DST#, SRC0#, SRC1#, IMM0, IMM1. **[paper]** (the layout,
  Table III), **[ANEMOS]** (the opcode values).

### The illegal flag

- **[DEC-5]** **When `illegal` = 1.** `illegal` = 1 if and only if one of
  these holds ([TOP-ISA-2] for the word alone):
  1. the opcode is **reserved**: 3, 6, 7 or 12 to 15, an opcode no
     instruction of the yaml has;
  2. the instruction is ADD, MUL, MAD or MAC and **A = 1** (the yaml's
     `v1_illegal: [aam_set]`);
  3. the instruction is MOV, FILL, ADD, MUL, MAD or MAC and its operand
     codes are **not a legal combination** ([DEC-7]). A reserved operand
     code (6 or 7) in a field the instruction checks is in no list, so it is
     a case of this one.

  **[bankside]** ([TOP-ISA-2]). ANEMOS has no flag (see Sources).

- **[DEC-6]** **Never illegal.** These never set `illegal`, whatever they
  hold: **[bankside]**
  - **NOP, JUMP and EXIT**, whatever their other 28 bits hold. Their IMM
    fields are not checked here ([TOP-ISA-25]). A JUMP's IMM0 range check
    ([TOP-ISA-26]) depends on the PC the JUMP is fetched at, which the
    decoder doesn't have, so `pcu_ctrl` makes it ([CTRL-7]) and calls the
    slot ILLJ, not ILL ([CTRL-8]). To `pcu_decode` a JUMP with IMM0 = 0 is
    a legal word ([case A](#case-a-worked-words), row 4).
  - **The bits a format doesn't name** ([TOP-ISA-1]): bits 27–19 of the
    control format; 21–13, 11, 7 and 3–0 of the data format (so a MOV or
    FILL has no SRC1, SRC2, A or SRC1#: a reserved code at bits 21–19 is
    not checked, row 15); 14–11, 7 and 3 of the ALU format (bit 12, R in
    the data format, is unused here).
  - **The index fields**: DST#, SRC0#, SRC1# select one of 8 entries or are
    ignored ([TOP-ISA-9]), so no value of them is illegal.
  - **SRC2 of ADD, MUL and MAC**, a reserved code included ([TOP-ISA-10],
    [DEC-8]).
  - **R of FILL** ([TOP-ISA-16]).

- **[DEC-7]** **The legal combinations** are exactly the yaml's `legal`
  lists with their `constraints`: an instruction's word is a legal
  combination if one entry of its `legal` list has every field it names
  holding one of the operands listed for that field, and the instruction's
  constraints hold (`one_bank_operand`: at most one of SRC0, SRC1 is a bank,
  [TOP-ARCH-7]; `one_read_per_srf`, ADD only: SRC0 and SRC1 are not both
  SRF_A). A field no entry names is not checked. So the fields checked are:

  | Instruction | Fields checked | Legal combinations | Top rule |
  |---|---|---|---|
  | MOV | DST, SRC0 | 20 | [TOP-ISA-15] |
  | FILL | DST, SRC0 | 4 | [TOP-ISA-16] |
  | ADD | DST, SRC0, SRC1 | 40 | [TOP-ISA-17] |
  | MUL | DST, SRC0, SRC1 | 32 | [TOP-ISA-18] |
  | MAD | DST, SRC0, SRC1, SRC2 | 32 | [TOP-ISA-19], [TOP-ISA-22], [TOP-ISA-23] |
  | MAC | DST, SRC0, SRC1 | 16 | [TOP-ISA-21], [TOP-ISA-22] |

  In particular: MAC and MAD take exactly MUL's 16 (SRC0, SRC1) pairs, the
  two same-file pairs included ([TOP-ISA-22]); MAD is legal only with SRC2
  = SRF_A (3), and any other value of SRC2, reserved ones included, makes it
  illegal ([TOP-ISA-23]); MAC is legal only with DST = GRF_B
  ([TOP-ISA-21]). The counts are those of the
  [guide's table](../../top/doc/programmers_guide.md#legal-combinations-compared-with-the-paper)
  and of [VER-5]'s bins, and the script computes them from the yaml
  ([case B](#case-b-every-word-class)). **[paper]** (Table II, as the top
  rules read it), **[ANEMOS]** (MAC and MAD's pairs), **[bankside]** (the
  rest; each top rule says which).

- **[DEC-8]** **MAC's SRC2 is ignored.** A MAC's outputs don't depend on its
  SRC2 field: all 8 values give the same `illegal`, `bank_rd`, `bank_sel`
  and `dec_instr`. The assembler writes GRF_B (1) there ([TOP-ISA-1]),
  ANEMOS's writes GRF_A (0), and both words run the same MAC
  ([case A](#case-a-worked-words), rows 24 to 26). This is option 3 of
  decision #19, applied by #29. **[ANEMOS]** (its decoder reads SRC2 only
  for MAD), **[bankside]** (reserved codes there legal too). The paper's
  Section III-C describes the field as GRF_B; the top spec follows the paper
  for the encoding and ANEMOS for the hardware ([TOP-ISA-10]).

### An illegal word has no effect

- **[DEC-9]** For every word with `illegal` = 1: `bank_rd` = 0, `bank_sel` =
  0 and `dec_instr` = `DEC_NOP` ([DEC-14]). So the decoder's own outputs
  request no bank access and, issued, write nothing and read nothing in S2
  to S5 ([DP-6]), which is [TOP-ISA-24] at this module's boundary. `pcu_ctrl`
  does the same on its side: a slot of kind ILL requests no bank read
  ([CTRL-11]) and issues `DEC_NOP` ([CTRL-12]); `illegal` is what makes the
  slot ILL ([CTRL-8]) and sets `err_illegal`. **[bankside]** ANEMOS differs
  (see Sources). Why the decoder repeats what `pcu_ctrl` already does:
  [Choices weighed](#choices-weighed).

### The bank read

- **[DEC-10]** `bank_rd` = 1 if and only if the word is a legal MOV, FILL,
  ADD, MUL, MAD or MAC (`illegal` = 0) and its **SRC0**, or for the ALU
  format its **SRC1**, is EVEN_BANK or ODD_BANK. Then `bank_sel` = 1 if that
  operand is ODD_BANK and 0 if it is EVEN_BANK (bit 0 of the operand code).
  In every other case `bank_rd` = 0 and `bank_sel` = 0. **[bankside]**
  - A legal word has at most one bank source ([DEC-7], [TOP-ARCH-7]), so
    "that operand" is unique.
  - A bank **destination** (a MOV or FILL store) is not a read: the store is
    `pcu_datapath`'s, in S5. MAD's SRC2 is never a bank in a legal word.
  - NOP, JUMP and EXIT read no bank.

  `pcu_ctrl` drives `bank_rd_en` from `bank_rd` in a slot of kind OP and
  `bank_rd_sel` from `bank_sel` ([CTRL-11]). ANEMOS has no bank read request
  in its decoder: its bank reads are DRAM commands, and its decoder drives
  only the bank output enables of a store (`even_out_en`, `odd_out_en`).

### The decoded instruction

- **[DEC-11]** **`dec_instr_t`** is a packed struct of 22 bits, these fields
  from the most significant down. **[bankside]**

  | Field | Type | Bits | Holds |
  |---|---|---|---|
  | `op` | `dec_op_e` | 21–19 | The operation ([DEC-12]); `DEC_OP_NONE` for "do nothing" |
  | `dst` | `opnd_e` | 18–16 | The DST operand code |
  | `src0` | `opnd_e` | 15–13 | The SRC0 operand code |
  | `src1` | `opnd_e` | 12–10 | The SRC1 operand code (ALU format) |
  | `dst_idx` | `logic [2:0]` | 9–7 | DST# |
  | `src0_idx` | `logic [2:0]` | 6–4 | SRC0# |
  | `src1_idx` | `logic [2:0]` | 3–1 | SRC1# (for MAD also the SRF_A index of the addend, [TOP-ISA-20]) |
  | `relu` | `logic` | 0 | R (MOV) |

  ```systemverilog
  typedef struct packed {
    dec_op_e    op;
    opnd_e      dst;
    opnd_e      src0;
    opnd_e      src1;
    logic [2:0] dst_idx;
    logic [2:0] src0_idx;
    logic [2:0] src1_idx;
    logic       relu;
  } dec_instr_t;   // $bits = 22
  ```

  These are the fields [DP-6] lists, and no more: `pcu_datapath` never reads
  SRC2 (MAD's addend is always SRF_A, [TOP-ISA-23]), so the type has no
  `src2`; A is always 0 in a legal word; IMM0 and IMM1 matter only to NOP
  and JUMP, which `pcu_ctrl` reads from the word itself ([CTRL-15]) and
  never issues ([CTRL-12]). What the type leaves out:
  [What the decoder doesn't output](#what-the-decoder-doesnt-output).

  ![dec_instr_t, 22 bits: op 21-19, dst 18-16, src0 15-13, src1 12-10, dst_idx 9-7, src0_idx 6-4, src1_idx 3-1, relu 0](img/dec_instr_t.svg)

  *Figure 1: the layout of `dec_instr_t` ([DEC-11]), bit 0 on the right.
  The script checks the figure's source against this table. Source:
  [dec_instr_t.reg.json](img/dec_instr_t.reg.json).*

- **[DEC-12]** **The two enumerations**, both `logic [2:0]`. `opnd_e` has
  the yaml's operand codes; codes 6 and 7 have no name and never appear in
  `dec_instr` ([DEC-13]). `dec_op_e` value 7 has no name and is never
  output. **[bankside]**, **[ANEMOS]** (the operand code values).

  | `opnd_e` | Value | | `dec_op_e` | Value | For |
  |---|---|---|---|---|---|
  | `OPND_GRF_A` | 0 | | `DEC_OP_NONE` | 0 | NOP, JUMP, EXIT and every illegal word |
  | `OPND_GRF_B` | 1 | | `DEC_OP_MOV` | 1 | MOV (opcode 4) |
  | `OPND_SRF_M` | 2 | | `DEC_OP_FILL` | 2 | FILL (opcode 5) |
  | `OPND_SRF_A` | 3 | | `DEC_OP_ADD` | 3 | ADD (opcode 8) |
  | `OPND_EVEN_BANK` | 4 | | `DEC_OP_MUL` | 4 | MUL (opcode 9) |
  | `OPND_ODD_BANK` | 5 | | `DEC_OP_MAD` | 5 | MAD (opcode 10) |
  | | | | `DEC_OP_MAC` | 6 | MAC (opcode 11) |


- **[DEC-13]** **`dec_instr` for a legal MOV, FILL, ADD, MUL, MAD or MAC.**
  Each field takes the word's field of the same name, except where the
  instruction ignores it: **every field the instruction ignores is 0**. So
  two words that differ only in bits the instruction ignores give the same
  `dec_instr` ([case C](#case-c-two-words-one-instruction)). **[bankside]**
  (the zeros), carrying out [TOP-ISA-1], [TOP-ISA-9], [TOP-ISA-10] and
  [TOP-ISA-20].

  | Field | MOV | FILL | ADD, MUL | MAD | MAC |
  |---|---|---|---|---|---|
  | `op` | `DEC_OP_MOV` | `DEC_OP_FILL` | `DEC_OP_ADD`, `DEC_OP_MUL` | `DEC_OP_MAD` | `DEC_OP_MAC` |
  | `dst` | DST | DST | DST | DST | DST (always GRF_B) |
  | `src0` | SRC0 | SRC0 | SRC0 | SRC0 | SRC0 |
  | `src1` | 0 | 0 | SRC1 | SRC1 | SRC1 |
  | `dst_idx` | DST#, or 0 if DST is a bank | DST#, or 0 if DST is a bank | DST# | DST# | DST# |
  | `src0_idx` | SRC0#, or 0 if SRC0 is a bank | as MOV | as MOV | as MOV | as MOV |
  | `src1_idx` | 0 | 0 | SRC1#, or 0 if SRC1 is a bank | **SRC1#, also if SRC1 is a bank** ([TOP-ISA-20]) | SRC1#, or 0 if SRC1 is a bank |
  | `relu` | R | 0 ([TOP-ISA-16]) | 0 | 0 | 0 |

  The legal combinations put no reserved code in a field that is passed on,
  so `dst`, `src0` and `src1` always hold a named `opnd_e` value, and `op`
  is never `DEC_OP_NONE` for a legal MOV to MAC.

- **[DEC-14]** **`DEC_NOP`** is the constant `dec_instr_t` with every field 0
  (`'0`): `op` = `DEC_OP_NONE`. It is: **[bankside]**
  - the `dec_instr` of the word 0x00000000 (`NOP 0`), as [CTRL-12] asks;
  - the `dec_instr` of every NOP, JUMP and EXIT word, whatever their other
    bits, and of every illegal word ([DEC-9]);
  - so `dec_instr` = `DEC_NOP` if and only if `dec_instr.op` =
    `DEC_OP_NONE`, if and only if the word is a control word or illegal.

  An entry whose `op` is `DEC_OP_NONE` does nothing in S2 to S5 ([DP-6]).
  `pcu_ctrl` issues `DEC_NOP` for every slot that does nothing, a NOP's or
  EXIT's included ([CTRL-12]), so the decoder's `dec_instr` for a control
  word is never what makes it do nothing, but it is defined all the same
  ([DEC-2]).

### Where the types live

- **[DEC-15]** `dec_op_e`, `opnd_e`, `dec_instr_t` and `DEC_NOP` are
  declared, exactly as [DEC-11], [DEC-12] and [DEC-14] give them, in the one
  shared SystemVerilog package of [TOP-HIER-9]: the `common` module's
  package in `src/common/rtl/`, named **`bankside_pkg`**. `pcu_decode`,
  `pcu_ctrl` and `pcu_datapath` import them from there, and DV's models take
  the same names and values. The package adds no rule of its own; this doc
  is the one that defines these four. **[bankside]** The `common` doc
  doesn't list its package's contents yet; it is to point here for these
  four (see the PR).

### Timing

- **[DEC-16]** **Combinational paths.** Each of `illegal`, `bank_rd`,
  `bank_sel` and `dec_instr` is combinational from `instr` and from nothing
  else. `pcu_decode` sits on `pcu_ctrl`'s longest path, *w* → `dec` →
  `bank_rd_en` ([CTRL-16]); `illegal` is on that path too, since only a
  legal word's slot is of kind OP. The synthesis run of `pcu_ctrl` measures
  it against the clock period ([TOP-ARCH-3]); `pcu_decode` has no budget of
  its own. **[bankside]**

### What the decoder doesn't output

The hierarchy's list for this doc names the stages used, the slot count and
IMM0/IMM1. They are facts of the yaml that other modules read where they
need them, not outputs of `pcu_decode` ([DEC-2]); this table says where each
comes from:

| Instruction | Stages used (yaml `stages`) | Slots (yaml `slots`) | Who reads it, and from what |
|---|---|---|---|
| NOP | – | max(IMM0, 1) ([TOP-ISA-12]) | `pcu_ctrl`, IMM0 from the word's bits ([CTRL-9], [CTRL-15]) |
| JUMP | – | 0 | `pcu_ctrl`, IMM0 and IMM1 from the word's bits ([CTRL-7]) |
| EXIT | – | 1 | `pcu_ctrl`, the opcode from the word's bits ([CTRL-8]) |
| MOV, FILL | none | 1 | `pcu_datapath`, from `op` ([DP-10], [DP-11]) |
| ADD | ADD (S4) | 1 | as MOV |
| MUL | MULT (S3) | 1 | as MOV |
| MAD, MAC | MULT, ADD | 1 | as MOV |

## Choices weighed

| Choice | Options | Where they differ | Chosen |
|---|---|---|---|
| Fields an instruction ignores, in `dec_instr` | (a) 0; (b) the word's bits, as they are | [Case C](#case-c-two-words-one-instruction): a word and the assembler's word for the same instruction give one `dec_instr` under (a) and two under (b), so under (b) DV's model has to reproduce which bits are don't-care, a unit test can't compare `dec_instr` as a whole, and the stage registers toggle on bits nothing reads. (a) costs an AND gate per index bit and on R | (a), [DEC-13]. **[bankside]** |
| Outputs for an illegal word | (a) `DEC_NOP`, `bank_rd` = 0; (b) the decoded fields and the bank source as for a legal word, only `illegal` raised | Row 13 of [case A](#case-a-worked-words), `MOV GRF_B[0], EVEN_BANK`: under (b) `bank_rd` = 1 and `dec_instr` says "write GRF_B[0]"; nothing happens only because `pcu_ctrl` gates both by the slot kind ([CTRL-11], [CTRL-12]), so [TOP-ISA-24] rests on `pcu_ctrl` alone and a unit test of `pcu_decode` can't check it. Under (a) it holds at both boundaries. The gate on `bank_rd` repeats `pcu_ctrl`'s and synthesis can merge the two | (a), [DEC-9]. **[bankside]** |
| How `op` is encoded | (a) `dec_op_e`, 3 bits, one value `DEC_OP_NONE` for "nothing"; (b) the 4-bit opcode; (c) one-hot, 6 bits | Under (b) "nothing" is four values (NOP 0, JUMP 1, EXIT 2, and a reserved opcode unless the decoder maps it), which `pcu_datapath` must test for in every stage, and each stage register carries one bit more. (c) carries 3 bits more per stage register and saves only a 3-to-6 decode in `pcu_datapath`. With (a), `DEC_NOP` is all zeros and `op` alone says whether the entry does anything | (a), [DEC-11], [DEC-12]. **[bankside]** |
| What `dec_instr_t` carries | (a) [DP-6]'s fields only: `op`, DST, SRC0, SRC1, three indices, R; (b) also SRC2, A, IMM0, IMM1, the stages and slot count (the hierarchy's list) | No behaviour differs. Under (b) the S1/S2 register gains 3 + 1 + 19 bits, plus the stages and slots, that are 0 or unread in every entry: `pcu_datapath` never reads SRC2 ([DP-6]), A is 0 in every legal word, and NOP and JUMP never issue ([CTRL-12]); `pcu_ctrl` reads IMM0 and IMM1 from the word ([CTRL-15]), and the stages follow from `op` | (a), [DEC-11]. **[bankside]** |
| Where the JUMP range check is | (a) `pcu_ctrl`; (b) here, with the PC as a second input | It needs the PC of the JUMP's fetch, which only `pcu_ctrl` has, and `pcu_ctrl` reads the JUMP at port 0 before it chooses the word it gives `dec` ([CTRL-15]); under (b) a second decoder would have to sit on port 0 | (a), [DEC-6], as [CTRL-7] already settles. **[bankside]** |
| Where `dec_instr_t` is declared | (a) the shared package of `common`; (b) a package of `pcu_decode` | [TOP-HIER-9] already chooses (a): three modules and DV use the type | (a), [DEC-15]. **[bankside]** |

## Examples

All three cases come from one script, a bit-level model of this doc
(written from it and the yaml) checked against the top spec's own
assembler, decoder and legality check,
[check_isa.py](../../top/doc/examples/check_isa.py), which the model does
not use. It checks:

1. **Every word class**: all 2^18 = 262144 values of the fields that decide
   legality (opcode, DST, SRC0, SRC1, SRC2, A, R), with the index fields and
   unused bits 0. `illegal` must be check_isa.py's `legal(word)` negated (or
   a reserved opcode), which treats every JUMP as legal as [DEC-6] does;
   `bank_rd` and `bank_sel` the bank source of a legal word; the fields of
   every legal word those of check_isa.py's `decode(word)`; and the word
   assembled back from that text must decode the same ([DEC-13]).
2. **Every index value**: each of the 784 legal combinations (each MOV pair
   with R = 0 and 1, each ADD, MUL, MAC with every SRC2) with all 512 values
   of DST#, SRC0#, SRC1# (64 for MOV and FILL): 379904 words.
3. **Every unused bit**: all values of the bits no field names on the same
   784 combinations; every IMM0 × IMM1 value of NOP, JUMP and EXIT, and
   every value of their unused bits 27–19; and 200000 random 32-bit words
   (seed 31).
4. The rules one by one: `DEC_NOP`, MAC's SRC2 ([DEC-8]), MAD's SRC2
   ([TOP-ISA-23]), the MAC, MAD and MUL source pairs ([TOP-ISA-22]), at most
   one bank source, and `op` ≠ `DEC_OP_NONE` for every legal word.
5. The three tables below, word for word, and Figure 1 and the tables of
   [DEC-11] and [DEC-12] against the model's layout.

What it doesn't sweep: the index fields and unused bits of every *illegal*
class (2^14 values each, about 3.4 × 10^9 words in all). The model never
reads them, so its output for those words is fixed by the class; the random
words sample them against check_isa.py.

Rerun from the repo root (about a minute):

```
.venv/bin/python src/pcu_decode/doc/examples/dec_check.py
```

Output: [examples/dec_check.out](examples/dec_check.out). It exits non-zero
if a check fails or a table below differs from the model.

### Case A: worked words

Each word is assembled by check_isa.py from the instruction, then the field
named in the second column is set by hand. `dec_instr` is the 22-bit value
of [DEC-11] in hex; the operand and index columns are its fields, with "0"
for a field the instruction ignores ([DEC-13]).

| # | Word | Instruction | `illegal` | `bank_rd`, `bank_sel` | `op` | `dst` | `src0` | `src1` | `dst_idx`, `src0_idx`, `src1_idx` | `relu` | `dec_instr` | Shows |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `0x00000000` | `NOP 0` | 0 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-14]: the word 0, `DEC_NOP` |
| 2 | `0x00002FFF` | `NOP 5`, IMM1 = 2047 | 0 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-6]: IMM1 ignored ([TOP-ISA-25]) |
| 3 | `0x10002801` | `JUMP -5, 1` | 0 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-6]: legal here; out of range at PC 2 to 4, which `pcu_ctrl` checks |
| 4 | `0x10000000` | `JUMP -0, 0` (IMM0 = 0) | 0 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-6]: legal here; out of range at every PC ([TOP-ISA-26]) |
| 5 | `0x2007FFFF` | `EXIT`, IMM0 = 255, IMM1 = 2047 | 0 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-6]: IMM0 and IMM1 ignored ([TOP-ISA-25]) |
| 6 | `0x30000000` | opcode 3 | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-5]: reserved opcode |
| 7 | `0xFFFFFFFF` | opcode 15, every other bit 1 | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-5]: reserved opcode |
| 8 | `0x41000000` | `MOV GRF_A[0], EVEN_BANK` | 0 | 1, 0 (EVEN) | MOV | GRF_A | EVEN_BANK | 0 | 0, 0, 0 | 0 | `0x088000` | [DEC-10]: a bank load |
| 9 | `0x41001350` | `MOV(RELU) GRF_A[3], EVEN_BANK`, SRC0# = 5 | 0 | 1, 0 (EVEN) | MOV | GRF_A | EVEN_BANK | 0 | 3, 0, 0 | 1 | `0x088181` | [DEC-13]: a bank's index is 0 ([TOP-ISA-9]) |
| 10 | `0x4A400620` | `MOV ODD_BANK, GRF_B[2]`, DST# = 6 | 0 | 0, 0 | MOV | ODD_BANK | GRF_B | 0 | 0, 2, 0 | 0 | `0x0D2020` | [DEC-10]: a store is not a read; DST# 0 ([TOP-ISA-9]) |
| 11 | `0x44008217` | `MOV SRF_M[2], GRF_A[1]`, bits 15 and 2–0 set | 0 | 0, 0 | MOV | SRF_M | GRF_A | 0 | 2, 1, 0 | 0 | `0x0A0110` | [DEC-6]: unused bits ([TOP-ISA-1]) |
| 12 | `0x53401400` | `FILL GRF_B[4], ODD_BANK`, R = 1 | 0 | 1, 1 (ODD) | FILL | GRF_B | ODD_BANK | 0 | 4, 0, 0 | 0 | `0x11A200` | [DEC-13]: R of FILL is 0 ([TOP-ISA-16]) |
| 13 | `0x43000000` | `MOV GRF_B[0], EVEN_BANK` | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-7]: a crossed pair ([TOP-ISA-15]) |
| 14 | `0x41800000` | `MOV GRF_A[0], GRF_B[0]`, SRC0 = 6 | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-5]: a reserved code in a checked field |
| 15 | `0x40780000` | `MOV GRF_A[0], GRF_B[0]`, SRC1 = 7 | 0 | 0, 0 | MOV | GRF_A | GRF_B | 0 | 0, 0, 0 | 0 | `0x082000` | [DEC-6]: MOV has no SRC1; bits 21–19 unused |
| 16 | `0x811F0200` | `ADD GRF_A[2], EVEN_BANK, SRF_A[0]`, SRC2 = 7 | 0 | 1, 0 (EVEN) | ADD | GRF_A | EVEN_BANK | SRF_A | 2, 0, 0 | 0 | `0x188D00` | [DEC-6]: SRC2 ignored, even reserved ([TOP-ISA-10]) |
| 17 | `0x81280000` | `ADD GRF_A[0], EVEN_BANK, ODD_BANK` | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-7]: two bank sources ([TOP-ARCH-7]) |
| 18 | `0x82D80101` | `ADD GRF_B[1], SRF_A[0], SRF_A[1]` | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-7]: SRF_A read twice |
| 19 | `0x80481012` | `ADD GRF_A[0], GRF_B[1], GRF_B[2]`, bit 12 set | 0 | 0, 0 | ADD | GRF_A | GRF_B | GRF_B | 0, 1, 2 | 0 | `0x182414` | [DEC-13]: bit 12 is unused in the ALU format, `relu` 0 |
| 20 | `0x92100314` | `MUL GRF_B[3], GRF_A[1], SRF_M[4]` | 0 | 0, 0 | MUL | GRF_B | GRF_A | SRF_M | 3, 1, 4 | 0 | `0x210998` | [DEC-13]: every index used |
| 21 | `0x92108314` | `MUL GRF_B[3], GRF_A[1], SRF_M[4]`, A = 1 | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-5]: A = 1 in v1 |
| 22 | `0xA0630015` | `MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]` | 0 | 1, 0 (EVEN) | MAD | GRF_A | GRF_B | EVEN_BANK | 0, 1, 5 | 0 | `0x28301A` | [DEC-13]: MAD keeps SRC1# with a bank SRC1 ([TOP-ISA-20]) |
| 23 | `0xA1110002` | `MAD GRF_A[0], EVEN_BANK, SRF_M[2], GRF_B[2]` | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-7]: MAD's SRC2 must be SRF_A ([TOP-ISA-23]) |
| 24 | `0xB3110000` | `MAC GRF_B[0], EVEN_BANK, SRF_M[0]` (SRC2 = 1, as assembled) | 0 | 1, 0 (EVEN) | MAC | GRF_B | EVEN_BANK | SRF_M | 0, 0, 0 | 0 | `0x318800` | [DEC-8] |
| 25 | `0xB3100000` | the same, SRC2 = 0 | 0 | 1, 0 (EVEN) | MAC | GRF_B | EVEN_BANK | SRF_M | 0, 0, 0 | 0 | `0x318800` | [DEC-8]: the same output as 24 |
| 26 | `0xB3170000` | the same, SRC2 = 7 | 0 | 1, 0 (EVEN) | MAC | GRF_B | EVEN_BANK | SRF_M | 0, 0, 0 | 0 | `0x318800` | [DEC-8]: the same output as 24 |
| 27 | `0xB0210010` | `MAC GRF_A[0], GRF_A[1], EVEN_BANK` | 1 | 0, 0 | NONE | 0 | 0 | 0 | 0, 0, 0 | 0 | `0x000000` | [DEC-7]: MAC writes GRF_B only ([TOP-ISA-21]) |
| 28 | `0xB2010012` | `MAC GRF_B[0], GRF_A[1], GRF_A[2]` | 0 | 0, 0 | MAC | GRF_B | GRF_A | GRF_A | 0, 1, 2 | 0 | `0x310014` | [DEC-7]: a same-file pair ([TOP-ISA-22]) |

- Rows 1 to 5: every control word is legal and decodes to `DEC_NOP`,
  whatever its IMM fields hold. Rows 3 and 4 are JUMPs that `pcu_ctrl`
  finds out of range at some or all PCs ([CTRL-7]); here they are legal
  ([DEC-6]).
- Rows 6, 7, 13, 14, 17, 18, 21, 23, 27: each class of [DEC-5], each giving
  `DEC_NOP` and no bank read ([DEC-9]).
- Rows 9, 10, 11, 12, 15, 16, 19: a field the instruction ignores is set,
  and the word stays legal; the field is 0 in `dec_instr` (compare row 9's
  `0x088181` with case C).
- Row 22: MAD keeps SRC1# = 5 although SRC1 is a bank ([TOP-ISA-20]). An
  ADD, MUL or MAC with a bank SRC1 would give `src1_idx` = 0 ([DEC-13]).
- Rows 24 to 26: MAC with SRC2 = 1, 0, 7, one output ([DEC-8]).

### Case B: every word class

The 2^18 classes of check 1, by opcode. "Legal" counts classes, so it
includes every value of the bits an instruction ignores among those seven
fields (for MOV: SRC1, SRC2 and A, 128 values per combination and R);
"legal operand combinations" counts the distinct values of the fields
[DEC-7] checks. An illegal class is counted under the first reason that
applies, in the order of the columns. Each count is the model's, and the
model agrees with check_isa.py on every class.

| Opcode | Instruction | Classes | Legal | Legal operand combinations | Reserved opcode | A = 1 | Reserved code in a checked field | MAD SRC2 not SRF_A | Combination not listed |
|---|---|---|---|---|---|---|---|---|---|
| 0 | NOP | 16384 | 16384 | – | 0 | 0 | 0 | 0 | 0 |
| 1 | JUMP | 16384 | 16384 | – | 0 | 0 | 0 | 0 | 0 |
| 2 | EXIT | 16384 | 16384 | – | 0 | 0 | 0 | 0 | 0 |
| 3 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 4 | MOV | 16384 | 5120 | 20 | 0 | 0 | 7168 | 0 | 4096 |
| 5 | FILL | 16384 | 1024 | 4 | 0 | 0 | 7168 | 0 | 8192 |
| 6 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 7 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 8 | ADD | 16384 | 640 | 40 | 0 | 8192 | 4736 | 0 | 2816 |
| 9 | MUL | 16384 | 512 | 32 | 0 | 8192 | 4736 | 0 | 2944 |
| 10 | MAD | 16384 | 64 | 32 | 0 | 8192 | 5600 | 2160 | 368 |
| 11 | MAC | 16384 | 256 | 16 | 0 | 8192 | 4736 | 0 | 3200 |
| 12 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 13 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 14 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| 15 | reserved | 16384 | 0 | – | 16384 | 0 | 0 | 0 | 0 |
| all | | 262144 | 56768 | 144 | 114688 | 32768 | 34144 | 2160 | 21616 |

- The legal operand combinations are those of [DEC-7] and the guide: 144 in
  all.
- Every NOP, JUMP and EXIT class is legal ([DEC-6]); every class with a
  reserved opcode is illegal.
- Only MAD has classes in the "MAD SRC2 not SRF_A" column: 2160 classes
  (6 DST × 6 SRC0 × 6 SRC1 named codes, × the 5 named SRC2 codes other
  than SRF_A, × R) with A = 0. A MAD with SRC2 = 6 or 7 counts under
  "reserved code" ([TOP-ISA-23] makes it illegal either way).
- No ADD, MUL or MAC class is illegal through SRC2 ([TOP-ISA-10]).

### Case C: two words, one instruction

Where the two options for ignored fields differ. Each word is a row of case
A with an ignored field set; the second word is the assembler's word for the
same instruction. Under the chosen option (a) both decode to the same
`dec_instr`; under (b), which passes the word's fields through, they don't.

| Case | Word with the ignored field set | The assembler's word | (a) canonical: same `dec_instr`? | (b) raw fields: same `dec_instr`? |
|---|---|---|---|---|
| 9 | `0x41001350` | `0x41001300` `MOV(RELU) GRF_A[3], EVEN_BANK` | yes (`0x088181`) | no (`0x0881D1` vs `0x088181`) |
| 10 | `0x4A400620` | `0x4A400020` `MOV ODD_BANK, GRF_B[2]` | yes (`0x0D2020`) | no (`0x0D2320` vs `0x0D2020`) |
| 12 | `0x53401400` | `0x53400400` `FILL GRF_B[4], ODD_BANK` | yes (`0x11A200`) | no (`0x11A201` vs `0x11A200`) |
