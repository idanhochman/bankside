# Worked examples for the top spec

Scripts that check the spec's encoding and worked cases, and their saved
output. Rerun from the repo root after changing `src/top/doc/`; each exits
non-zero if the spec disagrees with itself.

| Script | What it shows | Output | Rerun |
|---|---|---|---|
| [check_isa.py](check_isa.py) | `bankside_isa.yaml` parses; the programmer's guide format, opcode and operand tables match it; the legal-combination counts follow from it; every assembler example assembles, decodes back and is legal, except lines marked `; illegal`, which must be illegal (JUMPs checked at their PC, [TOP-ISA-26]); the [TOP-ISA-10], [TOP-ISA-20], [TOP-ISA-22], [TOP-ISA-23] and [TOP-ISA-26] cases; every MAC assembles with SRC2 = GRF_B ([TOP-ISA-1]) and is legal with any SRC2; every instruction word written in the guide encodes as written; requirement IDs are unique and every reference is defined; every relative link and anchor resolves; the ANEMOS layout table matches `src/opcodes.h` as printed in [anemos_ctrl.out](anemos_ctrl.out), and the yaml | [check_isa.out](check_isa.out) | `.venv/bin/python src/top/doc/examples/check_isa.py` |
| [mac_mad_pairs.py](mac_mad_pairs.py) | The options for the MAC/MAD source pairs ([TOP-ISA-22]) and MAD's SRC2 ([TOP-ISA-23]): how Table II's counts follow from the operand sets, the pairs published kernels use, how many two-pair exclusions fit the paper's 14/28, the programs where the options differ, and that the yaml gives the chosen option | [mac_mad_pairs.out](mac_mad_pairs.out) | `.venv/bin/python src/top/doc/examples/mac_mad_pairs.py` |
| [paper_table3.py](paper_table3.py) | Reads Table III's cell borders and labels from the ISCA 2021 PDF, maps each field to its bits and compares with the yaml; prints Table II and the Section III-C sentences on MAC's and MAD's SRC2. Needs your own copy of the paper (not in the repo) and pypdf, which `.venv` lacks | [paper_table3.out](paper_table3.out) | `python3 src/top/doc/examples/paper_table3.py <paper.pdf>` |
| [loop_trace.py](loop_trace.py) | Slot-level model of the PC, NOP and JUMP loop state ([TOP-ISA-3], [TOP-ISA-5], [TOP-ISA-8], [TOP-ISA-12], [TOP-ISA-13]) next to ANEMOS; the `JUMP -1, 2` trace in the guide is checked against it. The broken-rule cases ([TOP-ISA-26] to [TOP-ISA-28], cases 6 to 9) are checked against the guide's tables, and the ANEMOS model against [anemos_ctrl.out](anemos_ctrl.out) | [loop_trace.out](loop_trace.out) | `.venv/bin/python src/top/doc/examples/loop_trace.py` |
| [anemos_ctrl.cpp](anemos_ctrl.cpp) | A testbench that links ANEMOS's own `src/instr_decoder.cpp`, `src/pc_unit.cpp` and `src/crf.cpp` (commit `f2d4018`, unchanged) and drives one triggering command per cycle (every second cycle in case F). It prints the field positions of ANEMOS's `src/opcodes.h` and three words built from them (read by check_isa.py, group 8), then the PC, decoded word and loop state per cycle for the control cases. Needs SystemC (2.3.4 was used) | [anemos_ctrl.out](anemos_ctrl.out) | `A=<cnm_framework>; g++ -std=c++17 -I $A/src src/top/doc/examples/anemos_ctrl.cpp $A/src/instr_decoder.cpp $A/src/pc_unit.cpp $A/src/crf.cpp -lsystemc -o <scratch>/anemos_ctrl`, then `SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_ctrl > src/top/doc/examples/anemos_ctrl.out` |
| [fp_relu_nan.py](fp_relu_nan.py) | The ReLU ([TOP-FP-8]) and NaN-result ([TOP-FP-6]) tables in the theory of operation match bit-level models of bankside's rules and ANEMOS's; the two ReLU rules differ on exactly 1024 of the 65536 inputs. With `--anemos` it checks the tables against [anemos_fp.out](anemos_fp.out), the output of [anemos_fp.cpp](anemos_fp.cpp) built against ANEMOS's own `src/half.hpp` (commit `f2d4018`, needs SystemC); with `--numpy` it checks the NumPy column on the host and the sign-bit NumPy ReLU on all inputs (needs NumPy, which `.venv` lacks). The saved output is from NumPy 2.5.1 on x86-64 and SystemC 2.3.4 | [fp_relu_nan.out](fp_relu_nan.out) | `.venv/bin/python src/top/doc/examples/fp_relu_nan.py`; full: `g++ -std=c++17 -I <cnm_framework>/src src/top/doc/examples/anemos_fp.cpp -lsystemc -o <scratch>/anemos_fp`, `SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fp > src/top/doc/examples/anemos_fp.out`, then `python3 src/top/doc/examples/fp_relu_nan.py --numpy --anemos src/top/doc/examples/anemos_fp.out` |
| [module_trace.py](module_trace.py) | A toy GEMV program traced cycle by cycle through the v1 module split ([TOP-HIER-2] to [TOP-HIER-5]), with the accumulator bypass done three ways (write-through on the accumulator port, a datapath mux, neither) against an in-order reference; backs the worked case in [hierarchy.md](../hierarchy.md) | [module_trace.out](module_trace.out) | `.venv/bin/python src/top/doc/examples/module_trace.py` |
| [regfile_ports.py](regfile_ports.py) | The read ports each register file needs, counted from the yaml's legal combinations (S2 sources plus the S4 accumulator), against the theory-of-operation table; backs [TOP-ARCH-10] and the `pcu_regfile` instance table ([TOP-HIER-4]) | [regfile_ports.out](regfile_ports.out) | `.venv/bin/python src/top/doc/examples/regfile_ports.py` |
| [hazard_trace.py](hazard_trace.py) | A cycle-level model of register-file reads and writes (S2 sources, the S4 accumulator, S5 writes, triggers and bubbles), with and without write-through: the theory of operation's hazard traces (cases A to D), the distance sweep k = 1 to 4, and 20000 random programs checked against in-order execution ([TOP-HAZ-1], [TOP-HAZ-3], [TOP-HAZ-4]) and every S2 read against [TOP-HAZ-5]. Section 4 adds the v1 bank (S1 request, S5 store, write-first or read-first on the same edge, [TOP-IF-2], [TOP-IF-3]): store then load at the limit (case E), [TOP-HAZ-6] broken with an older store in flight and with a bubble (cases F, G), the bank distance sweep k = 1 to 6, and 20000 random programs with loads and stores checked against in-order execution and every bank read against [TOP-HAZ-7]. Section 5 compares every write in S5 ([TOP-PIPE-1]) with ANEMOS's early writes (cases H, I) | [hazard_trace.out](hazard_trace.out) | `.venv/bin/python src/top/doc/examples/hazard_trace.py` |
| [cfg_dbg_ports.py](cfg_dbg_ports.py) | The configuration and debug ports over all 8 selects and 32 indices ([TOP-IF-9] to [TOP-IF-12]): the select table in interfaces.md against the yaml, which writes take effect, what each read returns, the out-of-range options, and the debug read in the cycle of a write (write-through or not, with the [TOP-IF-8] gate) | [cfg_dbg_ports.out](cfg_dbg_ports.out) | `.venv/bin/python src/top/doc/examples/cfg_dbg_ports.py` |
| [figures_check.py](figures_check.py) | The figures against the yaml and the models: the three instruction bitfields of the programmer's guide against the yaml's `formats`; in every timing diagram, each instruction's stages at the cycles its trigger gives ([TOP-IF-1], [TOP-PIPE-1]); the accumulator-bypass figure against `hazard_trace.py`'s case D ([TOP-HAZ-2]); `busy` in the busy figure ([TOP-IF-7]); the before-the-first-reset figure against [TOP-IF-13] | [figures_check.out](figures_check.out) | `.venv/bin/python src/top/doc/examples/figures_check.py` |
| [spec_check.py](spec_check.py) | The whole suite, below | – | `.venv/bin/python src/top/doc/examples/spec_check.py` |
| [busy_trace.py](busy_trace.py) | A slot-level model of triggers, NOP slots, the loop state, EXIT and reset, with every slot a pipeline entry ([TOP-PIPE-4]): `busy` per [TOP-IF-7] against options (1b) and (2b), cycle by cycle for the worked cases (P, Q, S checked word for word against the tables in interfaces.md; R and T printed), and 5000 random runs checking that (1b) accepts the same configuration writes ([TOP-IF-8]), that no accepted write meets an S5 write ([TOP-HIER-6]), and the falling-edge rule | [busy_trace.out](busy_trace.out) | `.venv/bin/python src/top/doc/examples/busy_trace.py` |

