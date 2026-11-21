# Worked examples for the top spec

Scripts that check the spec's encoding and worked cases, and their saved
output. Rerun from the repo root after changing `src/top/doc/`; each exits
non-zero if the spec disagrees with itself.

| Script | What it shows | Output | Rerun |
|---|---|---|---|
| [check_isa.py](check_isa.py) | `bankside_isa.yaml` parses; the programmer's guide format, opcode and operand tables match it; the legal-combination counts follow from it; every assembler example assembles, decodes back and is legal (with the [TOP-ISA-10] and [TOP-ISA-20] cases); requirement IDs are unique and every reference is defined; every relative link and anchor resolves | [check_isa.out](check_isa.out) | `.venv/bin/python src/top/doc/examples/check_isa.py` |
| [loop_trace.py](loop_trace.py) | Slot-level model of the PC, NOP and JUMP loop state ([TOP-ISA-3], [TOP-ISA-5], [TOP-ISA-8], [TOP-ISA-12], [TOP-ISA-13]) next to ANEMOS; the `JUMP -1, 2` trace in the guide is checked against it | [loop_trace.out](loop_trace.out) | `.venv/bin/python src/top/doc/examples/loop_trace.py` |

The ANEMOS behaviour in `loop_trace.py` is read from github.com/gem5-X/cnm_framework
at commit `f2d4018` (`src/instr_decoder.cpp`, `src/pc_unit.cpp`), not run.
