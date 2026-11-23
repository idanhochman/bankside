# common: specification

Owner: architect. Readers: everyone. The designer and DV each build from this
alone, so anything they would have to guess belongs here.

Every rule is tagged `[paper]`, `[ANEMOS]` or `[bankside]`, and every rule a
test can check has an ID: `[CMN-1]`, `[CMN-2]`, ...

## Overview

`common` holds what several modules share. For v1 that is one SystemVerilog
package, **`bankside_pkg`**: the shared package of [TOP-HIER-9]. It holds
two kinds of item:

- **Constants of the encoding**: widths, opcodes, operand codes and the bit
  positions of the instruction fields. Their values are those of
  [bankside_isa.yaml](../../top/doc/bankside_isa.yaml), the source of truth
  for the encoding. This doc names them and gives their types
  ([CMN-4] to [CMN-7]).
- **The decoder's types**: `dec_op_e`, `opnd_e`, `dec_instr_t` and
  `DEC_NOP`. They are defined by [`pcu_decode`'s
  doc](../../pcu_decode/doc/README.md), in [DEC-11], [DEC-12] and [DEC-14],
  and placed here by [DEC-15]. This doc points to them and does not restate
  them.

The package implements those docs and the yaml. It adds no rule of its own
([TOP-HIER-9]). The rules here say which items it holds, what they are named
and how they stay equal to the yaml. `common` has no module, so it has no
ports, no timing and no parent ([TOP-HIER-1]).

[TOP-HIER-1]: ../../top/doc/hierarchy.md#modules
[TOP-HIER-9]: ../../top/doc/hierarchy.md#shared-package-and-the-wrapper
[TOP-ISA-1]: ../../top/doc/programmers_guide.md#instruction-formats
[TOP-ISA-2]: ../../top/doc/programmers_guide.md#illegal-instructions
[TOP-ISA-10]: ../../top/doc/programmers_guide.md#instruction-formats
[TOP-IF-9]: ../../top/doc/interfaces.md#register-file-access-through-the-ports
[DEC-4]: ../../pcu_decode/doc/README.md#reading-the-word
[DEC-11]: ../../pcu_decode/doc/README.md#the-decoded-instruction
[DEC-12]: ../../pcu_decode/doc/README.md#the-decoded-instruction
[DEC-14]: ../../pcu_decode/doc/README.md#the-decoded-instruction
[DEC-15]: ../../pcu_decode/doc/README.md#where-the-types-live
[CTRL-7]: ../../pcu_ctrl/doc/README.md#fetch-and-the-zero-slot-jump
[CTRL-15]: ../../pcu_ctrl/doc/README.md#pcu_decode
[FMUL-1]: ../../fp16_mul/doc/README.md#ports