The ANEMOS behaviour in `loop_trace.py` is read from github.com/gem5-X/cnm_framework
at commit `f2d4018` (`src/instr_decoder.cpp`, `src/pc_unit.cpp`, `src/crf.cpp`),
and checked against the run of those files in `anemos_ctrl.out`.

The ANEMOS facts in `mac_mad_pairs.py` and in the MAD section of the guide are
read from the same commit (`src/instr_decoder.cpp`, `inputs/src/map_dp.cpp`,
`inputs/src/map_conv.cpp`), also not run. `paper_table3.out` was produced with
pypdf 6.14.2 from an IEEE Xplore copy of the paper.

The ANEMOS facts behind [TOP-ARCH-5], [TOP-ARCH-10], [TOP-HAZ-1] and
[TOP-IF-9] to [TOP-IF-12] (register files cleared on reset, not
write-through, 0 for a read index above their size, writes to one ignored,
GRF_B's shared port 1, the host select codes) are read from the same commit
(`src/rf_twoport.h`, `src/rf_threeport.h`, `src/instr_decoder.cpp`,
`src/interface_unit.cpp`, `src/opcodes.h`, `src/defs.h`), not run.

The ANEMOS facts behind [TOP-PIPE-1], [TOP-ARCH-8] and [TOP-IF-7] (a MOV
from a register and a bank store written in the decode cycle, bank loads
through the write pipeline, no busy output) are read from the same commit
(`src/instr_decoder.cpp`: `grfa_wr_en_comb`, `even_out_en`,
`wr_en_pipe[MULT_STAGES + ADD_STAGES]`; `src/interface_unit.cpp`), not run.

## The whole suite

[spec_check.py](spec_check.py) runs every check of every module's spec in
one command, from the repo root:

```
.venv/bin/python src/top/doc/examples/spec_check.py
```

1. Every script in `src/*/doc/examples/`, six at a time. Each must exit 0,
   and where the saved `.out` is the output of the script's default command
   (every script but the three below), the new output must equal it byte
   for byte. `--update` rewrites the `.out` files that differ instead; use
   it only when the change is intended, and commit them with the change.
2. `.claude/skills/diagrams/scripts/render.py --check src/`: every SVG
   exists and matches its source.
3. Requirement IDs across all modules: each defined once, in the doc of the
   module whose prefix it carries ([TOP-HIER-1]); every ID referenced is
   defined (VER-n in DV's [testplan](../../dv/README.md)).
4. Every relative link and anchor in `src/*/doc/` and `src/*/README.md`.

It takes about six minutes on six cores (`fadd_check.py` is the longest)
and exits non-zero if anything fails. `paper_table3.py` isn't run: it needs
your own copy of the paper.

### The NumPy and ANEMOS runs

Three scripts have a fuller form, and their saved `.out` is from it:

| Script | Full command, from the repo root | Needs | Time |
|---|---|---|---|
| `src/fp16_mul/doc/examples/fmul_check.py` | `<py> src/fp16_mul/doc/examples/fmul_check.py --numpy --exhaustive --anemos src/fp16_mul/doc/examples/anemos_fmul.out` | NumPy | about 15 minutes |
| `src/fp16_add/doc/examples/fadd_check.py` | `<py> src/fp16_add/doc/examples/fadd_check.py --numpy --exhaustive --anemos src/fp16_add/doc/examples/anemos_fadd.out` | NumPy | about 30 minutes |
| `src/top/doc/examples/fp_relu_nan.py` | `<py> src/top/doc/examples/fp_relu_nan.py --numpy --anemos src/top/doc/examples/anemos_fp.out` | NumPy | seconds |

`<py>` is a Python with NumPy. The repo's `.venv` has none, so the saved
outputs came from the system `python3` (CPython 3.12.3, NumPy 2.5.1,
x86-64). To reproduce them without touching `.venv`, make a scratch
environment with the same NumPy:

```
python3 -m venv <scratch>/np
<scratch>/np/bin/pip install numpy==2.5.1
.venv/bin/python src/top/doc/examples/spec_check.py --full --numpy-python <scratch>/np/bin/python
```

`--full` runs the three full commands as well, with that interpreter, and
compares their output with the saved `.out` files. The ANEMOS halves read
the saved ANEMOS outputs (`anemos_fmul.out`, `anemos_fadd.out`,
`anemos_fp.out`); rebuilding those needs SystemC and an ANEMOS checkout, as
each module's doc says. The NaN column of `fp_relu_nan.py` and the NumPy
NaN bits depend on the host's floating-point unit (x86-64 here). Whether
NumPy becomes a dependency of `.venv`, so that CI can run the full form,
is for the maintainer or DV to decide; the spec doesn't need it.
