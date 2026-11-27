---
name: diagrams
description: How to draw diagrams in bankside's docs - block diagrams, module hierarchy, datapaths, testbench architecture, flows, state machines, timing diagrams (pipeline stages, hazards, interface handshakes) and bitfields (instruction and register layouts). Use it whenever a spec, testplan or review page needs a picture, whenever you change one that has a diagram, and before opening a PR that touches any file under a doc/img/ folder. Covers the formats (Graphviz DOT and WaveDrom), the house conventions, and the render-and-check script. Not for simulation waveforms from a VCD/FST dump: those are the waves skill.
---

# Diagrams

bankside's diagrams are **text source in the repo**, rendered to SVG. Never
draw an image by hand or paste a screenshot of a drawing: an agent can't edit
it, a PR diff can't show what changed, and it goes stale silently. A source
file next to the prose it illustrates has none of those problems.

Two words, used consistently: a **timing diagram** is drawn by hand and shows
how something *should* behave (this skill). A **waveform** comes from a
simulation and shows how the RTL *did* behave (the `waves` skill, which draws
it with GTKWave). A review page can put the two side by side: the timing
diagram the spec promises, and the waveform of what the RTL did.

## Which format

| What you're drawing | Format | Source file |
|---|---|---|
| Block diagram: module hierarchy, datapath, register files, testbench architecture | Graphviz DOT | `<name>.dot` |
| Flow or state machine: control flow, FSM, test sequence | Graphviz DOT | `<name>.dot` |
| Timing diagram: pipeline stages, hazards and bypasses, interface handshakes | WaveDrom | `<name>.wave.json` |
| Bitfield: instruction formats, register layouts | WaveDrom bitfield | `<name>.reg.json` |

Before you write one, read the reference for its format; it has the house
template and worked examples:

- DOT: [references/dot.md](references/dot.md)
- WaveDrom timing diagrams and bitfields: [references/wavedrom.md](references/wavedrom.md)

## Where files go

- The source and its SVG sit in an `img/` folder beside the page that uses
  them: `src/<module>/doc/img/` for the spec, `src/<module>/rtl/doc/img/` and
  `src/<module>/dv/doc/img/` for review pages. You only add diagrams to the
  folders your role owns.
- Name files for what they show, in snake_case: `top_hierarchy.dot`,
  `mac_accumulator_bypass.wave.json`, `data_format.reg.json`. The SVG gets
  the same stem: `mac_accumulator_bypass.svg`.
- Embed the SVG in the Markdown, with a caption and a link to the source:

  ```markdown
  ![Back-to-back MACs into the same register use the accumulator bypass](img/mac_accumulator_bypass.svg)

  *Figure 3: back-to-back MACs into GRF_B[0]. Source: [mac_accumulator_bypass.wave.json](img/mac_accumulator_bypass.wave.json).*
  ```

## Conventions

These keep the pictures and the spec from disagreeing, which is the whole point
of drawing from source.

- **Names exactly as in the spec.** Block names, port names, signal names,
  register names and field names are copied from the spec text or the yaml,
  character for character. If a name in a diagram doesn't exist in the spec,
  either the spec is missing something (file a spec gap) or the diagram is
  wrong.
- **Each block says where it is specified.** A block in a block diagram carries
  its module's doc path as a second line, e.g. `pcu_alu\n(alu/doc)`, so a
  reader can find the spec for every box.
- **One idea per diagram.** A hierarchy diagram doesn't also show timing; a
  hazard timing diagram shows only the instructions that create the hazard.
  Several small diagrams beat one that needs a legend to read.
- **Timing diagrams are worked examples.** A spec timing diagram counts as
  proof only if its cycles match the rule it illustrates. Number the cycles,
  and say in the caption which requirement ID it demonstrates.
- **Bitfields match the yaml.** `src/top/doc/bankside_isa.yaml` is the source
  of truth for the encoding. Until a generator exists in `src/common/util/`,
  write `.reg.json` files by hand from the yaml, and check every bit range
  against it.

## Render, look, check

A diagram counts only if it renders and you have looked at it. Run everything
from the repo root:

```bash
# render one source, or every source under a folder, to SVG beside it
.venv/bin/python .claude/skills/diagrams/scripts/render.py src/top/doc/img/

# also write PNG previews to a scratch folder, then open them with Read
.venv/bin/python .claude/skills/diagrams/scripts/render.py --png <scratch>/previews src/top/doc/img/top_hierarchy.dot

# before a PR: every SVG exists and matches its source
.venv/bin/python .claude/skills/diagrams/scripts/render.py --check src/
```

- **Look at the PNG preview** (the Read tool shows images; it can't show SVG).
  Check that labels are readable, nothing overlaps, arrows go where you meant,
  and the cycle numbers are right. Fix the source and render again until it
  reads well. Never commit the PNGs; keep them in your scratch folder.
- The script treats Graphviz warnings as failures, since they almost always
  mean a typo in a node or port name.
- **In the PR:** commit the source and the SVG together, and run `--check` on
  the folders you touched before opening it. `--check` reports a missing SVG
  or one that no longer matches its source.

## When something won't render

- `dot` syntax error: the message gives the line. A common cause is an
  unescaped `{ } | < >` inside a record label, which are record syntax.
  Escape them with `\`.
- `dot warning: ... port ... unrecognized`: an edge names a port the record
  doesn't have. Usually a typo; check it against the label.
- Edges loop around a block and cross each other: the ports are on the wrong
  side. See "Blocks with ports" in the DOT reference.
- `invalid JSON`: WaveDrom sources must be strict JSON (double quotes, no
  trailing commas, no comments), so the script can give a clear error. Put
  explanations in the Markdown caption instead.
- WaveDrom draws something odd but doesn't fail: a `wave` string has a
  different length from the others, or `data` has fewer entries than the
  data cells (`=`, `2`–`9`) in the wave. Count them.
