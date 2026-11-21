# WaveDrom in bankside

For **timing diagrams** (`.wave.json`) and **bitfields** (`.reg.json`). Both
are strict JSON: double quotes, no comments, no trailing commas.

The examples below use names from spec draft 0.1. They show the format and
the style; in a real diagram, take every name from the current spec.

## Timing diagrams

### The format in brief

Each signal is `{"name": ..., "wave": ...}`. Each character of `wave` is one
cycle (with `"hscale"` stretching it):

| Char | Meaning |
|---|---|
| `p` | clock (first cycle; following `.` continue it) |
| `0` `1` | low, high |
| `x` | unknown / don't care |
| `z` | high impedance |
| `=` or `2`–`9` | a data value; its text comes from `data`, in order. Digits pick a fill colour |
| `.` | same as the previous cycle |
| `|` | a gap (cycles left out) |

`"data": ["A", "B"]` gives the texts of the data cells, in the order they
appear in `wave`. Count them: if there are fewer texts than data cells, the
diagram renders wrong without an error.

### House rules

- **Every wave string in a diagram has the same length.** One character per
  cycle, no exceptions.
- **The clock comes first**, named as in the spec (`clk`), wave `p` then dots.
- **Number the cycles**: `"head": {"tick": 0}` puts cycle numbers along the top.
  Spec text refers to cycles by these numbers ("the write in cycle 4").
- **Signal names exactly as in the spec.** Group related signals with
  `["group name", {...}, {...}]`.
- **Bus values in hex** with the spec's notation (`0x3C00`), or a symbolic name
  when the value doesn't matter (`D0`, `D1`).
- **Mark the events the caption talks about**: give a cycle a `node` letter
  (in the `node` string, at the same position as the cycle) and connect two
  markers with an `edge`, e.g. `"a~>b 4 cycles"`. Marker letters show on the
  diagram, so keep them single lowercase letters and name them in the caption.
  An arrow between two adjacent rows is short, so its text gets cramped:
  leave the edge unlabelled (`"a~>b"`) and explain it in the caption.
- **Stretch dense diagrams**: `"config": {"hscale": 2}` doubles the cycle
  width. Use it when data cells hold text (stage names, values).
- **Caption in the Markdown, not in the JSON.** The caption names the
  requirement ID the diagram demonstrates.

### Example: a bank read (an interface)

`bank_rd_data` is valid in the cycle after `bank_rd_en`:

```json
{
  "signal": [
    {"name": "clk",          "wave": "p....."},
    {"name": "trig_valid",   "wave": "010...", "node": ".a...."},
    {"name": "bank_rd_en",   "wave": "010..."},
    {"name": "bank_rd_data", "wave": "x.=x..", "data": ["D0"], "node": "..b..."}
  ],
  "edge": ["a~>b next cycle"],
  "head": {"tick": 0}
}
```

### Example: pipeline occupancy (a hazard)

One row per instruction, its stages as data cells. This is the clearest way to
show a hazard distance or a bypass: the reader sees which stages line up in
which cycle.

```json
{
  "signal": [
    {"name": "clk", "wave": "p........"},
    {"name": "MAC GRF_B[0] (P)", "wave": "=====x...", "data": ["S1","S2","S3","S4","S5"], "node": "....a...."},
    {"name": "MAC GRF_B[0] (C)", "wave": "x=====x..", "data": ["S1","S2","S3","S4","S5"], "node": "....b...."}
  ],
  "edge": ["a~>b"],
  "head": {"tick": 0},
  "config": {"hscale": 2}
}
```

Here P writes GRF_B[0] in S5 (cycle 4) and C reads its accumulator in S4 in
the same cycle, so the value comes through the bypass (the arrow a → b). A caption would say
which requirement ID this demonstrates, e.g. `[HAZ-2]`.

## Bitfields

A `.reg.json` file is `{"reg": [...], "config": {...}}`. The `reg` list goes
from bit 0 upward: the first entry is the least significant field.

| Key | Meaning |
|---|---|
| `bits` | field width |
| `name` | field name, exactly as in the yaml |
| `type` | optional number (2–7), a fill colour for grouping fields |

A field with no `name` draws as an unnamed gap: use that for unused bits.

### House rules

- **The yaml is the source of truth.** `src/top/doc/bankside_isa.yaml` gives
  each field as `[msb, lsb]`. Convert each to `bits = msb - lsb + 1`, list
  them from bit 0 up, and fill the unused ranges with unnamed entries. The
  widths must add up to the instruction width (32).
- One diagram per instruction format.
- `"config": {"bits": 32, "lanes": 1, "hspace": 1000, "fontsize": 12}` keeps a
  32-bit format on one line, with room for names in 1-bit fields.
- Until a generator exists in `src/common/util/`, write these by hand and check
  every range against the yaml after rendering.

### Example: the ALU format of draft 0.1

From the yaml: `opcode [31,28]`, `dst [27,25]`, `src0 [24,22]`, `src1 [21,19]`,
`src2 [18,16]`, `aam [15,15]`, `dst_idx [10,8]`, `src0_idx [6,4]`,
`src1_idx [2,0]`; bits 3, 7 and 14–11 unused.

```json
{
  "reg": [
    {"bits": 3, "name": "src1_idx"},
    {"bits": 1},
    {"bits": 3, "name": "src0_idx"},
    {"bits": 1},
    {"bits": 3, "name": "dst_idx"},
    {"bits": 4},
    {"bits": 1, "name": "aam"},
    {"bits": 3, "name": "src2"},
    {"bits": 3, "name": "src1"},
    {"bits": 3, "name": "src0"},
    {"bits": 3, "name": "dst"},
    {"bits": 4, "name": "opcode"}
  ],
  "config": {"bits": 32, "lanes": 1, "hspace": 1000, "fontsize": 12}
}
```
