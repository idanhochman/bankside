# bankside specification

**Status: draft.**

bankside is an open-source SystemVerilog near-bank compute unit, in the class
of the processing unit inside Samsung's HBM-PIM (Aquabolt-XL). One unit sits
beside a pair of DRAM banks and runs a short microkernel of FP16 SIMD
instructions, one per DRAM column command.

It is **not** Samsung's design, is not compatible with it, and is not endorsed
by Samsung. It is a clean-room design from public papers.

## Features

- 16-lane FP16 SIMD datapath (256 bits, one DRAM column per access).
- Register files: CRF (32 × 32-bit instructions), GRF_A and GRF_B
  (8 × 256-bit each), SRF_M and SRF_A (8 × 16-bit each).
- 9 instructions: NOP, JUMP, EXIT, MOV (with optional ReLU), FILL, ADD, MUL,
  MAD, MAC.
- 5-stage pipeline accepting one instruction per cycle, with an accumulator
  bypass so back-to-back MACs into the same register run at full rate.
- IEEE 754 binary16 arithmetic: correctly rounded, round-to-nearest-even,
  subnormals supported, unfused MAC/MAD.

## Scope

| | v1 | v2 |
|---|---|---|
| ISA | All 9 instructions, non-AAM | + AAM (address-aligned mode) |
| Bank side | Simple synchronous bank port, driven by the testbench | Timing-correct HBM2 command interface |
| Modes | Always in PIM mode | SB / AB / AB-PIM mode switching |
| Register-file access | Direct testbench port | Memory-mapped through DRAM writes |

## Documents

| Document | Contents |
|---|---|
| [theory_of_operation.md](theory_of_operation.md) | Architecture, register files, pipeline, hazards, FP16 arithmetic |
| [programmers_guide.md](programmers_guide.md) | Instruction encoding, instruction reference, programming rules, assembler syntax, examples |
| [interfaces.md](interfaces.md) | v1 ports and their timing |
| [hierarchy.md](hierarchy.md) | The v1 modules, their prefixes, and how `top` connects them |
| [../dv/README.md](../dv/README.md) | Verification requirements |
| [bankside_isa.yaml](bankside_isa.yaml) | Machine-readable ISA: **the source of truth for the encoding** |

## Conventions

- **Requirement IDs.** Rules that tests check are tagged `[TOP-AREA-n]`, e.g.
  `[TOP-HAZ-2]`. `TOP` is this module's prefix (see
  [../README.md](../README.md)); areas are `ARCH`, `ISA`, `FP`, `PIPE`, `HAZ`,
  `IF`, `HIER`. Test plans refer to these IDs. IDs are never reused, and their
  numbers carry no order. Draft 0.1 wrote them without the prefix: its `[HAZ-2]` is
  `[TOP-HAZ-2]` here, and the unprefixed forms are retired. An ID is *defined*
  where it is in bold; elsewhere it is a reference.
- **Source tags.** Every rule is tagged `[paper]` (ISCA 2021 or Hot Chips 33),
  `[ANEMOS]` or `[bankside]` (our own choice), in that order of precedence.
  When the sources differ, the rule says what the other one does.
- **Lanes.** A 256-bit vector holds 16 FP16 lanes; lane *i* is bits
  `[16i+15 : 16i]`, so lane 0 is in the low bits.
- **Slot.** One issue slot is one triggering command. Each triggering command
  issues one instruction (or one cycle of a multi-cycle NOP).
- "Must" is a rule for programs or the hardware; "should" is a recommendation.

## Sources

The spec is written only from public material:

1. **ISCA 2021:** S. Lee et al., "Hardware Architecture and Software Stack for
   PIM Based on Commercial DRAM Technology: Industrial Product", ISCA 2021,
   DOI 10.1109/ISCA52012.2021.00013. The field layout (Table III), operations
   (Table II), pipeline, AAM and modes.
2. **Hot Chips 33** (2021) Aquabolt-XL slides: FILL, and the GEMV example.
3. **ANEMOS:** R. Medina et al., "Bank on Compute-near-Memory: Design Space
   Exploration of Processing-near-Bank Architectures", IEEE TCAD 43(11), 2024,
   DOI 10.1109/TCAD.2024.3442989, and its open SystemC model
   (github.com/gem5-X/cnm_framework, BSD-3). bankside adopts its opcode and
   operand-source values and uses it as a second reference model.

