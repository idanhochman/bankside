# Milestones

The plan for bankside, as a sequence of milestones. A milestone is a set of
tasks with an exit condition, not a time box. It closes when all its tasks are
done and the maintainer has reviewed the ones they chose to review.

- **One at a time.** Only the open milestone's tasks are worked on. The next
  one opens when the current one closes.
- **This file is the plan; GitHub is the status.** Each milestone here is
  filed as a GitHub milestone whose description links to its section below.
  Tasks, progress and what's blocked live on GitHub, not here.
- **Who changes it:** the maintainer sets the milestones and creates them on
  GitHub. The PM updates this file when the maintainer asks, and never adds,
  drops or reorders a milestone itself.

| # | Milestone | Roles |
|---|---|---|
| M1 | [Architecture closure](#m1-architecture-closure) | architect, PM |
| M2 | [FP16 units](#m2-fp16-units) | designer, DV |
| M3 | [Verification infrastructure](#m3-verification-infrastructure) | DV |
| M4 | [PCU core](#m4-pcu-core) | designer, DV, architect |
| M5 | [v1 verification closure](#m5-v1-verification-closure) | DV, designer |
| M6 | [v1 release](#m6-v1-release) | designer, PM, maintainer |
| v2 | [The PIM side](#v2-the-pim-side) | to be planned |

## M1: Architecture closure

**Goal:** a spec the designer and DV can build v1 from without asking anyone.

**Done when:**
- spec draft 0.1 is moved into `src/top/doc/` (prose and the ISA yaml), and
  its open choices are settled;
- the split into v1 modules is decided and described in `src/top/doc/`;
- each v1 module exists (created with `new_module.py`) and has its doc, with
  its ports, timing and requirement IDs;
- no spec-gap issue for v1 is open.

## M2: FP16 units

**Goal:** the FP16 multiplier and adder, proven correct on their own. The
first full designer → DV → review cycle, on small modules with a clean
interface.

**Done when:**
- both units are lint-clean and synthesize;
- DV's sweeps match NumPy `float16` bit-exactly, including subnormals,
  NaN/Inf and round-to-nearest-even ties;
- each unit has review pages on both sides (`rtl/doc/`, `dv/doc/`);
- each unit has a first PPA number (area and timing on ASAP7).

## M3: Verification infrastructure

**Goal:** the system-level checks exist before the core RTL needs them.

**Done when:**
- the bankside reference model and the assembler exist, unit-tested against
  plain NumPy maths;
- ANEMOS runs as the second reference model, with its intended differences
  listed;
- the system testplan (`src/top/dv/`) maps every top-level requirement ID to
  its tests, or lists it as uncovered;
- CI runs the regression on every PR.

## M4: PCU core

**Goal:** all nine instructions working in the RTL.

**Done when:**
- the core is brought up in this order, each step with directed tests per
  instruction passing against the reference model: NOP/EXIT, the program
  counter, MOV/FILL, ADD/MUL, MAC/MAD (with the accumulator bypass), JUMP;
- each step has its review pages;
- spec gaps found on the way are settled in the spec.

## M5: v1 verification closure

**Goal:** v1 shown correct by all three independent checks.

**Done when:**
- the GEMV, vector add, vector mul and ReLU kernels pass against the
  reference model (bit-exact), ANEMOS (differences masked) and NumPy maths
  (within an FP16 error bound);
- constrained-random tests run, with operand-combination coverage at a target
  set when this milestone opens.

## M6: v1 release

**Goal:** v1 published, with claims that hold.

**Done when:**
- a full OpenROAD run on ASAP7, with power from GEMV switching activity;
- the results are compared against the published unit figures (gate count
  from ISCA 2021, area split from SideDRAM), with the caveats stated;
- the README states the v1 claims;
- `v1.0` is tagged.

## v2: The PIM side

A placeholder, to be split into milestones once v1 is done: a timing-correct
HBM2 command driver in the testbench, AAM, the SB/AB/AB-PIM mode switching,
and the sustained-throughput check.
