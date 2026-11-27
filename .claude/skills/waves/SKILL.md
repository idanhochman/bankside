---
name: waves
description: How to read and show simulation waveforms from opendv's dump.fst - a text table of signal values per clock cycle for debugging, and GTKWave images with labelled markers for review pages. Use it whenever you debug a failing or suspicious test, need to know what a signal did in a run, put a waveform on a review page, or open a PR that touches a *.waves.yaml or its PNG. Covers the waves tool (.claude/skills/waves/scripts/waves), the .waves.yaml spec format and the check before a PR. Not for hand-drawn timing diagrams of how something should behave: those are the diagrams skill.
---

# Waves

A **waveform** shows how the RTL *did* behave in a simulation. It comes from
the `dump.fst` that `opendv run` writes (the sim skill). A **timing diagram**
shows how something *should* behave and is drawn by hand (the diagrams skill).
Never draw a waveform by hand or edit one: it is proof only because a tool
drew it from a real run.

One tool does both jobs below, from the repo:

```bash
.claude/skills/waves/scripts/waves list  <dump.fst>
.claude/skills/waves/scripts/waves table <dump.fst> --signals a,b,c [--clock clk] [--from 50ns] [--to 260ns]
.claude/skills/waves/scripts/waves png   <name>.waves.yaml ...
.claude/skills/waves/scripts/waves png   --check <folder> ...
```

It runs in its own container (GTKWave on a virtual display), built on first
use; the first call takes a few minutes. Don't call `gtkwave`, `fst2vcd` or
`docker` yourself.

## Reading a run: tables

You can't look at a waveform viewer, so read the dump as text:

```bash
src/common/util/opendv run fp16_mul:test_ties --seed 2147      # writes dump.fst
.claude/skills/waves/scripts/waves list sim/fp16_mul/test_ties/build_1/dump.fst
.claude/skills/waves/scripts/waves table sim/fp16_mul/test_ties/build_1/dump.fst \
    --signals valid_in,a,b,valid_out,result --from 400ns --to 520ns
```

```
cycle  time(ns)  valid_in       a       b  valid_out  result
   40       410         1  0x3C00  0x3C00          0       x
   41       420         0  0x3C00  0x3C00          1  0x4000
```

- One row per rising edge of the clock (`--clock`, default `clk`), with each
  signal's value **just before the edge**: what a flip-flop samples there.
  Cycle numbers count rising edges from the start of the run, so they are the
  same whatever window you ask for.
- **No clock** (a combinational unit such as `fp16_mul`, whose dump has no
  `clk`; or `--clock none`): one row per time at which any listed signal
  changes, with the values once that time has settled. Each row is then one
  stimulus and its result:

  ```
  time(ns)       a       b       p
        10  0x7C01  0x3C00  0x7E00
        20  0xFE00  0x0000  0x7E00
  ```
- Buses are hex (`0x3C00`), bits `0`/`1`; `x` or `z` means some bit is.
- A signal is named by its full path from `waves list`, or by any ending of it
  that is unique (`result`, `u_round.result`). `waves list` skips cocotb's
  `$rootio` copy of the toplevel's ports.
- Start wide (a few cycles around the failure time the log gives), then narrow.
  When you report a failure, paste the table rows that show it.

## Showing a run: review-page images

A review page's waveform is a GTKWave image drawn from a spec file that sits
next to it in the page's `img/` folder:

```yaml
# src/fp16_mul/dv/doc/img/ties.waves.yaml -> ties.png
dump: sim/fp16_mul/test_ties/build_1/dump.fst       # from the repo root
run: src/common/util/opendv run fp16_mul:test_ties --seed 2147
signals:
  - clk
  - valid_in
  - a
  - b
  - result
  - {name: result, format: bin}                     # hex (default), dec, signed, bin
from: 400ns
to: 520ns
markers:
  - {at: 410ns, label: tie}
  - {at: 420ns, label: even}
width: 1200                                         # pixels, optional
```

```bash
src/common/util/opendv run fp16_mul:test_ties --seed 2147
.claude/skills/waves/scripts/waves png src/fp16_mul/dv/doc/img/ties.waves.yaml
```

The image is a PNG: it is GTKWave's own window, a picture, so it can't be an
SVG (the "SVG where the tool allows" rule in `CLAUDE.md` doesn't apply).
Then **open the PNG with Read and look at it** before you use it: the window
shows what the caption claims, the markers sit on the events, nothing is cut
off. Fix the spec and draw again until it does.

- **`run`** is the exact command that writes the dump, with the seed. It is
  what makes the image reproducible; the page quotes it too.
- **Signals** in the order you want them, clock first, named as in the spec.
  Only the ones the page talks about: five to ten, not the whole module.
- **The window** (`from`, `to`) covers the events and a few cycles either side.
  It can't run past the end of the simulation: GTKWave stops there.
- **Markers** go on the events the caption talks about. They are drawn as
  lettered lines A, B, C... in order, with the label above. Keep labels to a
  word or two: labels of nearby markers overlap. Explain them in the caption.
- Embed it like any figure, with the spec and the command in the caption:

  ```markdown
  ![A tie rounds to even](img/ties.png)

  *Figure 2: [FMUL-6], a tie rounds to even. A: the product's tie bits; B: the
  result, 0x4000. Source: [ties.waves.yaml](img/ties.waves.yaml), at commit
  `<hash>`: `src/common/util/opendv run fp16_mul:test_ties --seed 2147`.*
  ```

## Before a PR

Commit each `.waves.yaml` with its PNG, and check the folders you touched:

```bash
.claude/skills/waves/scripts/waves png --check src/fp16_mul/dv/doc/
```

`--check` redraws every image into a scratch file and compares the bytes, so
it needs the dumps: if one is missing it prints the `run` command to recreate
it. `STALE` means the PNG no longer matches its spec or its run: redraw it.
A change to the RTL or the test that changes the run makes the page's images
stale; regenerate them in the same PR (`CLAUDE.md`, Review pages).
