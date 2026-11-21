# Module hierarchy (v1)

This page splits the v1 unit into modules and says how `top` connects them.
Each child's ports, timing and requirement IDs are defined in the child's own
doc (`src/<module>/doc/`); this page refers to them and never copies them.
Until those docs exist (the per-module tasks under #12), the "What each
module's doc defines" section below is the list of what they must contain.

The module boundaries don't change any behaviour in
[theory_of_operation.md](theory_of_operation.md),
[programmers_guide.md](programmers_guide.md) or
[interfaces.md](interfaces.md): they place that behaviour in modules. The
papers describe blocks (16 FP16 multipliers, 16 FP16 adders, the register
files, control), not an RTL module split, so where the split is our own
choice it is tagged **[bankside]**, and where ANEMOS
(github.com/gem5-X/cnm_framework, commit `f2d4018`, `src/*.h`) is split
differently, the rule says how.

## Modules

- **[TOP-HIER-1]** v1 has these modules, with this hierarchy, instance names
  and requirement-ID prefixes. A prefix belongs to its module only and is
  never reused. **[bankside]**

| Module | Instances (in parent) | Parent | Prefix | Role | First built in |
|---|---|---|---|---|---|
| `top` | – | none | `TOP` | The v1 unit: the ports of [interfaces.md](interfaces.md), the children below and the glue between them (write-port select, debug read select, `busy`). | M4 |
| `pcu_ctrl` | `ctrl` | `top` | `CTRL` | Stage S1: trigger, PC, loop state, NOP counter, CRF fetch, JUMP/EXIT, bank read request, `err_illegal`. Owns the S1/S2 register. | M4 |
| `pcu_decode` | `dec` | `pcu_ctrl` | `DEC` | Combinational: one 32-bit instruction word to its decoded fields and an illegal flag, from [bankside_isa.yaml](bankside_isa.yaml). | M4 |
| `pcu_datapath` | `dp` | `top` | `DP` | Stages S2 to S5: source selection, SRF broadcast, ReLU, the 16 lanes of multiply and add, the MAC accumulator read, write-back and the bank write port. Owns the S2/S3, S3/S4 and S4/S5 registers. | M4 |
| `fp16_mul` | 16, one per lane | `pcu_datapath` | `FMUL` | One FP16 multiply, combinational ([TOP-HIER-3]). | M2 |
| `fp16_add` | 16, one per lane | `pcu_datapath` | `FADD` | One FP16 add, combinational ([TOP-HIER-3]). | M2 |
| `pcu_regfile` | `crf`, `grf_a`, `grf_b`, `srf_m`, `srf_a` | `top` | `RF` | A parameterised register file: depth, width, number of read ports; combinational reads, write-through, one write port, no reset ([TOP-HIER-4]). | M4 |
| `common` | – | none | `CMN` | Exists already. Holds the SystemVerilog package of types shared by several modules ([TOP-HIER-9]). | M2 |

`fp16_mul` and `fp16_add` are the names [VER-4] in the
[verification requirements](../dv/README.md) uses. The lane generate-block and
instance names inside `pcu_datapath` are set by its doc.

![The v1 module tree: top has pcu_ctrl, pcu_datapath and five pcu_regfile instances; pcu_ctrl has pcu_decode; pcu_datapath has 16 fp16_mul and 16 fp16_add](img/top_hierarchy.svg)

*Figure 1: the v1 hierarchy ([TOP-HIER-1]), instance name : module, the doc
that specifies it, and its prefix. Source: [top_hierarchy.dot](img/top_hierarchy.dot).*

## Who owns which stage

- **[TOP-HIER-2]** The pipeline stages of the
  [theory of operation](theory_of_operation.md#pipeline) are split between two
  modules at a register boundary **[bankside]**:
  - `pcu_ctrl` does S1 and holds the **S1/S2 register**. What that register
    holds (valid, the decoded instruction, the trigger's row and column) is
    the **issue** output of `pcu_ctrl`, defined in its doc.
  - `pcu_datapath` does S2 to S5 and holds the **S2/S3, S3/S4 and S4/S5
    registers**, with each stage's control carried next to its data. The
    `bank_wr_*` ports ([TOP-IF-3]) are driven from the S4/S5 register.
  - No other module holds pipeline state. `pcu_regfile` holds only its
    entries; `fp16_mul` and `fp16_add` hold nothing.

  ANEMOS splits by function instead: its `control_unit` drives every
  register-file and FPU select, and its `fpu` holds no stage registers (they
  are inside `fp_multiplier` and `fp_adder`). bankside keeps each stage's data
  and control in one module, so they can't drift apart.

## FP16 units

- **[TOP-HIER-3]** `fp16_mul` and `fp16_add` each compute **one lane** and
  are **purely combinational**: no clock, no reset, no state. `pcu_datapath`
  has 16 of each; lane *i* takes and gives bits `[16i+15 : 16i]` of the
  256-bit vectors. The S3 multiply and S4 add each sit between two stage
  registers of `pcu_datapath`.
  **[paper]** (16 FP16 multipliers and 16 FP16 adders, one per lane),
  **[ANEMOS]** (one `fp_multiplier` and one `fp_adder` per lane, in its
  `fpu`), **[bankside]** (combinational). ANEMOS's units are clocked, with
  `MULT_STAGES` pipeline registers inside `fp_multiplier`.

  Why combinational: the accumulator bypass ([TOP-HAZ-2]) is a one-cycle loop
  S5 → S4 accumulator read → `fp16_add` → S4/S5 register. A register inside
  `fp16_add` would lengthen the loop and break [TOP-HAZ-4]. It also makes each
  unit a pure function of 32 input bits, which is what [VER-4] sweeps.

## Register files

- **[TOP-HIER-4]** The five register files are instances of one module,
  `pcu_regfile`, with parameters for depth, width and number of read ports.
  Every read port is **combinational** and **write-through**: a read of the
  entry the write port is writing in the same cycle returns the data being
  written ([TOP-HAZ-1]). The write takes effect at the end of the cycle. There
  is one write port and no reset ([TOP-ARCH-4], [TOP-ARCH-5]). **[bankside]**
  ANEMOS has three modules (`crf`, `grf` built from per-lane `rf_threeport`,
  and one `srf` holding both SRF_M and SRF_A) and puts the write-data
  multiplexer and ReLU inside `grf`; bankside puts those in `pcu_datapath`.

  | Instance | Depth × width | Functional read ports, and who uses them | Write port driven by |
  |---|---|---|---|
  | `crf` | 32 × 32 | `pcu_ctrl` fetch, S1: the count is set by `pcu_ctrl`'s doc (1 in the [register-file table](theory_of_operation.md#register-files); see #27) | `cfg_*` only |
  | `grf_a` | 8 × 256 | `pcu_datapath`: 2 in S2 | write-port select ([TOP-HIER-6]) |
  | `grf_b` | 8 × 256 | `pcu_datapath`: 2 in S2, 1 in S4 (MAC accumulator) | write-port select |
  | `srf_m` | 8 × 16 | `pcu_datapath`: 1 in S2 | write-port select |
  | `srf_a` | 8 × 16 | `pcu_datapath`: 1 in S2 | write-port select |

  Each instance also has one more read port, for the debug read
  ([TOP-HIER-7]). The functional counts follow from the yaml `legal` lists:
  see [Worked case: read ports from the yaml](#worked-case-read-ports-from-the-yaml).

- **[TOP-HIER-5]** The **accumulator bypass** of [TOP-HAZ-2] is `grf_b`'s
  write-through on its S4 read port. When the instruction in S5 writes the
  GRF_B entry a MAC in S4 reads, the port returns the S5 write data, which is
  the S5 result [TOP-HAZ-2] names. `pcu_datapath` has no separate bypass
  multiplexer. **[bankside]** This is the same behaviour as [TOP-HAZ-2], built
  from the mechanism [TOP-HAZ-1] already needs; see
  [Worked case: the GEMV pattern through the modules](#worked-case-the-gemv-pattern-through-the-modules).

## How top connects its children

![Connections inside top: trig_* to pcu_ctrl, crf to pcu_ctrl fetch, pcu_ctrl issue to pcu_datapath, register-file reads to pcu_datapath, S5 write and cfg_* through the write-port select to the register files, bank ports and status](img/top_connections.svg)

*Figure 2: the connections inside `top` (selected bundles: clock, reset and
the debug read are left out). Dashed lines are configuration paths. Bundle
names are those of the table below; the signals in each are defined by the
child docs. Source: [top_connections.dot](img/top_connections.dot).*

Each row is one bundle. "Defined by" names the doc that defines its signals
and timing; `top` connects them one-to-one unless the row says otherwise.
**[bankside]** throughout.

| Bundle | From → to | Stage | Defined by |
|---|---|---|---|
| `clk` | top port → `ctrl`, `dp`, all `pcu_regfile` instances | – | [interfaces.md](interfaces.md) |
| `rst_n` | top port → `ctrl`, `dp` only (register files aren't reset, [TOP-ARCH-5]) | – | [interfaces.md](interfaces.md) |
| trigger: `trig_valid`, `trig_row`, `trig_col` | top ports → `ctrl` | S1 | [interfaces.md](interfaces.md), `pcu_ctrl` |
| fetch | `ctrl` ↔ `crf` read port(s): address out, instruction word back | S1 | `pcu_ctrl`, `pcu_regfile` |
| bank read request: `bank_rd_en`, `bank_rd_sel`, `bank_rd_row`, `bank_rd_col` | `ctrl` → top ports | S1 ([TOP-IF-2]) | `pcu_ctrl` |
| issue (the S1/S2 register) | `ctrl` → `dp` | S1/S2 | `pcu_ctrl` (its fields come from `pcu_decode`) |
| `bank_rd_data` | top port → `dp` | S2 ([TOP-IF-2]) | [interfaces.md](interfaces.md), `pcu_datapath` |
| S2 reads | `dp` ↔ `grf_a` ports 0–1, `grf_b` ports 0–1, `srf_m` port 0, `srf_a` port 0 | S2 | `pcu_datapath`, `pcu_regfile` |
| S4 accumulator read | `dp` ↔ `grf_b` port 2 | S4 | `pcu_datapath`, `pcu_regfile` |
| S5 write | `dp` → write-port select → `grf_a`, `grf_b`, `srf_m`, `srf_a` | S5 | `pcu_datapath` |
| bank write: `bank_wr_*` | `dp` → top ports | S5 ([TOP-IF-3]) | `pcu_datapath` |
| configuration: `cfg_*` | top ports → `crf` write port, and → write-port select | – | [interfaces.md](interfaces.md) |
| debug read: `dbg_rd_*` | top ports ↔ the debug read port of every instance, through the debug select | – | [interfaces.md](interfaces.md), `pcu_regfile` |
| `busy` | `ctrl` and `dp` → OR → top port | – | `pcu_ctrl`, `pcu_datapath` ([TOP-HIER-8]) |
| `err_illegal` | `ctrl` → top port | – | `pcu_ctrl` |

The glue that `top` itself contains:

- **[TOP-HIER-6]** **Write-port select.** For each of `grf_a`, `grf_b`,
  `srf_m` and `srf_a`: when `cfg_wr_en` = 1 and `cfg_wr_sel` is that file's
  operand code, the write port takes `cfg_wr_idx` and the low bits of
  `cfg_wr_data` (256, 256, 16, 16 bits); otherwise it takes `dp`'s S5 write
  for that file. `crf` is written only from `cfg_*`, when `cfg_wr_sel` = 7,
  with `cfg_wr_data[31:0]`. [TOP-IF-6] keeps a configuration write and an S5
  write from meeting. **[bankside]** What a select or index outside the
  defined values does is #15.
- **[TOP-HIER-7]** **Debug read.** Every instance's debug read port takes its
  index from `dbg_rd_idx`; `dbg_rd_sel` chooses which instance drives
  `dbg_rd_data`. The synthesis wrapper in `src/top/syn/` ties `dbg_rd_*` off,
  so the debug ports drop out of the PPA ([interfaces.md](interfaces.md#debug-port)).
  **[bankside]** Unused selects, out-of-range indices, the unused high bits,
  and whether the debug read sees a same-cycle write are #15; if #15 says it
  must not, `pcu_regfile` makes that port's write-through a parameter.
- **[TOP-HIER-8]** **Busy.** `busy` is the OR of a `busy` output of `ctrl`
  (an instruction valid in S1, NOP slots left, `loop_active`) and one of `dp`
  (an instruction valid in S2 to S5): together the terms of [TOP-IF-7]. The
  exact cycles are #24. **[bankside]**

## Shared package and the wrapper

- **[TOP-HIER-9]** Types used by more than one module (the opcode and
  operand codes of [bankside_isa.yaml](bankside_isa.yaml), and the decoded
  instruction of `pcu_decode`'s doc) are in one SystemVerilog package in
  `src/common/rtl/`. The package implements those docs and adds no rule of its
  own. **[bankside]**
- **[TOP-HIER-10]** v1 has **no wrapper module**: `top` is the unit, with the
  ports of [interfaces.md](interfaces.md), and instantiates its children
  directly. The synthesis wrapper of [TOP-HIER-7] is a file of `src/top/syn/`,
  not a module with a doc. **[bankside]** In v2, the HBM2 command interface
  that replaces the trigger, bank and configuration ports becomes a new child
  of `top`, beside `ctrl`; the other children keep their ports. ANEMOS nests
  `control_unit` (with its `interface_unit`) inside `imc_core`, inside
  `imc_pch`.

## Choices weighed

Each choice lists the options, the case where they differ, and the source.

| Choice | Options | Where they differ | Chosen |
|---|---|---|---|
| FP16 units | (a) one lane, combinational; (b) one 16-lane module, like ANEMOS's `fpu`; (c) internally pipelined, like ANEMOS's `fp_multiplier` | Back-to-back MACs: under (c) the S4 add result isn't at the S4/S5 register one cycle later, so the bypass loop of [TOP-HAZ-2] breaks unless the unit's register *is* the S4/S5 register, which also has to carry MOV and MUL results the adder never sees. (b) vs (a): the same hardware; (a) is the unit [VER-4] sweeps and the "16 multipliers" of the paper | (a), [TOP-HIER-3]. **[paper]**, **[ANEMOS]** (per lane), **[bankside]** (combinational) |
| Register files | (a) one `pcu_regfile`, five instances; (b) `crf`, `grf`, `srf` as in ANEMOS; (c) no module, inside `top` or `pcu_datapath` | Write-through [TOP-HAZ-1] is tested once on one module under (a), three times under (b), and only through whole programs under (c), where a read port hit at distance 3 needs a 4-instruction program and a matching trigger sequence | (a), [TOP-HIER-4]. **[bankside]** |
| Accumulator bypass | (a) `grf_b`'s write-through on its S4 port; (b) a multiplexer in `pcu_datapath` from the S5 result | No program tells them apart: the [worked case](#worked-case-the-gemv-pattern-through-the-modules) gives the same bank write under both. (a) needs no second mechanism, since [TOP-HAZ-1] already makes every port write-through | (a), [TOP-HIER-5]. **[bankside]** |
| Fetch, decode, control | (a) `pcu_ctrl` with a child `pcu_decode`; (b) one `pcu_ctrl`, decode inside; (c) ANEMOS's split: decoder, PC unit and interface unit as three modules | [VER-8] (every class of illegal instruction): under (a) a unit test applies each word class to `pcu_decode` and compares with the yaml, one word per cycle; under (b) each word needs a CRF write and a trigger through the whole unit. (c) puts the zero-slot JUMP ([TOP-ISA-4]) across a module boundary: the PC, loop state and fetch are resolved together in one S1 cycle | (a). **[ANEMOS]** (decoder separate from the PC), **[bankside]** (PC, loop and NOP state in `pcu_ctrl` itself) |
| Datapath | (a) one `pcu_datapath` for S2 to S5, 16 FP16 units of each kind inside; (b) a lane module, 16 instances; (c) ANEMOS's: operand selects in the control unit, muxes and ReLU in `grf`, arithmetic in `fpu` | (c) splits a stage's data from its control across modules ([TOP-HIER-2]). (b) vs (a): no behaviour differs; the lanes are identical and independent, so a generate loop in (a) gives the same structure without one more doc | (a). **[bankside]** |
| Wrapper | (a) none: `top` is the unit; (b) `top` wraps a `pcu_core` with the same ports; (c) a synthesis wrapper module | In v1 (b) has two port tables, `top`'s and `pcu_core`'s, that must stay equal. In v2, `top`'s ports change: under (a) `top` gains the command-interface child and its glue changes; under (b) only the wrapper changes. The children's docs are unchanged under both. (c): the tie-off is two lines of synthesis setup and has no behaviour to specify | (a), [TOP-HIER-10]. **[bankside]** |

## Worked case: the GEMV pattern through the modules

The GEMV kernel of the
[programmer's guide](programmers_guide.md#gemv-partial-sum-no-loop), cut to
two MACs, traced cycle by cycle through the split. It shows [TOP-HIER-2]
(which module does what in each cycle), [TOP-HIER-5] (the bypass is `grf_b`'s
write-through) and [TOP-HAZ-3] at distance 3 on a `grf_b` S2 port. One trigger
per cycle; the trigger of cycle *k* has column *k*. Lane 0 values; GRF_B[0]
holds −1.0 from an earlier run (it isn't reset, [TOP-ARCH-5]).

```
PC 0  MOV GRF_B[0], ODD_BANK
PC 1  MAC GRF_B[0], EVEN_BANK, SRF_M[0]    ; SRF_M[0] = 0.5
PC 2  MAC GRF_B[0], ODD_BANK,  SRF_M[1]    ; SRF_M[1] = 3.0
PC 3  NOP 2                                ; [TOP-HAZ-3]
PC 4  MOV ODD_BANK, GRF_B[0]
PC 5  EXIT
```

| Cycle | `ctrl` (S1) | `dp` S2 | `dp` S3 | `dp` S4 | `dp` S5 |
|---|---|---|---|---|---|
| 1 | PC 0 MOV; bank read ODD col 1 | – | – | – | – |
| 2 | PC 1 MAC; bank read EVEN col 2 | PC 0: `bank_rd_data` = 0.5 | – | – | – |
| 3 | PC 2 MAC; bank read ODD col 3 | PC 1: `bank_rd_data` = 1.0; `srf_m` port 0 [0] = 0.5 | PC 0: pass | – | – |
| 4 | PC 3 NOP, slot 1 of 2 | PC 2: `bank_rd_data` = 2.0; `srf_m` port 0 [1] = 3.0 | PC 1: 1.0 × 0.5 = 0.5 | PC 0: pass | – |
| 5 | PC 3 NOP, slot 2 of 2 | – | PC 2: 2.0 × 3.0 = 6.0 | PC 1: `grf_b` port 2 [0] = **0.5 (write-through)**; 0.5 + 0.5 = 1.0 | PC 0: `grf_b` [0] ← 0.5 |
| 6 | PC 4 MOV | – | – | PC 2: `grf_b` port 2 [0] = **1.0 (write-through)**; 1.0 + 6.0 = 7.0 | PC 1: `grf_b` [0] ← 1.0 |
| 7 | PC 5 EXIT | PC 4: `grf_b` port 0 [0] = **7.0 (write-through)** | – | – | PC 2: `grf_b` [0] ← 7.0 |
| 8 | – | – | PC 4: pass | – | – |
| 9 | – | – | – | PC 4: pass | – |
| 10 | – | – | – | – | PC 4: `bank_wr_*` ODD col 6 ← 7.0 |

- In cycles 5 and 6 each MAC's accumulator comes from the S5 write of the
  instruction just before it, through `grf_b`'s port 2: the [TOP-HAZ-2]
  bypass with no multiplexer in `dp` ([TOP-HIER-5]).
- In cycle 7 the store reads GRF_B[0] in S2, 3 slots after the last MAC, in
  the cycle that MAC writes it: [TOP-HAZ-1] and [TOP-HAZ-3].
- The NOP slots are shown in S1 only. Whether they travel down S2 to S5 is
  #24; nothing in this trace depends on it.

The script runs the same program with the bypass built as (a) `grf_b`
write-through, (b) a multiplexer in `dp`, and (c) neither, and compares the
bank write with an in-order execution of the program:

| Built as | Bank write, ODD col 6, lanes 0 to 3 | Same as in-order? |
|---|---|---|
| (a) write-through, chosen | 7.0, 7.25, 7.5, 7.75 | yes |
| (b) multiplexer in `dp` | 7.0, 7.25, 7.5, 7.75 | yes |
| (c) neither | 6.5, 6.25, 6.0, 5.75 | no: each MAC reads the value from before the previous write (−1.0, then 0.5) |

Script: [examples/module_trace.py](examples/module_trace.py), output
[examples/module_trace.out](examples/module_trace.out). Rerun from the repo
root: `.venv/bin/python src/top/doc/examples/module_trace.py` (exits
non-zero if (a) or (b) differ from the in-order result, or (c) doesn't).

## Worked case: read ports from the yaml

The functional read-port counts of [TOP-HIER-4] come from the operand
combinations the ISA allows. For every legal combination in the yaml, the
script counts the entries of each file read in S2 (sources) and in S4 (the
MAC accumulator). Different instructions are in S2 and S4 in the same cycle,
so a file needs the S2 maximum plus the S4 maximum.

| File | S2 max | reached by | S4 max | Ports | [Register-file table](theory_of_operation.md#register-files) |
|---|---|---|---|---|---|
| GRF_A | 2 | `ADD GRF_A, GRF_A, GRF_A` | 0 | 2 | 2 |
| GRF_B | 2 | `ADD GRF_A, GRF_B, GRF_B` | 1 | 3 | 3 |
| SRF_M | 1 | `MOV GRF_A, SRF_M` | 0 | 1 | 1 |
| SRF_A | 1 | `MOV GRF_A, SRF_A` (ADD reads SRF_A at most once; MAD's SRC2 is its only SRF_A source) | 0 | 1 | 1 |

The same script shows that GRF_B's count stays 3 under either alternative
named for R1 and R11 (#6, #8): dropping the same-file source pairs from
MAC/MAD, or GRF_B as a MAC multiplier source. ADD and MUL with two GRF_B
sources stay legal, and one of them can be in S2 while a MAC reads its
accumulator in S4.

Script: [examples/regfile_ports.py](examples/regfile_ports.py), output
[examples/regfile_ports.out](examples/regfile_ports.out). Rerun from the repo
root: `.venv/bin/python src/top/doc/examples/regfile_ports.py` (exits
non-zero if the counts disagree with the register-file table).

## What each module's doc defines

The per-module tasks (#12) write these. Each doc defines its own ports and
timing; the rules it carries out are cited by their `TOP-` IDs, not copied.

| Module | Its doc defines | Settled first by |
|---|---|---|
| `fp16_mul` | Ports (two FP16 operands, one result), combinational ([TOP-HIER-3]); × under [TOP-FP-1], [TOP-FP-2], [TOP-FP-4] to [TOP-FP-7]; worked cases for subnormals, overflow, ties and NaN | #7 (NaN result) |
| `fp16_add` | As `fp16_mul`, for +, including the signs of zero results ([TOP-FP-5]); the timing budget: one clock period, since it sits in the bypass loop | #7 |
| `pcu_regfile` | Parameters (depth, width, read ports, and write-through per port if #15 needs it); ports; combinational read, write-through, write at the edge, no reset; what a read of a never-written entry gives in simulation | #8, #15 |
| `pcu_decode` | Input word; the decoded instruction (fields, operand selects, indices, R, the stages used, slot count, IMM0/IMM1) and the illegal flag, for every opcode, from the yaml ([TOP-ISA-1], [TOP-ISA-2], [TOP-ISA-9], [TOP-ISA-10], [TOP-ISA-15] to [TOP-ISA-21]) | #6 (merged), #9, #19 |
| `pcu_ctrl` | Ports (trigger, fetch, bank read request, issue, `busy`, `err_illegal`); S1 timing; PC, loop state, NOP counter ([TOP-ISA-3] to [TOP-ISA-8], [TOP-ISA-12], [TOP-ISA-13]); the zero-slot JUMP fetch and the CRF's read ports; the issue bundle (the S1/S2 register); reset ([TOP-IF-4]) | #9, #24, #27 |
| `pcu_datapath` | Ports (issue, `bank_rd_data`, the S2 and S4 read ports, the S5 write, `bank_wr_*`, `busy`); S2 to S5 timing; source selection, SRF broadcast ([TOP-ISA-11]), ReLU ([TOP-FP-8]), MOV GRF → SRF lane, the MAC accumulator read ([TOP-HIER-5]), bank stores ([TOP-ARCH-8], [TOP-IF-3]); lane naming | #7, #8, #9, #10 |
| `common` | A pointer to the docs its package implements ([TOP-HIER-9]); no rules of its own | – |

`pcu_ctrl` must exist before `pcu_decode` is created, and `pcu_datapath`
before `fp16_mul` and `fp16_add`: `new_module.py` needs the parent's `doc/`
folder. Creating the parent from the template is enough; its doc can come
later.
