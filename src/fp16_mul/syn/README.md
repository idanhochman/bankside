# fp16_mul: synthesis

Owner: designer. `ppa.yaml` is the last full synthesis run (ORFS on ASAP7,
written by the synth skill's tool), and this file says what its numbers mean
and what they compare against. A `constraint.sdc` or `orfs.mk` here overrides
the common ones, only when this module needs it (say why below). Full run
output is not committed.

## What was run

```
.claude/skills/synth/scripts/synth fp16_mul
```

- **Commit:** `83ea73a` (`clean: true`). The RTL (`rtl/fp16_mul.sv`,
  `rtl/fp16_mul.f`) is unchanged since `e844553`, the commit of #71.
- **Flow:** ORFS `26Q4-615-g8ba54e723`, ASAP7, the full flow (synthesis,
  floorplan, placement, CTS, routing, finish), 461 s.
- **Settings:** the common `constraint.sdc` and `orfs.mk` (40% utilisation,
  0.60 placement density). fp16_mul has no `syn/constraint.sdc` or
  `syn/orfs.mk` of its own; it needs none.
- **Clock:** 3333 ps ([TOP-ARCH-3], 300 MHz). fp16_mul has no `clk`
  ([FMUL-3]), so it is timed against a virtual clock with no input or output
  allowance, and the number that matters is its delay.

## Results

| Measure | Value |
|---|---|
| Area, placed and routed (`cells`) | 149.2 µm² |
| Area after synthesis | 147.3 µm² |
| Die (40% utilisation) | 448.9 µm² |
| Cells | 1561 (1451 after synthesis, 48 timing buffers, 0 flops) |
| Delay, `a`/`b` → `p` | 1238.8 ps |
| Slack against 3333 ps | 2094.2 ps |
| DRC violations | 0 |
| Max slew / cap / fanout violations | 0 / 0 / 0 |
| Power | 0.128 mW, OpenSTA's default activity (10% toggle): an indication, not a measurement |

ORFS's two equivalence checks (after repair, `4_rsz_lec_check`, and on the
final netlist, `6_final_lec_check`) both report the circuits identical.

**The worst path** runs from `b[14]` to `p[8]`: an exponent bit, through the
OR that makes the hidden bit, the 11 × 11 significand multiplier, the
leading-zero count `lz`, the normalising shift, the rounding increment `inc`,
and the carry of `mag_round` into `p[8]`. That is the whole datapath in
series, as the structure on the review page predicts
([`rtl/doc/fp16_mul.md`](../rtl/doc/fp16_mul.md#structure)).

**Against the quick run** at `e844553` (synthesis only, no wires): 1018.4 ps
and 147.3 µm². Placement and routing add 220 ps (22%) of wire and buffer
delay and 1.9 µm² of buffers.

## Against [FMUL-11]

[FMUL-11] sets no delay budget for the unit beyond the clock period. The
unit's path in the pipeline is the S3 multiply: the S2/S3 register's
clock-to-output, then `fp16_mul`, then the choice of *x* ([DP-10]), then the
S3/S4 register's setup ([DP-17]), all within 3333 ps. fp16_mul takes 1238.8 ps of that,
37% of the period, which leaves 2094 ps for the register and the
multiplexer. It fits with a wide margin; there is no finding. That whole path
is measured when `pcu_datapath` is synthesized.

The multiplier is not on the one-cycle accumulator loop ([TOP-HAZ-2],
[TOP-HAZ-4]), which goes through `fp16_add`, so this delay does not bear on
that loop.

The 3333 ps target is relaxed, so the tools did not push for speed: the
delay describes a relaxed circuit, not the fastest this RTL could go.

[TOP-ARCH-3]: ../../top/doc/theory_of_operation.md#architecture
[TOP-HAZ-2]: ../../top/doc/theory_of_operation.md#hazards
[TOP-HAZ-4]: ../../top/doc/theory_of_operation.md#hazards
[FMUL-3]: ../doc/README.md#behaviour
[FMUL-11]: ../doc/README.md#timing
[DP-10]: ../../pcu_datapath/doc/README.md#s3-and-s4-the-lanes
[DP-17]: ../../pcu_datapath/doc/README.md#timing
