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

The ANEMOS behaviour in `loop_trace.py` is read from github.com/gem5-X/cnm_framework
at commit `f2d4018` (`src/instr_decoder.cpp`, `src/pc_unit.cpp`), not run.

The ANEMOS facts in `mac_mad_pairs.py` and in the MAD section of the guide are
read from the same commit (`src/instr_decoder.cpp`, `inputs/src/map_dp.cpp`,
`inputs/src/map_conv.cpp`), also not run. `paper_table3.out` was produced with
pypdf 6.14.2 from an IEEE Xplore copy of the paper.