**Sources.** The papers (ISCA 2021, Table III) give the field layout. The
opcode and operand-code values are ANEMOS's (github.com/gem5-X/cnm_framework
at `f2d4018`, `src/opcodes.h`), as the yaml's header records. Both reach
this doc only through the yaml. The package itself, its names and the way it
is kept in step are **[bankside]**: the papers describe no RTL. ANEMOS's
`src/opcodes.h` plays the same role in C++. It names opcodes `OP_*`, operand
codes `OPC_*`, and gives each field's lowest bit as `*_END`. bankside's
names differ on purpose ([choices](#choices-weighed)).

## The package

- **[CMN-1]** **One package, one file.** `common`'s RTL is one SystemVerilog
  package named `bankside_pkg`, in `src/common/rtl/bankside_pkg.sv`. It is
  the first line of the filelist `src/common/rtl/common.f`. `common` has no
  module. The package imports no other package. **[bankside]** (the name
  was chosen in [DEC-15]).

  Every build that compiles a module importing the package, whether a unit
  build or `top`'s, compiles `bankside_pkg.sv` exactly once, before that
  module. How the filelists arrange this is the designer's choice, but
  there is a catch. Suppose two child filelists each include `common.f` and
  `top`'s filelist includes both. Then the package is read twice, and
  Verilator 5.020 with `-Wall` stops with `MODDUP` ("Duplicate declaration").
  An include guard (`` `ifndef BANKSIDE_PKG_SV `` around the package) lints
  clean in that layout. Both results come from a three-module trial run for
  this doc; it is not kept in the repo.

- **[CMN-2]** **What it holds.** The package holds exactly these items, in
  this declaration order, and nothing else. Each item is defined by the rule
  in the last column. An item that is not in the table needs a change to this
  doc before it is added to the package. **[bankside]**

  | Item | Kind | Defined by |
  |---|---|---|
  | `INSTR_W`, `OPCODE_W`, `OPND_W` | `localparam int` | [CMN-4] |
  | `opcode_e` | enum, `logic [OPCODE_W-1:0]`, members `OPCODE_*` | [CMN-5] |
  | `FLD_*` | `localparam int`, an MSB and an LSB per instruction field | [CMN-7] |
  | `opnd_e` | enum, members `OPND_*`; its codes are those of [CMN-6] | [DEC-12] |
  | `dec_op_e` | enum, members `DEC_OP_*` | [DEC-12] |
  | `dec_instr_t` | packed struct, 22 bits | [DEC-11] |
  | `DEC_NOP` | constant `dec_instr_t` | [DEC-14] |

  `opnd_e`, `dec_op_e`, `dec_instr_t` and `DEC_NOP` are declared exactly as
  `pcu_decode`'s doc gives them. That doc is where their names, widths,
  values and fields are defined, and [DEC-15] says which modules use them.
  The rest of this doc covers only the first three rows.

- **[CMN-3]** **Declarations only.** The package holds only `localparam`s
  and `typedef`s: no functions, tasks, variables or `initial` blocks. It
  synthesizes to nothing on its own. **[bankside]**

### What the package doesn't hold

These are shared by fewer than two modules, so [TOP-HIER-9] doesn't put
them here:

| Not in the package | Why | Where it is |
|---|---|---|
| The `cfg_wr_sel` and `dbg_rd_sel` codes (7 = CRF) | Only `top`'s glue decodes them. Codes 0 to 3 equal the operand codes, but 7 is not one | [TOP-IF-9] |
| An FP16 type | `fp16_mul` and `fp16_add` use `logic [15:0]` ports | [FMUL-1] |
| `ROW_W`, `COL_W` | Parameters of the modules that carry the trigger's row and column, set by `top` | `pcu_ctrl`, `pcu_datapath` |
| The legal operand combinations | They are the decoder's behaviour, not a constant | `pcu_decode` |

## The constants

The values below are copied from the yaml by hand and checked against it by
[pkg_check.py](examples/pkg_check.py) ([Examples](#examples)). Where a table
and the yaml disagree, the yaml is right and the table is a bug.

- **[CMN-4]** **Widths.** Three `localparam int`s. **[bankside]** (the
  names); the values are the yaml's.

  | Constant | Value | From the yaml |
  |---|---|---|
  | `INSTR_W` | 32 | `instruction_width` |
  | `OPCODE_W` | 4 | the width of the `opcode` field (bits 31–28) |
  | `OPND_W` | 3 | the width of the `dst`, `src0`, `src1` and `src2` fields, which is the width of `opnd_e` ([DEC-12]) |

- **[CMN-5]** **Opcodes.** The enum `opcode_e`, of type
  `logic [OPCODE_W-1:0]`, has one member for each entry of the yaml's
  `instructions`. Each member is named `OPCODE_` followed by the entry's key,
  and its value is the entry's `opcode`. Values 3, 6, 7, 12–15 have no
  member: they are the reserved opcodes of [TOP-ISA-2]. Since `opcode_e` is
  4 bits wide, a variable of that type can still hold a reserved value, and
  the decoder must handle it (as illegal). **[bankside]** (the type and
  names), **[ANEMOS]** (the values, through the yaml).

  | Member | Value | yaml key | Format |
  |---|---|---|---|
  | `OPCODE_NOP` | 0 | `NOP` | control |
  | `OPCODE_JUMP` | 1 | `JUMP` | control |
  | `OPCODE_EXIT` | 2 | `EXIT` | control |
  | `OPCODE_MOV` | 4 | `MOV` | data |
  | `OPCODE_FILL` | 5 | `FILL` | data |
  | `OPCODE_ADD` | 8 | `ADD` | ALU |
  | `OPCODE_MUL` | 9 | `MUL` | ALU |
  | `OPCODE_MAD` | 10 | `MAD` | ALU |
  | `OPCODE_MAC` | 11 | `MAC` | ALU |

  `opcode_e` is a different type from `dec_op_e` ([DEC-12]). `opcode_e`
  holds the 4-bit opcode of the word. `dec_op_e` holds the 3-bit operation
  of the decoded instruction, so the two differ in value: `OPCODE_MOV` = 4
  and `DEC_OP_MOV` = 1. [Case B](#case-b-each-opcode-and-the-dec_op_e-it-decodes-to)
  shows the mapping, as the model of `pcu_decode` computes it.

- **[CMN-6]** **Operand codes.** The package's operand-code constants are
  the members of `opnd_e`, as [DEC-12] declares them: one member for each
  entry of the yaml's `operands`, named `OPND_` followed by the key, whose
  value is the entry's `code`. The package declares no second constant for
  any operand code. Codes 6, 7 have no member: they are reserved
  ([TOP-ISA-2]). This table is not a second definition. It lists the yaml's
  codes that [DEC-12]'s members must equal, and the script checks it against
  both. **[bankside]** (the rule of one name per code), **[ANEMOS]** (the
  values, through the yaml).

  | yaml key | Code | Constant |
  |---|---|---|
  | `GRF_A` | 0 | `OPND_GRF_A` |
  | `GRF_B` | 1 | `OPND_GRF_B` |
  | `SRF_M` | 2 | `OPND_SRF_M` |
  | `SRF_A` | 3 | `OPND_SRF_A` |
  | `EVEN_BANK` | 4 | `OPND_EVEN_BANK` |
  | `ODD_BANK` | 5 | `OPND_ODD_BANK` |

- **[CMN-7]** **Field positions.** For each field of the yaml's `formats`
  there are two `localparam int`s, `FLD_<FIELD>_MSB` and `FLD_<FIELD>_LSB`,
  where `<FIELD>` is the field's yaml name in upper case. They hold the
  field's bit range in the 32-bit word, both bits included, so the field is
  `instr[FLD_<FIELD>_MSB:FLD_<FIELD>_LSB]`. The names carry no format,
  because every field the yaml names in more than one format sits at the
  same bits in each. If the yaml ever moves a field in one format only, this
  rule changes first. A bit that no field covers has no constant
  ([TOP-ISA-1]: it is ignored). **[paper]** (the layout, through the yaml),
  **[bankside]** (the names).

  | Constants | Value | yaml field | Formats |
  |---|---|---|---|
  | `FLD_OPCODE_MSB`, `FLD_OPCODE_LSB` | 31, 28 | `opcode` | control, data, ALU |
  | `FLD_IMM0_MSB`, `FLD_IMM0_LSB` | 18, 11 | `imm0` | control |
  | `FLD_IMM1_MSB`, `FLD_IMM1_LSB` | 10, 0 | `imm1` | control |
  | `FLD_DST_MSB`, `FLD_DST_LSB` | 27, 25 | `dst` | data, ALU |
  | `FLD_SRC0_MSB`, `FLD_SRC0_LSB` | 24, 22 | `src0` | data, ALU |
  | `FLD_RELU_MSB`, `FLD_RELU_LSB` | 12, 12 | `relu` | data |
  | `FLD_DST_IDX_MSB`, `FLD_DST_IDX_LSB` | 10, 8 | `dst_idx` | data, ALU |
  | `FLD_SRC0_IDX_MSB`, `FLD_SRC0_IDX_LSB` | 6, 4 | `src0_idx` | data, ALU |
  | `FLD_SRC1_MSB`, `FLD_SRC1_LSB` | 21, 19 | `src1` | ALU |
  | `FLD_SRC2_MSB`, `FLD_SRC2_LSB` | 18, 16 | `src2` | ALU |
  | `FLD_AAM_MSB`, `FLD_AAM_LSB` | 15, 15 | `aam` | ALU |
  | `FLD_SRC1_IDX_MSB`, `FLD_SRC1_IDX_LSB` | 2, 0 | `src1_idx` | ALU |

  `pcu_decode` reads every field at these positions ([DEC-4]), and
  `pcu_ctrl` reads the opcode, IMM0 and IMM1 at them ([CTRL-7], [CTRL-15]).
  Fields of different formats share bits: `imm0` (control, 18–11) covers
  `src2` (18–16), `aam` (15) and `relu` (12), and `imm1` (10–0) covers the
  three index fields. So a field's constant is meaningful only in a word
  whose format is in its last column, which the opcode decides.

## Keeping the package equal to the yaml

- **[CMN-8]** **Written by hand, from this block.** Until the yaml has a
  generator (its header says one comes with the reference model, M3), the
  designer writes `bankside_pkg.sv` by hand. Its constants section is this
  block, character for character. The script renders the block from the yaml
  and fails if the copy here differs, and it lints the block with Verilator
  ([Examples](#examples)). The rest of the file is declared as [CMN-2]
  orders it, from [DEC-11], [DEC-12] and [DEC-14]. When a generator exists,
  it writes the same names and values, and the check of [CMN-9] stays as
  it is. **[bankside]**

```systemverilog
// The constants of [CMN-4] to [CMN-7], from bankside_isa.yaml.
// Widths [CMN-4]
localparam int INSTR_W  = 32;
localparam int OPCODE_W = 4;
localparam int OPND_W   = 3;

// Opcodes [CMN-5]; reserved values have no member
typedef enum logic [OPCODE_W-1:0] {
  OPCODE_NOP  = 4'd0,
  OPCODE_JUMP = 4'd1,
  OPCODE_EXIT = 4'd2,
  OPCODE_MOV  = 4'd4,
  OPCODE_FILL = 4'd5,
  OPCODE_ADD  = 4'd8,
  OPCODE_MUL  = 4'd9,
  OPCODE_MAD  = 4'd10,
  OPCODE_MAC  = 4'd11
} opcode_e;

// Instruction field positions [CMN-7], [msb:lsb] in the 32-bit word
localparam int FLD_OPCODE_MSB   = 31;
localparam int FLD_OPCODE_LSB   = 28;
localparam int FLD_IMM0_MSB     = 18;
localparam int FLD_IMM0_LSB     = 11;
localparam int FLD_IMM1_MSB     = 10;
localparam int FLD_IMM1_LSB     = 0;
localparam int FLD_DST_MSB      = 27;
localparam int FLD_DST_LSB      = 25;
localparam int FLD_SRC0_MSB     = 24;
localparam int FLD_SRC0_LSB     = 22;
localparam int FLD_RELU_MSB     = 12;
localparam int FLD_RELU_LSB     = 12;
localparam int FLD_DST_IDX_MSB  = 10;
localparam int FLD_DST_IDX_LSB  = 8;
localparam int FLD_SRC0_IDX_MSB = 6;
localparam int FLD_SRC0_IDX_LSB = 4;
localparam int FLD_SRC1_MSB     = 21;
localparam int FLD_SRC1_LSB     = 19;
localparam int FLD_SRC2_MSB     = 18;
localparam int FLD_SRC2_LSB     = 16;
localparam int FLD_AAM_MSB      = 15;
localparam int FLD_AAM_LSB      = 15;
localparam int FLD_SRC1_IDX_MSB = 2;
localparam int FLD_SRC1_IDX_LSB = 0;
```

- **[CMN-9]** **Checked in simulation, against the yaml.** `common`'s unit
  test compiles `bankside_pkg` and reads the yaml when it runs, not a copy
  of it. It fails unless all of the following hold: **[bankside]**
  1. every constant of [CMN-4] and [CMN-7] equals the yaml's value;
  2. every `opcode_e` and `opnd_e` member equals the yaml's value, and each
     enum has exactly one member for each yaml entry (`.num()` is 9 for
     `opcode_e` and 6 for `opnd_e`);
  3. `$bits(dec_instr_t)` is 22 and `DEC_NOP` is 0 ([DEC-11], [DEC-14]).

  How the test reads the package's values (for example through a small
  SystemVerilog harness that drives them onto ports) is DV's choice. DV's
  Python models take operand codes, opcodes and field positions from the
  yaml as well, never from this doc or the package. [DEC-15] gives them the
  same names.

- **[CMN-10]** **Who changes what, and when.** **[bankside]**
  - A PR that changes the yaml's opcodes, operand codes, field positions or
    `instruction_width` updates this doc's tables and block in the same PR.
    `pkg_check.py` fails until it does. The architect writes that PR and says
    in it that `bankside_pkg.sv` must follow.
  - The designer then updates `bankside_pkg.sv`. Until that is done, the
    test of [CMN-9] fails on `main`, which is the signal.
  - A module's RTL uses the package's names and never a literal for an
    opcode, an operand code or a field position. A review of the RTL checks
    this. No test can, because a literal that has the right value passes.

## Choices weighed

| Choice | Options | Where they differ | Chosen |
|---|---|---|---|
| Opcode constants: type | (a) an enum `opcode_e`, like `opnd_e`; (b) untyped `localparam logic [3:0]`s | [Case D](#case-d-an-operand-code-where-an-opcode-was-meant): an opcode variable assigned `OPND_EVEN_BANK` by mistake. Under (a) Verilator stops with an `ENUMVALUE` error. Under (b) it gives only a width warning, which goes away once the widths happen to match (for example `{1'b0, OPND_EVEN_BANK}`). Comparing `instr[31:28]` with a member needs no cast under either | (a), [CMN-5]. **[bankside]** |
| Opcode constants: names | (a) `OPCODE_*`; (b) `OP_*`, ANEMOS's opcode names; (c) `OPC_*` | (b) puts `OP_MOV` = 4 next to `DEC_OP_MOV` = 1, two names that differ only by a prefix and have different values. (c) is ANEMOS's prefix for *operand* codes (`OPC_GRF_A` = 0), so anyone reading ANEMOS beside bankside would read `OPC_MOV` as an operand. (a) clashes with neither | (a), [CMN-5]. **[bankside]**. ANEMOS uses `OP_*` |
| Operand-code constants | (a) the `opnd_e` members only; (b) also untyped `localparam`s, such as `OPERAND_EVEN_BANK = 4` | Under (b) code 4 has two names. A yaml change that renumbers EVEN_BANK and updates only one of them gives a package that compiles and disagrees with itself. Under (a) [CMN-9] checks the one name | (a), [CMN-6]. **[bankside]** |
| Field positions | (a) `FLD_*` constants in the package; (b) each module writes the bits from the yaml | They are used by two modules: `pcu_decode` reads every field, and `pcu_ctrl` reads the opcode and the immediates. Say the yaml moved R from bit 12 to ANEMOS's bit 15. Under (b) two RTL files change by hand and no test ties them to the yaml. Under (a) one line changes and [CMN-9] checks it | (a), [CMN-7]. **[bankside]** |
| Field-constant names | (a) one pair per yaml field name; (b) one pair per format and field (`FLD_ALU_DST_MSB`, ...) | No value differs today: every shared field sits at the same bits in each format (the script checks this). (b) gives 22 pairs instead of 12, with five sets of duplicates | (a), [CMN-7]. **[bankside]** |
| Reserved codes | (a) no member; (b) named members, such as `OPCODE_RSVD3` | Take a `case` with one arm per member. Under (b) it has an arm for each reserved value too, and each of those arms has to be written as illegal one by one. Under (a) the reserved values all fall to `default`, the one arm that [TOP-ISA-2] makes illegal. (a) matches `opnd_e` ([DEC-12]) | (a), [CMN-5]. **[bankside]** |
| How the package follows the yaml | (a) hand-written from the doc's block, with the doc checked by script and the RTL checked by test; (b) a generator now; (c) the doc only, no test | The yaml's header plans a generator for M3, alongside the reference model. A generator is tooling, and it is not settled where it lives (`src/common/util/` is the maintainer's), so (b) is not this task's to build. Under (c) a hand slip in `bankside_pkg.sv` (say `OPCODE_MAD = 4'd11`) would surface only as a MAD/MAC mix-up in a system test. Under (a) it fails [CMN-9] item 2 by name | (a), [CMN-8], [CMN-9]. **[bankside]** |

## Examples

One script, [examples/pkg_check.py](examples/pkg_check.py), checks this doc.
It reads the tables of [CMN-2] and [CMN-4] to [CMN-7] back from this file
and compares them against two sources this doc doesn't control:

1. **The yaml**, parsed by the top spec's own checker,
   [check_isa.py](../../top/doc/examples/check_isa.py), which also checks the
   yaml against the programmer's guide. Every width, opcode, operand code and
   field position must equal the yaml. Every yaml entry must have its row,
   and no row may be extra. The reserved values must be exactly the gaps.
2. **`pcu_decode`'s model**, the one in
   [dec_check.py](../../pcu_decode/doc/examples/dec_check.py), which runs
   its own checks first. The operand codes must be the model's `opnd_e`
   codes and [DEC-12]'s rows. Each opcode must decode to its `dec_op_e`
   value (case B). The `FLD_*` constants, applied to 20000 random legal
   words, must give the fields the model decodes (case C).
3. **The block of [CMN-8]**, which must be exactly the script's rendering of
   the yaml. If Verilator is on the PATH, the block must also lint clean
   with `-Wall` in a file `bankside_pkg.sv`, beside a module that uses every
   constant, and case D is run.
4. **The contents table of [CMN-2]**: it must name exactly the items of the
   other tables and of [DEC-11], [DEC-12] and [DEC-14]. Every link here must
   resolve, and every CMN ID must be defined once.

Rerun from the repo root (about a minute, most of it `dec_check.py`):

```
.venv/bin/python src/common/doc/examples/pkg_check.py
```

Output: [examples/pkg_check.out](examples/pkg_check.out), from Verilator
5.020. It exits non-zero if a check fails or a table here differs.

### Case A: the tables against the yaml

The four constant tables above are case A. Group 1 of the script reads each
row back and compares it with the yaml, and its output prints the values it
compared.

### Case B: each opcode and the dec_op_e it decodes to

Each word was assembled by check_isa.py and decoded by `pcu_decode`'s model.
The last column is the `op` the model gives the word.

| `opcode_e` member | Value | Word | Instruction | `dec_instr.op` (model) |
|---|---|---|---|---|
| `OPCODE_NOP` | 0 | `0x00001800` | `NOP 3` | `DEC_OP_NONE` |
| `OPCODE_JUMP` | 1 | `0x10000802` | `JUMP -1, 2` | `DEC_OP_NONE` |
| `OPCODE_EXIT` | 2 | `0x20000000` | `EXIT` | `DEC_OP_NONE` |
| `OPCODE_MOV` | 4 | `0x41000100` | `MOV GRF_A[1], EVEN_BANK` | `DEC_OP_MOV` |
| `OPCODE_FILL` | 5 | `0x53400400` | `FILL GRF_B[4], ODD_BANK` | `DEC_OP_FILL` |
| `OPCODE_ADD` | 8 | `0x80580012` | `ADD GRF_A[0], GRF_B[1], SRF_A[2]` | `DEC_OP_ADD` |
| `OPCODE_MUL` | 9 | `0x92100314` | `MUL GRF_B[3], GRF_A[1], SRF_M[4]` | `DEC_OP_MUL` |
| `OPCODE_MAD` | 10 | `0xA0630015` | `MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]` | `DEC_OP_MAD` |
| `OPCODE_MAC` | 11 | `0xB2010012` | `MAC GRF_B[0], GRF_A[1], GRF_A[2]` | `DEC_OP_MAC` |
| – | 3, 6, 7, 12–15 | opcode *v* in bits 31–28, the rest 0 | reserved | `DEC_OP_NONE`, illegal |

The three control opcodes give `DEC_OP_NONE` ([DEC-14]), as every reserved
opcode does. So "`opcode_e` member to `dec_op_e` member" is not a renaming
that holds value for value, and code that converts one into the other must
go through the decoder.

### Case C: reading one word with the field constants

The word `0x92100314` is `MUL GRF_B[3], GRF_A[1], SRF_M[4]` (the
programmer's guide's ANEMOS example). Each row cuts the word with the
`FLD_*` constants of [CMN-7], then names the value with [CMN-5] or [CMN-6],
and compares it with what `pcu_decode`'s model decodes.

| Field | Bits (`FLD_*_MSB`:`FLD_*_LSB`) | Value | Constant | `dec_instr` field (model) |
|---|---|---|---|---|
| `opcode` | 31:28 | 9 | `OPCODE_MUL` | `op` = `DEC_OP_MUL` |
| `dst` | 27:25 | 1 | `OPND_GRF_B` | `dst` = 1 |
| `src0` | 24:22 | 0 | `OPND_GRF_A` | `src0` = 0 |
| `src1` | 21:19 | 2 | `OPND_SRF_M` | `src1` = 2 |
| `src2` | 18:16 | 0 | `OPND_GRF_A` | not in `dec_instr`: MUL ignores it ([TOP-ISA-10]) |
| `aam` | 15:15 | 0 | – | not in `dec_instr`: 1 is illegal in v1 ([TOP-ISA-2]) |
| `dst_idx` | 10:8 | 3 | – | `dst_idx` = 3 |
| `src0_idx` | 6:4 | 1 | – | `src0_idx` = 1 |
| `src1_idx` | 2:0 | 4 | – | `src1_idx` = 4 |

The script does the same on 20000 random legal words (seed 53), comparing
every field that the instruction does not ignore.

### Case D: an operand code where an opcode was meant

This is the first row of [choices](#choices-weighed). Each option is linted
with the block above and `opnd_e` from [DEC-12], in this module:

```systemverilog
module wrong import bankside_pkg::*; (input logic [INSTR_W-1:0] instr, output logic hit);
  <decl> op;
  assign op  = OPND_EVEN_BANK;  // meant OPCODE_MOV
  assign hit = (instr[FLD_OPCODE_MSB:FLD_OPCODE_LSB] == op);
endmodule
```

| Option | `op` declared as | Verilator `-Wall -Wno-UNUSED` reports | Caught? |
|---|---|---|---|
| (a) | `opcode_e` | `Error-ENUMVALUE`, `Warning-WIDTHEXPAND` | yes: an error, by type |
| (b) | `logic [OPCODE_W-1:0]` | `Warning-WIDTHEXPAND` | only by the width mismatch |
