---
name: synth
description: How to synthesize a bankside module and measure its PPA (area, timing, power) with OpenROAD-flow-scripts (Yosys + OpenROAD) on the ASAP7 7 nm predictive PDK, through the synth tool (.claude/skills/synth/scripts/synth). Use it whenever you check that RTL synthesizes, need a module's area, delay, slack or maximum frequency, update or review a syn/ppa.yaml, or open a PR that changes RTL (its PPA must be current). Covers the quick and full runs, the clock budget, what syn/ holds, and how to read and report the numbers.
---

# Synthesis and PPA

bankside's PPA comes from **ORFS** (OpenROAD-flow-scripts: Yosys, then
OpenROAD's floorplan, placement, clock tree, routing and reports) on **ASAP7**,
a free predictive 7 nm process: realistic numbers anyone can reproduce, not
a real foundry's. One tool runs it, one module at a time:

```bash
.claude/skills/synth/scripts/synth fp16_mul --quick     # ~1 min: synthesis + timing before placement
.claude/skills/synth/scripts/synth fp16_mul             # minutes: the full flow, writes syn/ppa.yaml
.claude/skills/synth/scripts/synth fp16_mul --clock-ps 600   # explore another clock (not saved)
```

It runs ORFS's own image, pinned, with the repo mounted read-only; the first
call pulls the image (6.8 GB, several minutes). Don't call `yosys`,
`openroad`, `make` in ORFS or `docker` yourself.

## What it reads

- **The module's filelist**, `rtl/<module>.f`: the same list opendv simulates,
  so synthesis and simulation see the same sources. Files, `-F` nested lists,
  `+incdir+` and `+define+`. The toplevel comes from the module's
  `opendv.yaml`.
- **The common settings** next to the tool, which every module uses:
  `constraint.sdc` (the clock, below) and `orfs.mk` (ASAP7, 40% utilisation,
  0.60 placement density).
- **Exceptions**: a module may have its own `syn/constraint.sdc` (replaces the
  common one) or `syn/orfs.mk` (overrides the common settings). Only when it
  really needs them, and its `syn/README.md` says why. `ppa.yaml` records
  which were used.

## The clock

[TOP-ARCH-3]: one clock, 300 MHz, so every module is synthesized at
**3333 ps**.

- **A module with a `clk` port** gets a real clock; its other inputs and its
  outputs get 20% of the period each for the neighbours' registers and
  wires. It reports setup and hold slack and the maximum frequency.
- **A combinational module** (no `clk`, like `fp16_mul` and `fp16_add`) is
  timed against a virtual clock with no allowance, so it reports its own
  **delay**: the longest input-to-output path, in ps. Its budget is set by
  its parent's spec ([FMUL-11], [FADD-11]: the period minus the registers and
  multiplexers around it); that whole loop is checked when the parent is
  synthesized. Until then, compare the delay against the budget the spec
  describes, and if it plainly can't fit, that's a finding for the architect,
  not a register to add.
- 3333 ps is easy for small units, so the tools don't push for speed: the
  numbers describe a relaxed circuit. `--clock-ps` explores a tighter target;
  those runs are never saved, and `syn/ppa.yaml` is always at 3333 ps.

## The two runs

- **`--quick`** while you work: synthesis and a timing estimate before
  placement (no wire delays). About a minute. It prints the numbers and saves
  nothing.
- **The full flow** for a PR: placement, clock tree, routing, reports. A few
  minutes for a unit, longer for big modules. It writes `syn/ppa.yaml`.

**Commit the RTL first.** A number must come from committed RTL, so anyone can
reproduce it. `ppa.yaml` records the commit, and `clean: false` if the RTL,
the module's `syn/` or this skill had uncommitted changes; never quote or
commit a `clean: false` result. The order is: commit the RTL, run the full
flow, commit `ppa.yaml`.

## syn/

```
src/<module>/syn/
  README.md        the designer's notes: what the numbers mean, what they compare against
  ppa.yaml         written by the tool after a full run; never edit it
  constraint.sdc   only if the module needs its own clock constraint
  orfs.mk          only if the module needs its own flow settings
```

The full run's outputs (reports, layout pictures, netlists, about 70 MB) stay
in `synth/<module>/` at the repo root, git-ignored. Look there for detail:
`reports/.../final_worst_path.webp`, `final_routing.webp` (open them with
Read), `reports/.../6_finish.rpt`, and `flow.log` when a run fails.

## Reading ppa.yaml

```yaml
# a combinational 16x16 integer multiplier, for scale
kind: combinational        # or clocked
clock_ps: 3333
area_um2:
  cells_after_synth: 120.6 # the logic as synthesized
  cells: 127.2             # after placement and routing, with timing buffers
  die: 375.0               # the block's outline at 40% utilisation
cells: {after_synth: 1296, total: 1451, flops: 0, timing_buffers: 64}
timing:
  setup_slack_ps: 2747.1   # negative = the clock is missed
  delay_ps: 585.9          # combinational: the longest path
  # clocked instead: hold_slack_ps, fmax_mhz
power_mw: {total: 0.09, activity: default}
drc_violations: 0
```

- **Area**: quote `cells` (placed and routed), in µm².
- **Timing**: a combinational unit's `delay_ps`; a clocked module's
  `setup_slack_ps` at 3333 ps and its `fmax_mhz`. Negative slack, a hold
  violation or `drc_violations` above 0 is a problem to fix or report, never
  to leave out.
- **Power** is OpenSTA's default guess (`activity: default`: inputs toggling on
  10% of cycles), not a measurement. Quote it only as an indication, labelled
  as such. Power from a simulated kernel's real switching comes in M6.

In the PR and the module's `syn/README.md`: area, delay or slack and fmax,
the clock, the commit and the ORFS version (all from `ppa.yaml`), and what
they compare against.

## When something goes wrong

- **`lists no source file yet`**: the filelist is empty.
- **`the flow failed`**: the end of `flow.log` follows; the step that failed
  is in its name (`1_synth`, `3_place`, `5_route`...). A synthesis error
  usually means RTL that Verilator accepts but synthesis doesn't (an
  `initial` block, a non-constant loop): run `opendv lint` and fix the RTL.
- **Routing fails or takes very long** on a big module: lower its utilisation
  in its own `syn/orfs.mk` (e.g. `export CORE_UTILIZATION = 30`) and say why
  in its README.
