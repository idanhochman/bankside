# Worked examples for the top spec

Scripts that check the spec's encoding and worked cases, and their saved
output. Rerun from the repo root after changing `src/top/doc/`; each exits
non-zero if the spec disagrees with itself.

| Script | What it shows | Output | Rerun |
|---|---|---|---|
| [check_isa.py](check_isa.py) | `bankside_isa.yaml` parses; the programmer's guide format, opcode and operand tables match it; the legal-combination counts follow from it; every assembler example assembles, decodes back and is legal (with the [TOP-ISA-10], [TOP-ISA-20], [TOP-ISA-22] and [TOP-ISA-23] cases); every instruction word written in the guide encodes as written; requirement IDs are unique and every reference is defined; every relative link and anchor resolves | [check_isa.out](check_isa.out) | `.venv/bin/python src/top/doc/examples/check_isa.py` |
| [mac_mad_pairs.py](mac_mad_pairs.py) | The options for the MAC/MAD source pairs ([TOP-ISA-22]) and MAD's SRC2 ([TOP-ISA-23]): how Table II's counts follow from the operand sets, the pairs published kernels use, how many two-pair exclusions fit the paper's 14/28, the programs where the options differ, and that the yaml gives the chosen option | [mac_mad_pairs.out](mac_mad_pairs.out) | `.venv/bin/python src/top/doc/examples/mac_mad_pairs.py` |
| [paper_table3.py](paper_table3.py) | Reads Table III's cell borders and labels from the ISCA 2021 PDF, maps each field to its bits and compares with the yaml; prints Table II and the Section III-C sentences on MAC's and MAD's SRC2. Needs your own copy of the paper (not in the repo) and pypdf, which `.venv` lacks | [paper_table3.out](paper_table3.out) | `python3 src/top/doc/examples/paper_table3.py <paper.pdf>` |
| [loop_trace.py](loop_trace.py) | Slot-level model of the PC, NOP and JUMP loop state ([TOP-ISA-3], [TOP-ISA-5], [TOP-ISA-8], [TOP-ISA-12], [TOP-ISA-13]) next to ANEMOS; the `JUMP -1, 2` trace in the guide is checked against it | [loop_trace.out](loop_trace.out) | `.venv/bin/python src/top/doc/examples/loop_trace.py` |
| [fp_relu_nan.py](fp_relu_nan.py) | The ReLU ([TOP-FP-8]) and NaN-result ([TOP-FP-6]) tables in the theory of operation match bit-level models of bankside's rules and ANEMOS's; the two ReLU rules differ on exactly 1024 of the 65536 inputs. With `--anemos` it checks the tables against [anemos_fp.out](anemos_fp.out), the output of [anemos_fp.cpp](anemos_fp.cpp) built against ANEMOS's own `src/half.hpp` (commit `f2d4018`, needs SystemC); with `--numpy` it checks the NumPy column on the host and the sign-bit NumPy ReLU on all inputs (needs NumPy, which `.venv` lacks). The saved output is from NumPy 2.5.1 on x86-64 and SystemC 2.3.4 | [fp_relu_nan.out](fp_relu_nan.out) | `.venv/bin/python src/top/doc/examples/fp_relu_nan.py`; full: `g++ -std=c++17 -I <cnm_framework>/src src/top/doc/examples/anemos_fp.cpp -lsystemc -o <scratch>/anemos_fp`, `SYSTEMC_DISABLE_COPYRIGHT_MESSAGE=1 <scratch>/anemos_fp > src/top/doc/examples/anemos_fp.out`, then `python3 src/top/doc/examples/fp_relu_nan.py --numpy --anemos src/top/doc/examples/anemos_fp.out` |

The ANEMOS behaviour in `loop_trace.py` is read from github.com/gem5-X/cnm_framework
at commit `f2d4018` (`src/instr_decoder.cpp`, `src/pc_unit.cpp`), not run.

The ANEMOS facts in `mac_mad_pairs.py` and in the MAD section of the guide are
read from the same commit (`src/instr_decoder.cpp`, `inputs/src/map_dp.cpp`,
`inputs/src/map_conv.cpp`), also not run. `paper_table3.out` was produced with
pypdf 6.14.2 from an IEEE Xplore copy of the paper.
