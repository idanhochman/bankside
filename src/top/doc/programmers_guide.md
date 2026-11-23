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

The same three formats as bitfields, bit 0 on the right, with the yaml's
field names (`dst_idx` is DST#, `aam` is A, `relu` is R); grey bits are
unused ([TOP-ISA-1]). [figures_check.py](examples/figures_check.py) checks
each against the yaml.

![The control format: opcode 31-28, unused 27-19, imm0 18-11, imm1 10-0](img/instr_control.svg)

*Figure 1: the control format (NOP, JUMP, EXIT). Source:
[instr_control.reg.json](img/instr_control.reg.json).*

![The data format: opcode 31-28, dst 27-25, src0 24-22, unused 21-13, relu 12, unused 11, dst_idx 10-8, unused 7, src0_idx 6-4, unused 3-0](img/instr_data.svg)

*Figure 2: the data format (MOV, FILL). Source:
[instr_data.reg.json](img/instr_data.reg.json).*

![The ALU format: opcode 31-28, dst 27-25, src0 24-22, src1 21-19, src2 18-16, aam 15, unused 14-11, dst_idx 10-8, unused 7, src0_idx 6-4, unused 3, src1_idx 2-0](img/instr_alu.svg)

*Figure 3: the ALU format (ADD, MUL, MAD, MAC). Source:
[instr_alu.reg.json](img/instr_alu.reg.json).*

- Control: **IMM0** is bits 18–11 (8 bits), **IMM1** is bits 10–0 (11 bits).
- **R** is the ReLU flag (data format), **A** the AAM flag (ALU format).
- **DST#, SRC0#, SRC1#** are 3-bit register indices, one per operand field.
- **[TOP-ISA-1]** Unused bits (–) are written as 0 by the assembler and ignored by
  the hardware. **[bankside]** The assembler also writes 0 into every field
  an instruction ignores ([assembler syntax](#assembler-syntax)), with one
  exception: it writes GRF_B (code 1) into MAC's SRC2. **[paper]** for that
  encoding (Section III-C: "SRC2 (GRF_B) points to the same GRF register as
  DST"), **[ANEMOS]** for the hardware ignoring it ([TOP-ISA-10]).
- **[TOP-ISA-9]** An index field whose operand is a bank (EVEN_BANK, ODD_BANK)
  selects nothing and is ignored: a bank operand's address comes from the
  trigger ([TOP-ARCH-6]). The one exception is SRC1# of MAD, which also
  indexes the SRF_A addend and so is used even when src1 is a bank
  ([TOP-ISA-20]). **[bankside]**
- **[TOP-ISA-10]** Only MAD uses the SRC2 field. ADD, MUL and MAC ignore it,
  whatever it holds, including a reserved code: their legality
  ([TOP-ISA-2]) doesn't depend on SRC2. **[ANEMOS]** (its decoder reads SRC2
  only for MAD), **[bankside]** (reserved codes there are not illegal).
  For MAC the assembler writes GRF_B there, as the paper's Section III-C
  describes the field ([TOP-ISA-1]); the hardware still ignores it.

**Checked against the paper.** [examples/paper_table3.py](examples/paper_table3.py)
reads Table III's cell borders and labels out of the paper's PDF and maps each
field onto the bit columns. Every field of all three formats matches the yaml
and the table above, including R at bit 12, A at bit 15 and the 3-bit DST#,
SRC0#, SRC1# at 10–8, 6–4, 2–0 ([output](examples/paper_table3.out)). The one
difference: the paper labels bits 2–0 of the data format SRC1#. MOV and FILL
have no SRC1, so bankside leaves those bits unused ([TOP-ISA-1]); the hardware
ignores them either way. **[paper]**, **[bankside]** (unused).

### ANEMOS's layout

ANEMOS uses its own layout, not the paper's Table III. bankside follows the
paper. ANEMOS kernels are translated before they run on bankside
([verification](../dv/README.md)). This table gives ANEMOS's layout for each
field next to bankside's. The ANEMOS bits are the `*_STA`/`*_END` macros of
`src/opcodes.h` at ANEMOS commit `f2d4018`, printed by a run of
[examples/anemos_ctrl.cpp](examples/anemos_ctrl.cpp) built against that
header ([output](examples/anemos_ctrl.out)). [examples/check_isa.py](examples/check_isa.py)
checks the table against that output and against the yaml. **[ANEMOS]**

| Field | Formats | ANEMOS bits | bankside bits | Same? |
|---|---|---|---|---|
| OPCODE | all | 31–28 | 31–28 | yes |
| IMM0 | control | 18–11 | 18–11 | yes |
| IMM1 | control | 10–0 | 10–0 | yes |
| DST | data, ALU | 27–25 | 27–25 | yes |
| SRC0 | data, ALU | 24–22 | 24–22 | yes |
| SRC1 | ALU | 21–19 | 21–19 | yes |
| SRC2 | ALU | 18–16 | 18–16 | yes |
| A (AAM) | ALU | 15 | 15 | yes |
| R (RELU) | data | 15 | 12 | no |
| DST# | data, ALU | 14–10 | 10–8 | no: ANEMOS 5 bits, bankside 3 |
| SRC0# | data, ALU | 9–5 | 6–4 | no: ANEMOS 5 bits, bankside 3 |
| SRC1# | ALU | 4–0 | 2–0 | no: ANEMOS 5 bits, bankside 3 |

- The three ANEMOS index fields are in the order DST#, SRC0#, SRC1#, from
  the top: DST# at 14–10, SRC0# at 9–5, SRC1# at 4–0.
- The control format is the same in both: NOP, JUMP and EXIT words are
  identical bit for bit.
- AAM and RELU share bit 15 in ANEMOS (`AAM_BIT` = `RELU_BIT` = 15). The
  decoder reads RELU only for MOV and AAM only for the ALU instructions, so the
  two never meet. In bankside, R is bit 12 and A is bit 15.
- ANEMOS's assembler also writes SRC1# (4–0) into MOV and FILL words, and
  its decoder ignores it there. bankside leaves 2–0 of the data format unused
  ([TOP-ISA-1]).

Worked translation. The words come from the same run (ANEMOS builds each field
as `value << *_END`, as its `build_instr` does) and from
[examples/check_isa.py](examples/check_isa.py) (bankside):

| Instruction | ANEMOS word | bankside word | What moves |
|---|---|---|---|
| `MUL GRF_B[3], GRF_A[1], SRF_M[4]` | 0x92100C24 | 0x92100314 | DST# 3, SRC0# 1, SRC1# 4 move down into the 3-bit fields |
| `MOV(RELU) GRF_A[3], EVEN_BANK` | 0x41008C00 | 0x41001300 | R from bit 15 to bit 12, DST# from 14–10 to 10–8 |
| `JUMP -3, 7` | 0x10001807 | 0x10001807 | nothing |

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
  instruction reference below), A = 1 (in v1), or if it is a JUMP whose IMM0
  is out of range ([TOP-ISA-26]). An illegal instruction executes as a
  one-slot NOP and sets the sticky `err_illegal` flag
  ([interfaces.md](interfaces.md)). **[bankside]**
- **[TOP-ISA-24]** "Executes as a one-slot NOP" means exactly this: the
  illegal instruction takes one slot, like `NOP 1` ([TOP-ISA-12]). It
  writes no register-file entry and drives no bank access (`bank_rd_en` = 0
  in its S1 cycle, and nothing in S5). It leaves the loop state
  ([TOP-ISA-3]) and the NOP counter unchanged, and sets PC ← PC + 1
  ([TOP-ISA-8]). `err_illegal` is set at the clock edge that ends the
  illegal instruction's S1 cycle, so it reads 1 from the next cycle on and
  stays 1 until reset ([TOP-IF-4]). Nothing else in the unit changes: the
  instructions before it in the pipeline complete, and the next trigger
  issues the instruction at PC + 1. **[bankside]**
- **[TOP-ISA-25]** NOP, JUMP and EXIT have no operand fields. NOP ignores
  IMM1, and EXIT ignores IMM0 and IMM1 (the yaml's `ignored` lists). Their
  values never make the instruction illegal, and the assembler writes them
  as 0. So a control instruction is illegal only through its opcode or, for
  a JUMP, through [TOP-ISA-26]. **[ANEMOS]** (its decoder reads IMM0 only
  for NOP and JUMP, and IMM1 only for JUMP), **[bankside]** (that they are
  never illegal).

A field the instruction ignores ([TOP-ISA-1], [TOP-ISA-9], [TOP-ISA-10],
[TOP-ISA-25], R of FILL) is not "used", so its value never makes the
instruction illegal.

**Why a NOP and a flag.** The paper doesn't say what an
illegal word does. ANEMOS has no legality check. Its decoder switches on the
fields and does nothing for a value it has no case for, and the PC still
advances. So in ANEMOS a reserved opcode is a one-slot no-op without a flag,
but an illegal operand combination may partly execute: in a MOV with a
reserved SRC0 code and a GRF destination, no source is selected, the GRF's
write multiplexer stays at its default (`MUX_EXT`, the host data bus), and
the GRF entry is written with whatever is on that bus (`src/instr_decoder.cpp`,
`OP_MOV`, at `f2d4018`; read, not run). bankside weighed three outcomes:

| Option | What the host and the tests see | Verdict |
|---|---|---|
| One-slot NOP and sticky `err_illegal` (chosen) | The program goes on, and the flag says something was wrong. The reference model gives the same state ([VER-1]) | Defined and observable. It costs one flag bit and the decode check that `pcu_decode` already has ([hierarchy](hierarchy.md)) |
| Halt until reset | The unit can't stall the host ([hazards](theory_of_operation.md#hazards)), so every later command does nothing. A whole run is lost for one bad word, and halting adds a state that `busy` and reset have to cover | Rejected |
| Ignore silently (NOP, no flag) | The same as the chosen option, but nothing records the error in silicon | Rejected: the flag is nearly free, and tests and the host can read it |

Worked case. The word at PC 1 pairs a crossed bank with a GRF
([TOP-ISA-15]). Encoded by [examples/check_isa.py](examples/check_isa.py),
which also checks that the line marked `illegal` is illegal and the others
are legal:

```
PC 0  MOV GRF_A[0], EVEN_BANK
PC 1  MOV GRF_B[0], EVEN_BANK    ; illegal: EVEN_BANK pairs with GRF_A only
PC 2  NOP 1
PC 3  MOV EVEN_BANK, GRF_A[0]
PC 4  EXIT
```

| Slot | bankside (chosen) | Halt | Ignore silently |
|---|---|---|---|
| 1 | PC 0: GRF_A[0] ← bank | same | same |
| 2 | PC 1: one-slot NOP, `err_illegal` ← 1, GRF_B[0] unchanged, no bank read | stops: nothing more runs until reset | one-slot NOP, no flag |
| 3 | PC 2: `NOP 1` | – | `NOP 1` |
| 4 | PC 3: the bank store of GRF_A[0] | – (no store) | the store |
| 5 | PC 4: EXIT, `err_illegal` still 1 | – | EXIT, nothing flagged |

The same word in an instruction-word table, with two more:

| Instruction | Word | bankside | ANEMOS |
|---|---|---|---|
| `MOV GRF_B[0], EVEN_BANK` | `0x43000000` | illegal ([TOP-ISA-15]): one-slot NOP, `err_illegal` ← 1 | no write (its decoder writes GRF_B only from ODD_BANK) |
| `MAC GRF_A[0], GRF_A[1], EVEN_BANK` | `0xB0210010` | illegal ([TOP-ISA-21]: dst is GRF_B only): one-slot NOP, `err_illegal` ← 1 | computes but writes nothing: its MAC decode enables a write only for a GRF_B destination |
| `ADD GRF_A[0], EVEN_BANK, ODD_BANK` | `0x81280000` | illegal ([TOP-ARCH-7]: two bank operands): one-slot NOP, `err_illegal` ← 1 | not traced here: VER-2 leaves illegal words out |

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
  (multi-cycle NOP), **[ANEMOS]** (IMM0 is the length), **[bankside]** (0 → 1,
  and counting triggering commands).
  ANEMOS loads its 8-bit NOP counter with IMM0 − 1, so in ANEMOS `NOP 0`
  wraps to 255 and lasts 256 slots. ANEMOS's counter also counts clock
  cycles, not commands: it counts down every cycle from the NOP's fetch, and
  a command that arrives meanwhile is dropped. With one command per cycle
  the two agree. With fewer, they differ: in the run of
  [examples/anemos_ctrl.cpp](examples/anemos_ctrl.cpp) (case F, a command
  every second cycle) the instruction after `NOP 3` decodes on the 3rd
  command, where bankside issues it on the 4th
  ([output](examples/anemos_ctrl.out)). bankside counts commands because
  the unit does nothing without one ([TOP-IF-1]).

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
  own PC, so that the target PC − IMM0 is between 0 and PC − 1. The
  hardware checks it ([TOP-ISA-26]). **[bankside]**

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

ANEMOS spends a triggering command on every JUMP fetch. Its decoder handles
the JUMP in the cycle of its own command, and the PC shows the target in the
next cycle. Its assembler (`inputs/src/nmc_assembler.cpp`) also emits a
command for each executed JUMP. In the ANEMOS run of the same program
(case A of [examples/anemos_ctrl.out](examples/anemos_ctrl.out)), the three
MOVs, three JUMP fetches and EXIT take 7 commands. bankside takes 4. The
order of instructions is the same; only the count of commands differs. This
is an intended difference ([TOP-ISA-4] is **[paper]**: the zero-cycle
JUMP).

#### When a JUMP rule is broken

Each of the three JUMP programming rules has a defined outcome, so the
reference model and the RTL agree on a broken program too.

- **[TOP-ISA-26]** A JUMP at PC *p* with IMM0 = 0 or IMM0 > *p* (outside
  [TOP-ISA-14]) is illegal ([TOP-ISA-2]). It executes as a one-slot NOP
  ([TOP-ISA-24]): it takes the slot, isn't taken, leaves the loop state
  alone, sets `err_illegal` and PC ← *p* + 1. Every JUMP at PC 0 is
  illegal. The check is made whenever a JUMP is fetched as the first word of
  a slot. A JUMP reached from another JUMP is first held over to the next
  slot ([TOP-ISA-27]) and checked there. **[bankside]**
- **[TOP-ISA-27]** A JUMP is resolved only as the first word fetched in a
  slot. If the instruction a JUMP leads to (its target, or PC + 1 when it
  falls through) is itself a JUMP (breaking [TOP-ISA-7]), the second JUMP is
  not resolved in that slot. The slot issues `NOP 1`: no register-file write,
  no bank access, no loop-state change. The PC is set to the second JUMP's
  address, so the next slot fetches that JUMP first and resolves it as usual
  ([TOP-ISA-3], [TOP-ISA-26], [TOP-ISA-28]). `err_illegal` is not set.
  **[bankside]**
- **[TOP-ISA-28]** There is one loop state, and the table of [TOP-ISA-3]
  applies to every JUMP fetched, whatever its PC. The state doesn't record
  which JUMP started the loop. So a JUMP inside another loop's body (breaking
  [TOP-ISA-6]) reads and changes the outer loop's `loop_active` and
  `loop_cnt`. Nothing is flagged in hardware. **[ANEMOS]** (its decoder keeps
  one `jmp_act_reg`/`jmp_cnt_reg` pair and no loop PC; run in case D below).

How each was chosen:

| Rule broken | Options weighed | Chosen, and why |
|---|---|---|
| [TOP-ISA-14] (IMM0 = 0 or > PC) | (a) illegal under [TOP-ISA-2]; (b) target wraps modulo 32; (c) ANEMOS's behaviour: its PC is 8 bits wide, so PC − IMM0 wraps modulo 256, and a CRF read at PC ≥ 32 returns 0, which is `NOP 0` (256 cycles), after which the PC goes to 0 (case C) | (a). Under (b), `JUMP -5, 1` at PC 2 would run CRF[29] to CRF[31], which the program never wrote and which aren't reset ([TOP-ARCH-5]), and an IMM0 > PC would become a forward jump that tests would have to cover. (c) depends on PC values bankside's 5-bit PC can't hold. (a) costs an 8-bit comparison against the PC, reuses the illegal path, and shows the error on `err_illegal` in silicon. The paper shows only backward jumps (`JUMP -1, 7`, Fig. 5) and gives no range |
| [TOP-ISA-7] (JUMP at a JUMP's target or after a JUMP) | (a) hold the second JUMP over one slot (chosen); (b) issue the second JUMP as a NOP and go on at its PC + 1; (c) make it illegal | (a) keeps the loop-state transitions the program asked for: the second JUMP still counts, one slot late. In that one case bankside spends a command on a JUMP, just as ANEMOS does on every JUMP. (b) would silently skip a loop's back edge. (c) would add a second illegal class decided by the previous word, not the word itself. A JUMP that sees another JUMP is the only case where the fetch would have to resolve two in one slot ([TOP-ISA-4]), and (a) never needs that |
| [TOP-ISA-6] (nested loop) | (a) keep the single loop state (chosen); (b) store the PC of the JUMP that set `loop_active` and make a JUMP at another PC illegal while it is set | (a). It is what [TOP-ISA-3] already implies and what ANEMOS does, and the paper gives no nesting. With the paper silent, ANEMOS decides. (b) would cost a 5-bit register and a comparator to report a program error the assembler already rejects ([programming rules](#programming-rules)) |

With [TOP-ISA-14] enforced, breaking [TOP-ISA-7] always breaks [TOP-ISA-6]
too. A JUMP's target lies before it, so if the target is a JUMP, that JUMP is
inside the first one's body. If a JUMP follows a JUMP, the first is inside
the second's body. So [TOP-ISA-27] decides when the second JUMP is resolved,
and [TOP-ISA-28] decides what it does.

**Worked cases.** Generated by [examples/loop_trace.py](examples/loop_trace.py),
which checks these tables. Its ANEMOS columns are checked against a run of
ANEMOS's own decoder, PC unit and CRF
([examples/anemos_ctrl.cpp](examples/anemos_ctrl.cpp),
[output](examples/anemos_ctrl.out)). One row per triggering command. "ANEMOS:
decoded" is the word its decoder acted on. "(NOP slot)" is a command that
falls inside a multi-cycle NOP.

*Case 6: IMM0 = 0, [TOP-ISA-26].* `JUMP -0, 3` at PC 1:

```
PC 0  MOV GRF_A[0], EVEN_BANK
PC 1  JUMP -0, 3                 ; illegal: IMM0 = 0
PC 2  EXIT
```

| Slot | bankside: issued | `err_illegal` | bankside loop state after | ANEMOS: decoded | ANEMOS loop state after |
|---|---|---|---|---|---|
| 1 | PC 0 MOV | 0 | active 0 | PC 0 MOV | active 0 |
| 2 | PC 1 JUMP illegal | 1 | active 0 | PC 1 JUMP | active 1, cnt 2 |
| 3 | PC 2 EXIT | 1 | active 0 | PC 1 JUMP | active 1, cnt 1 |
| 4 | PC 0 MOV | 1 | active 0 | PC 1 JUMP | active 1, cnt 0 |

bankside: one illegal slot, then EXIT. ANEMOS jumps to the JUMP itself, so it
spends IMM1 + 1 = 4 commands on it before EXIT.

*Case 7: IMM0 > PC, [TOP-ISA-26].* `JUMP -5, 1` at PC 2:

```
PC 0  MOV GRF_A[0], EVEN_BANK
PC 1  MOV GRF_B[0], ODD_BANK
PC 2  JUMP -5, 1                 ; illegal: IMM0 > PC
PC 3  EXIT
```

| Slot | bankside: issued | `err_illegal` | bankside loop state after | ANEMOS: decoded | ANEMOS loop state after |
|---|---|---|---|---|---|
| 1 | PC 0 MOV | 0 | active 0 | PC 0 MOV | active 0 |
| 2 | PC 1 MOV | 0 | active 0 | PC 1 MOV | active 0 |
| 3 | PC 2 JUMP illegal | 1 | active 0 | PC 2 JUMP | active 1, cnt 0 |
| 4 | PC 3 EXIT | 1 | active 0 | PC 253 NOP | active 1, cnt 0 |
| 5 | PC 0 MOV | 1 | active 0 | (NOP slot) | active 1, cnt 0 |

ANEMOS's PC becomes 2 − 5 mod 256 = 253. The CRF read there returns 0, a
`NOP 0`, and the following 255 commands are NOP slots.

*Case 8: nested loops, [TOP-ISA-28].* The intent is an outer loop over PC 0
to 3, run twice, and an inner loop over PC 1, run twice each time: PC 1 four
times and EXIT in slot 9.

```
PC 0  MOV GRF_A[0], EVEN_BANK
PC 1  MOV GRF_B[0], ODD_BANK
PC 2  JUMP -1, 1                 ; inner loop, inside the outer one's body
PC 3  MOV GRF_A[1], EVEN_BANK
PC 4  JUMP -4, 1
PC 5  EXIT
```

| Slot | bankside: issued | `err_illegal` | bankside loop state after | ANEMOS: decoded | ANEMOS loop state after |
|---|---|---|---|---|---|
| 1 | PC 0 MOV | 0 | active 0 | PC 0 MOV | active 0 |
| 2 | PC 1 MOV | 0 | active 0 | PC 1 MOV | active 0 |
| 3 | PC 1 MOV | 0 | active 1, cnt 0 | PC 2 JUMP | active 1, cnt 0 |
| 4 | PC 3 MOV | 0 | active 0 | PC 1 MOV | active 1, cnt 0 |
| 5 | PC 0 MOV | 0 | active 1, cnt 0 | PC 2 JUMP | active 0 |
| 6 | PC 1 MOV | 0 | active 1, cnt 0 | PC 3 MOV | active 0 |
| 7 | PC 3 MOV | 0 | active 0 | PC 4 JUMP | active 1, cnt 0 |
| 8 | PC 0 MOV | 0 | active 1, cnt 0 | PC 0 MOV | active 1, cnt 0 |
| 9 | PC 1 MOV | 0 | active 1, cnt 0 | PC 1 MOV | active 1, cnt 0 |
| 10 | PC 3 MOV | 0 | active 0 | PC 2 JUMP | active 0 |
| 11 | PC 0 MOV | 0 | active 1, cnt 0 | PC 3 MOV | active 0 |
| 12 | PC 1 MOV | 0 | active 1, cnt 0 | PC 4 JUMP | active 1, cnt 0 |
| 13 | PC 3 MOV | 0 | active 0 | PC 0 MOV | active 1, cnt 0 |
| 14 | PC 0 MOV | 0 | active 1, cnt 0 | PC 1 MOV | active 1, cnt 0 |

From slot 4 on, bankside cycles through PC 3, 0 and 1 for ever. When the outer JUMP
starts the loop again (`loop_cnt` = 0), the inner JUMP finds `loop_active` = 1
and `loop_cnt` = 0. It takes that as its own last iteration and clears the
state, so the outer JUMP starts again. EXIT is never reached
(`loop_trace.py` runs 1000 slots), and only reset ends the run. ANEMOS cycles
the same way (period 5 commands, since its JUMPs take a command each). The
outcome is the same in both, so VER-2 has no difference to mask here.

*Case 9: a JUMP right after a JUMP, [TOP-ISA-27].*

```
PC 0  MOV GRF_A[0], EVEN_BANK
PC 1  JUMP -1, 1
PC 2  JUMP -2, 0                 ; follows a JUMP; IMM1 = 0, never taken
PC 3  EXIT
```

| Slot | bankside: issued | `err_illegal` | bankside loop state after | ANEMOS: decoded | ANEMOS loop state after |
|---|---|---|---|---|---|
| 1 | PC 0 MOV | 0 | active 0 | PC 0 MOV | active 0 |
| 2 | PC 0 MOV | 0 | active 1, cnt 0 | PC 1 JUMP | active 1, cnt 0 |
| 3 | NOP 1 (the JUMP at PC 2 waits) | 0 | active 0 | PC 0 MOV | active 1, cnt 0 |
| 4 | PC 3 EXIT | 0 | active 0 | PC 1 JUMP | active 0 |
| 5 | PC 0 MOV | 0 | active 0 | PC 2 JUMP | active 1, cnt 4294967295 |

In slot 3 the first JUMP falls through to PC 2, which holds a JUMP, so the
slot is `NOP 1` and the second JUMP is resolved in slot 4 (never taken,
[TOP-ISA-13]), with EXIT issued in the same slot. ANEMOS spends a command on
each JUMP fetch anyway. Its last row differs only because of IMM1 = 0
([TOP-ISA-13]).

### EXIT

`EXIT` ends the microkernel. **[TOP-ISA-5]** PC ← 0 and the loop state
([TOP-ISA-3]) is cleared; it occupies one slot. Instructions already in the
pipeline complete. The next triggering command starts again at CRF[0].
**[ANEMOS]** (PC ← 0), **[bankside]** (clearing the loop state: ANEMOS's
EXIT resets only the PC).

### MOV

`MOV dst, src` or `MOV(RELU) dst, src` copies a register or bank column.
**[paper]** (GRF ← GRF/bank, ReLU), **[ANEMOS]** (SRF and bank destinations,
the even/odd pairing, GRF → SRF uses lane 0, [TOP-ISA-29]).

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
  and crossed pairs such as EVEN_BANK → GRF_B.
- **[TOP-ISA-29]** **Lanes.** Lane *l* (0 to 15) of a 256-bit value (a GRF
  entry, a bank column, `bank_rd_data`, `bank_wr_data`) is bits
  16*l* + 15 to 16*l*. MOV from a GRF entry into an SRF entry writes lane 0,
  bits 15–0, and ignores the other 15 lanes. **[ANEMOS]** (its SRF write
  input from the GRFs is wired to `grfa_out1[0]` and `grfb_out1[0]`, the
  first lane, in `src/imc_core.h` at `f2d4018`), **[bankside]** (lane
  numbering by bit position). The paper says only that data moves "among
  GRF, SRF, and BANK" (Section III-C), and its MOV count covers GRF
  destinations only, so it names no lane. Other options weighed: another
  fixed lane (no source picks one, and lane 0 is the one ANEMOS takes), or
  making GRF → SRF illegal (it would drop eight ANEMOS-legal pairs, and with
  them the only way to move a computed result into an SRF without the host).
- **[TOP-ISA-30]** With R = 1, ReLU ([TOP-FP-8]) is applied on every legal
  MOV pair, whatever the destination: to all 16 lanes for a GRF or bank
  destination, and to the one 16-bit value for an SRF destination (after
  lane 0 is selected, for GRF → SRF). **[paper]** (Section III-C: "a flag
  bit determines whether or not ReLU is performed during data movement",
  with no restriction to a destination). ANEMOS **differs**: it applies ReLU
  in the GRF write multiplexer (`src/grf.cpp`), so its R has an effect only
  when the destination is GRF_A or GRF_B, and a `MOV(RELU)` into an SRF or a
  bank copies the value unchanged. The paper comes first.

**Worked cases.** GRF_A[1] holds 0xBC00 (−1) in lane 0, 0x4000 (+2) in lane
1, and other values in lanes 2 to 15. SRF_M[0] holds 0xC000 (−2). Words
encoded by [examples/check_isa.py](examples/check_isa.py):

| Instruction | Word | bankside | ANEMOS |
|---|---|---|---|
| `MOV SRF_M[2], GRF_A[1]` | `0x44000210` | SRF_M[2] ← 0xBC00 (lane 0) | same |
| `MOV(RELU) SRF_M[2], GRF_A[1]` | `0x44001210` | SRF_M[2] ← 0x0000 (ReLU of lane 0) | SRF_M[2] ← 0xBC00 (R has no effect) |
| `MOV(RELU) GRF_B[0], SRF_M[0]` | `0x42801000` | GRF_B[0] ← 0x0000 in all 16 lanes | same (a GRF destination) |
| `MOV(RELU) EVEN_BANK, GRF_A[1]` | `0x48001010` | the bank column gets 0x0000 in lane 0, 0x4000 in lane 1, ReLU of each other lane | the column gets GRF_A[1] unchanged |

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
  - (src0, src1) is one of the 16 pairs of [TOP-ISA-22]; dst ∈ {GRF_A, GRF_B}.
- **[TOP-ISA-23]** The addend is always SRF_A: the SRC2 field must hold the
  SRF_A code (3). Any other value (GRF_A, GRF_B, SRF_M, EVEN_BANK, ODD_BANK
  or a reserved code) makes the MAD illegal ([TOP-ISA-2]). **[paper]**
  (Table II lists only SRF_A for SRC2), **[bankside]** (other values are
  illegal rather than ignored, so that a MAD never adds something other
  than what its SRC2 field names).
  ANEMOS's decoder also accepts GRF_A, GRF_B, EVEN_BANK and ODD_BANK in SRC2
  and routes them to the adder, indexed by SRC1#. bankside doesn't follow
  it: the paper comes first. No ANEMOS kernel uses that: its convolution
  kernels write `MAD GRFB0 EVEN_BANK SRFM0 SRFA0`.
- **[TOP-ISA-20]** The addend's index *j* is always the SRC1# field, whatever
  src1 is. There is no SRC2# field. **[paper]** (Section III-C: SRC1# and
  SRC2# "point to the same register index but in different register files
  (e.g., SRF_M and SRF_A, respectively)"; Table III has no SRC2# field),
  **[ANEMOS]** (its decoder indexes the SRC2 operand with `SRC1_N`, also when
  src1 is a bank, which the paper doesn't cover), **[bankside]** (the
  assembler rules below).
  - If src1 is a GRF or SRF_M entry, SRC1# is also src1's index, so *j* is
    the same number: `MAD d, a, SRF_M[k], SRF_A[k]`. The assembler rejects
    `MAD d, a, SRF_M[2], SRF_A[3]`.
  - If src1 is a bank, SRC1# selects nothing for src1 ([TOP-ISA-9]) and holds
    *j* alone: `MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]` has SRC1# = 5.
  - The hardware reads SRF_A[SRC1#] for every legal MAD and doesn't look at
    the kind of src1 to do so.

**Worked cases.** Encoded by [examples/check_isa.py](examples/check_isa.py),
which checks each word against this table.

| Instruction | Word | bankside | ANEMOS |
|---|---|---|---|
| `MAD GRF_A[0], ODD_BANK, SRF_M[2], SRF_A[2]` | `0xA1530002` | GRF_A[0] ← round(round(bank × SRF_M[2]) + SRF_A[2]) | same |
| `MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]` | `0xA0630015` | GRF_A[0] ← round(round(GRF_B[1] × bank) + SRF_A[5]); SRC1# = 5 | same |
| `MAD GRF_A[0], EVEN_BANK, SRF_M[2], GRF_B[2]` | `0xA1110002` | illegal ([TOP-ISA-23]): one-slot NOP, `err_illegal` ← 1 | GRF_A[0] ← round(round(bank × SRF_M[2]) + GRF_B[2]) |
| `MAD GRF_B[1], EVEN_BANK, GRF_B[3], SRF_A[3]` | `0xA30B0103` | GRF_B[1] ← round(round(bank × GRF_B[3]) + SRF_A[3]) | reads the wrong GRF_B entry, see below |

The last row is legal in both, but ANEMOS computes something else: for a MAD
with a bank src0 and src1 = GRF_B, its decoder writes SRC1# into GRF_A's
second read address instead of GRF_B's (`src/instr_decoder.cpp`, the
`OP_MAD` bank branch, at commit `f2d4018`; read, not run), so GRF_B is read
at a stale index. That is an ANEMOS bug, not a bankside rule; comparisons
against ANEMOS must leave this combination out.

### MAC

- **[TOP-ISA-21]** `MAC GRF_B[i], src0, src1`:
  GRF_B[i] ← round(GRF_B[i] + round(src0 × src1)) ([TOP-FP-3]), with *i* =
  DST#. **[paper]** (Table II; GRF_B is the only destination).
  - (src0, src1) is one of the 16 pairs of [TOP-ISA-22]; dst is GRF_B only.
    The hardware ignores the SRC2 field ([TOP-ISA-10]); the assembler
    writes GRF_B (code 1) there ([TOP-ISA-1]).
- The accumulator is read late, in S4, with a bypass ([TOP-HAZ-2]). A MAC may
  follow the previous write of its GRF_B entry immediately ([TOP-HAZ-4]).
- The paper's Fig. 7 and the Hot Chips slides show `MAC GRF_A, …`, which
  contradicts Table II and the text. bankside treats the figure as an erratum.
- The paper's Section III-C describes MAC's SRC2 as GRF_B: "SRC2 (GRF_B)
  points to the same GRF register as DST". The field carries no information
  of its own: the accumulator is GRF_B[DST#] whatever SRC2 holds. So bankside
  splits the two readings. The assembler follows the paper and writes GRF_B
  (**[paper]**, [TOP-ISA-1]); the hardware follows ANEMOS, whose decoder reads
  SRC2 only for MAD, and ignores the field (**[ANEMOS]**, [TOP-ISA-10]).
  ANEMOS's assembler writes 0 (GRF_A) there instead, and such a word runs
  the same MAC on bankside, so translated ANEMOS kernels need no rewrite of
  SRC2.

Worked case. `MAC GRF_B[0], EVEN_BANK, SRF_M[0]` with three values in SRC2
(bits 18–16). All three run the same MAC, GRF_B[0] ← round(GRF_B[0] +
round(bank × SRF_M[0])), on bankside and in ANEMOS; only the first is what
bankside's assembler writes. Checked by
[examples/check_isa.py](examples/check_isa.py):

| SRC2 | Word | Who writes it | bankside |
|---|---|---|---|
| 1 (GRF_B) | 0xB3110000 | bankside's assembler, as the paper describes the field | the MAC above |
| 0 (GRF_A) | 0xB3100000 | ANEMOS's assembler (`nmcInst` defaults `src2` to 0) | the same MAC |
| 7 (reserved) | 0xB3170000 | nobody; built by hand | the same MAC: legal ([TOP-ISA-10]) |

The options weighed (issue #19): ignoring SRC2 with the assembler writing 0
(the earlier rule) matches ANEMOS but not the paper's encoding; requiring
SRC2 = GRF_B and making other values illegal matches the paper strictly, but
it would make the 0xB3100000 row illegal, so every ANEMOS MAC kernel would
need SRC2 rewritten and VER-8 would gain an illegal class, for no hardware
gain. The chosen split gives the paper's words and still runs both rows.

### Legal combinations compared with the paper

The bankside counts are computed from the yaml `legal` lists by
[examples/check_isa.py](examples/check_isa.py).

- **[TOP-ISA-22]** MAC and MAD accept the same 16 (src0, src1) source pairs as
  MUL: src0 ∈ {GRF_A, GRF_B, EVEN_BANK, ODD_BANK}, src1 ∈ {GRF_A, GRF_B,
  EVEN_BANK, ODD_BANK, SRF_M}, at most one of them a bank ([TOP-ARCH-7]).
  Any other pair is illegal ([TOP-ISA-2]). **[ANEMOS]** (its decoder has a
  datapath route for each of these pairs), against the **[paper]**'s count:
  Table II gives MAC 14 and MAD 28, two source pairs fewer, without saying
  which two.

| src0 \ src1 | GRF_A | GRF_B | EVEN_BANK | ODD_BANK | SRF_M |
|---|---|---|---|---|---|
| GRF_A | legal | legal (a) | legal (c) | legal | legal |
| GRF_B | legal | legal | legal | legal (c) | legal |
| EVEN_BANK | legal (b) | legal | – | – | legal (d) |
| ODD_BANK | legal | legal | – | – | legal (d) |

Pairs a published example or kernel uses: (a) the paper's Section IV-B,
`MAD GRF_B[0], GRF_A[0], GRF_B[1]` (printed without its SRF_A operand); (b) the paper's Fig. 7,
`MAC(AAM) GRF_A, EVENBANK, GRF_A`; (c) ANEMOS's dot-product kernels
(`map_dp.cpp`); (d) ANEMOS's convolution kernels (`map_conv.cpp`), MAC and
MAD. The paper's Fig. 5 and Section III-C also multiply a bank by GRF_A and by
SRF_M without naming the bank.

**Why all 16.** Read with GRF = {GRF_A, GRF_B} and BANK = {EVEN_BANK,
ODD_BANK} and at most one bank operand, Table II gives MUL 16 pairs × 2
destinations = 32 and ADD 20 × 2 = 40, as printed, and the four rows add up
to the 114 operand combinations the paper's text states. The same reading
gives MAC 16 and MAD 32, so the paper drops two pairs from MAC and MAD that
it keeps for MUL. Its text doesn't say which. 45 different choices of two
pairs reproduce 14 and 28 without dropping a pair from the list above
([examples/mac_mad_pairs.py](examples/mac_mad_pairs.py),
[output](examples/mac_mad_pairs.out)), so the count can't settle it. With the
paper silent, ANEMOS breaks the tie, and its decoder accepts all 16. (It
doesn't reject two bank operands either; [TOP-ARCH-7], from the paper's MUL
and ADD counts, keeps those out.) The
superset also means no program the paper's hardware runs is illegal on
bankside; the cost is that bankside runs up to two pairs the paper's hardware
may reject.

The option weighed against it: drop the same-file pairs (GRF_A, GRF_A) and
(GRF_B, GRF_B), which gives exactly 14 and 28. Nothing in the paper points to
those two. MUL keeps both (its 32 needs all 16), and a MAC or MAD reads its
two sources in S2 exactly like a MUL, so dropping them saves no read port
([register files](theory_of_operation.md#register-files)). The two options
differ on, for example, `MAC GRF_B[0], GRF_A[1], GRF_A[2]` (`0xB2010012`):
with all 16 pairs (and in ANEMOS) GRF_B[0] ← round(GRF_B[0] +
round(GRF_A[1] × GRF_A[2])); with 14 it would be illegal, a one-slot NOP that
sets `err_illegal` and leaves GRF_B[0] unchanged.

| Op | bankside | Paper (Table II) | Note |
|---|---|---|---|
| MUL | 32 | 32 | |
| ADD | 40 | 40 | |
| MAC | 16 | 14 | 16 source pairs × GRF_B ([TOP-ISA-22]). The paper excludes two more pairs without saying which; bankside allows them (ANEMOS). |
| MAD | 32 | 28 | The same 16 pairs × 2 destinations, SRC2 = SRF_A only ([TOP-ISA-23]). |
| MOV | 20 pairs (× ReLU on/off) | 24 | bankside adds SRF and bank stores (ANEMOS), the paper counts GRF/bank → GRF |
| FILL | 4 | 12 (Hot Chips) | Restricted to bank ↔ GRF |

## Programming rules

A program that breaks one of these still executes, but its result is not what
was meant. An assertion flags each of them in simulation and the reference
model reports it as an error. The assembler also rejects the program when the
rule can be seen in the program text ([TOP-HAZ-3], [TOP-ISA-6], [TOP-ISA-7],
[TOP-ISA-14]); [TOP-HAZ-6] depends on the addresses the host sends and
[TOP-IF-6] and [TOP-IF-13] on the host itself, so the assembler can't check
those.

What the hardware does when a rule is broken is specified for every rule but
the reset-first rule of [TOP-IF-13], so tests that break one on purpose can
compare against the reference model after the violation too. Before the
first reset nothing is defined; the first reset cycle makes the control
state defined again:

| Rule | Outcome when broken | Flagged in hardware |
|---|---|---|
| [TOP-HAZ-3] | the read returns the newest value written by S5 up to its cycle ([TOP-HAZ-5]) | no |
| [TOP-HAZ-6] | the bank read returns the newest store to its column whose S5 cycle is the read's S1 cycle or earlier ([TOP-HAZ-7]) | no |
| [TOP-ISA-6] | one loop state for all JUMPs ([TOP-ISA-28]) | no |
| [TOP-ISA-7] | the second JUMP waits one `NOP 1` slot ([TOP-ISA-27]) | no |
| [TOP-ISA-14] | the JUMP is illegal: a one-slot NOP ([TOP-ISA-26]) | yes, `err_illegal` |
| [TOP-IF-6] | the configuration write is ignored ([TOP-IF-8]) | no |
| [TOP-IF-13] (reset first) | undefined until the end of the first cycle with `rst_n` = 0; register-file and bank contents written before then can't be relied on | no |

1. [TOP-HAZ-3]: at least **2 slots between** a write to a GRF/SRF entry and an
   instruction that reads it as a source. The MAC accumulator is exempt
   ([TOP-HAZ-4]).
2. [TOP-HAZ-6]: at least **3 slots between** a bank store and a read of the
   same bank column (v1 bank model).
3. **[TOP-ISA-6]** One loop at a time: no JUMP inside another loop's body.
   Loops in sequence are fine. **[ANEMOS]** (one loop counter; [TOP-ISA-3]
   keeps one loop state). In simulation the assertion can see it as a JUMP
   fetched while `loop_active` = 1 at a PC other than that of the JUMP that
   set `loop_active`.
4. **[TOP-ISA-7]** A JUMP's target, and the instruction after a JUMP, must not
   be a JUMP (each fetch resolves at most one). **[bankside]** ANEMOS has
   no such rule: there every JUMP takes a command of its own.
5. [TOP-ISA-14]: a JUMP's IMM0 is between 1 and the JUMP's own PC.
6. [TOP-IF-6]: the host writes register files only while `busy` = 0 and
   `trig_valid` = 0.
7. [TOP-IF-13]: the host holds `rst_n` = 0 for at least one cycle before
   its first trigger or configuration write after power-up.

## Differences from ANEMOS

ANEMOS (commit `f2d4018`) is the second reference model ([VER-2] in the
[verification requirements](../dv/README.md)). These are all the
differences in encoding, control and data movement that the spec knows of,
each next to its rule. The FP16 ones are in the
[theory of operation](theory_of_operation.md#fp16-arithmetic) ([TOP-FP-6],
[TOP-FP-8]). How VER-2 masks or excludes each is up to DV.

| Difference | Rule | bankside | ANEMOS |
|---|---|---|---|
| Field layout | [ANEMOS's layout](#anemoss-layout) | R at 12, 3-bit indices at 10–8, 6–4, 2–0 | R at 15, 5-bit indices at 14–10, 9–5, 4–0; control format identical |
| Commands per JUMP fetch | [TOP-ISA-4] | 0 | 1 (each time the JUMP is fetched) |
| `NOP n` length | [TOP-ISA-12] | *n* triggering commands; `NOP 0` = 1 | *n* clock cycles from its fetch, commands meanwhile dropped; `NOP 0` = 256 |
| JUMP with IMM1 = 0 | [TOP-ISA-13] | never taken | taken; its 32-bit counter wraps to 2³² − 1 |
| JUMP with IMM0 = 0 or > PC | [TOP-ISA-26] | illegal: one-slot NOP, `err_illegal` | IMM0 = 0: jumps to itself, IMM1 + 1 commands; IMM0 > PC: PC wraps modulo 256 into `NOP 0` words, then PC 0 |
| JUMP at a JUMP's target or after a JUMP | [TOP-ISA-27] | one `NOP 1` slot, then the JUMP | no extra slot (every JUMP takes one) |
| Nested loops | [TOP-ISA-28] | one loop state | the same |
| EXIT | [TOP-ISA-5] | clears the loop state | PC ← 0 only |
| Illegal words | [TOP-ISA-2], [TOP-ISA-24] | one-slot NOP, `err_illegal` | no check, no flag; a reserved opcode is a no-op, an illegal operand combination may partly execute |
| MAD's SRC2 other than SRF_A | [TOP-ISA-23] | illegal | used as the addend |
| MAC's SRC2 as assembled | [TOP-ISA-1] | GRF_B (1); the hardware ignores it | GRF_A (0); its decoder ignores it too, so the words differ only in bits 18–16 |
| MAD with a bank src0 and src1 = GRF_B | [TOP-ISA-19] | as specified | reads GRF_B at a stale index (an ANEMOS bug, see [MAD](#mad)) |
| `MOV(RELU)` into an SRF or a bank | [TOP-ISA-30] | ReLU applied | R has no effect |
| FILL | [TOP-ISA-16] | the four bank ↔ GRF moves | not implemented |
| Configuration write while running | [TOP-IF-8] | ignored | applied; if an S5 write to the same file comes in the same cycle, the two are ORed bit by bit (enable, index, source select) |
| `err_illegal` | [TOP-ISA-2] | exists | none |
| Index values 8 to 31 | [ANEMOS's layout](#anemoss-layout) | can't be encoded | encodable; its files have 8 entries, and they read 0 for an index above 7 and ignore a write to one (`rf_twoport.h`, `rf_threeport.h`; read, not run) |
| Register files on reset | [TOP-ARCH-5], [TOP-ARCH-9] | kept; never-written entries hold an unpredicted power-up value | cleared to 0 |
| A read in the cycle its entry is written | [TOP-HAZ-1] | write-through: the new value | the stored, old value (its gap slots differ anyway, [TOP-HAZ-3]) |
| GRF_B read ports | [TOP-ARCH-10] | 3: the MAC accumulator has its own | 2: the accumulator's index is ORed into port 1's, so a GRF_B read through port 1 in the same cycle reads the ORed index |
| When MOV and bank stores write | [TOP-PIPE-1] | in S5, like every other write: at most one write per cycle, in program order | a MOV from a register, and a bank store, write in the cycle they are decoded; bank loads and arithmetic through its write pipeline |
| Bank read after a bank store to the same column | [TOP-HAZ-6] | at least 4 slots apart (v1 bank, write first on the same edge) | the store is driven on the bank bus in its own command's cycle; when a later read sees it depends on ANEMOS's DRAM side, outside its unit (not checked) |
| State before the first reset | [TOP-IF-13] | undefined until the end of the first reset cycle; the host resets first | its clocked threads run their reset branch at time 0 (read, not run) |
| `busy` output | [TOP-IF-7] | 1 from the cycle after a trigger until 4 cycles after the last one, longer inside a NOP or a loop | none |

Same in both, so nothing to mask: the rising clock edge ([TOP-ARCH-11]),
the opcode and operand codes, the loop
state's transitions for a JUMP with IMM1 ≥ 1 ([TOP-ISA-3]), the PC wrap
from 31 to 0 ([TOP-ISA-8]), GRF → SRF taking lane 0 ([TOP-ISA-29]), and a
reserved opcode advancing the PC by one.

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
([TOP-ISA-9]), SRC2 of ADD and MUL ([TOP-ISA-10]) and R of FILL.
**[bankside]** The one exception is SRC2 of MAC, which the hardware also
ignores: the assembler writes GRF_B (code 1) there, as the paper's
Section III-C describes the field ([TOP-ISA-1], **[paper]**). So
`MAC GRF_B[0], EVEN_BANK, SRF_M[0]` assembles to `0xB3110000`, not
`0xB3100000`. These encodings are checked by
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
