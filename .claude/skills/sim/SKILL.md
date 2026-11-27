---
name: sim
description: How to lint, build and simulate bankside's RTL - Verilator lint, cocotb tests, regressions, seeds and replays, waveform dumps, random power-up values - through opendv and bankside's pinned wrapper src/common/util/opendv. Use it whenever you lint or simulate anything, run or write a cocotb test, reproduce or report a failure, set up a module's opendv.yaml or the designer's toy harness, or need a dump.fst for a review page. Never call docker or an opendv on your PATH; this skill says how instead. Viewing and drawing waveforms is the waves skill.
---

# Simulation

bankside simulates through **opendv** (Verilator + cocotb, in a Docker image).
Always run it as **`src/common/util/opendv`**, from anywhere inside the repo
(with a relative path from a subfolder, e.g. `../common/util/opendv`):

- It pins the opendv release bankside is tested with, so every role, CI and
  every rerun of a review page use the same Verilator and cocotb.
- It mounts the repo and nothing else, with the user-only paths read-only.

Don't run `docker`, `podman` or an `opendv` from your PATH, and don't set
`OPENDV_IMAGE`: the guard refuses them. If the wrapper or opendv can't do
something you need, say so in your report (opendv is the user's, see the
Rules in `CLAUDE.md`). Don't work around it.

`src/common/util/opendv help` and `opendv help <command>` print the full
options.

## The project

- The root `opendv.yaml` (DV's) lists every module as a target:
  `targets: [src/fp16_mul, src/fp16_add, ...]`. A new module is listed at once.
- Each module's `src/<module>/opendv.yaml` (DV's) names its toplevel, its
  filelist (`rtl/<module>.f`, the designer's) and its tests (`dv/tests/`,
  `test_*.py`). Keys and examples: [references/opendv_yaml.md](references/opendv_yaml.md).
- A target is named by its folder name: `fp16_mul`, `fp16_mul:test_ties`.
  Standing inside `src/fp16_mul/`, a bare test name or no name means that
  target.
- Until a module has tests, `lint` checks it, `regress` skips it and `run`
  says it has none.

## The four commands

```bash
src/common/util/opendv targets                        # the targets, toplevels and tests
src/common/util/opendv lint fp16_mul                  # Verilator -Wall on the RTL, no tests needed
src/common/util/opendv run fp16_mul:test_ties         # ONE test, one random seed, waves on
src/common/util/opendv regress fp16_mul --seeds 20    # many tests x many seeds, the dashboard
```

**`lint`** runs `verilator --lint-only -Wall` on the target's filelist and
toplevel, with its parameters and `sim.build_args`. It prints the warnings,
then `fp16_mul: clean` or the counts, and exits 1 on any warning. **Clean
means zero warnings.** An accepted warning is waived in the RTL, narrowly,
with the reason next to it:

```systemverilog
/* verilator lint_off UNUSEDSIGNAL */
// [FMUL-4]: only the top 11 bits of the product feed the rounding.
logic [21:0] product;
/* verilator lint_on UNUSEDSIGNAL */
```

Never turn a warning off for a whole file or the whole project.

**`run`** is for debugging one test. It builds, runs one seed and keeps
everything in `sim/<target>/<test>/build_1/` at the repo root: `sim.log`,
`results.xml`, `dump.fst`, and `build.log` for compile errors. It ends with
`PASS` or `FAIL`, the seed, and a `rerun:` command. Running it again
overwrites `build_1`; `--tag 2` keeps it and builds afresh in `build_2`.
`--no-waves` skips the dump.

**`regress`** is the real check: every selected test, once per seed, each in
its own simulator process from power-on. Name targets, `target:test` (globs
allowed, quoted: `'fp16_mul:test_sub*'`) or `--all`. Results go to
`regress/<timestamp>/`, with a dashboard (`index.html`) and, for every
failure, its seed, log and a one-test `repro:` command. Waves are off by
default here (`--waves` turns them on); `--code-cov` adds line and toggle
coverage.

`sim/` and `regress/` are git-ignored. Never commit them.

## Seeds

Every test is random by default, and the seed fixes everything: cocotb's
Python `random` and the RTL's own randomness (`$urandom`, random power-up
values) both follow it.

- **Every failure is reported with its seed and the command that replays
  it**, exactly as opendv printed it, with `src/common/util/` in front:
  `src/common/util/opendv run fp16_mul:test_ties --seed 2147`. A bug issue
  without that line can't be reproduced.
- **Replay before you fix, and after.** A fix is done when the failing seed
  passes and a fresh regression of the same tests passes.
- `regress --master-seed N` replays a whole regression; `--seed-list 7 99`
  runs chosen seeds.
- A test must never seed itself from the clock or pick its own seed: use
  `random` (already seeded) or read `OPENDV_SEED` from the environment.

## Power-up values

[TOP-ARCH-9]: an entry never written since reset holds an unpredicted
power-up value, which may differ from one power-up to the next. To simulate
that, Verilator must start registers random, from the seed, instead of zero.
DV sets it in the root `opendv.yaml`, for every target:

```yaml
defaults:
  sim:
    build_args: [--x-initial, unique]       # build: random-capable initial values
    plusargs: [+verilator+rand+reset+2]     # run: randomise them from the seed
```

With this, a test that reads a never-written entry sees a different value
for each seed, and the same value when the seed is replayed. A design that
works only because registers start at zero fails here, as it should.

## By role

**Designer.**
- Lint your module before every PR, and say in the PR that it's clean (or
  list the waivers). M2 and later need lint-clean RTL.
- Your toy examples (see `designer.md`) run as a small opendv project of their
  own, in `src/<module>/rtl/doc/examples/`, so they never touch DV's tests
  (opendv uses the nearest project file):

  ```
  rtl/doc/examples/
    opendv.yaml              version: 1, project: <module>_examples, targets: [toy]
    toy/opendv.yaml          name: <module>_examples, toplevel: <module>,
                             rtl: {filelist: ../../../<module>.f},
                             dv: {dir: ., tests: ['example_*']}
    toy/tests/example_<scenario>.py
  ```

  Run them from `toy/`: `../../../../../common/util/opendv run example_hazard`.
  The `dump.fst` is your review page's waveform.
- You may run DV's tests to reproduce a bug DV filed: paste its repro
  command. Running a test doesn't need you to read it; reading it follows the
  rules in `designer.md`.

**DV.**
- You own the `opendv.yaml` files and the root one. Add each new module to
  the root `targets` as soon as it exists.
- Tests are `dv/tests/test_<name>.py` (one cocotb module per file); shared
  code is in `dv/env/`, and code shared across modules goes on
  `dv.pythonpath`.
- Before a PR, run the regression of the targets you touched with enough
  seeds to mean something (at least the configured default), and put the
  command, master seed and result in the PR.
- A review page's waveform comes from `run` (waves are on): name the commit
  and paste the exact `run ... --seed N` command on the page, so it can be
  regenerated.

## When something goes wrong

- **`BUILD ERROR`**: the Verilator messages follow; the full compile output is
  in `build.log`. A missing file usually means the filelist is wrong; the
  filelist is the designer's.
- **`no tests yet`**: the target's `dv/tests/` has no `test_*.py`.
- **`unknown target`**: name it by its folder (`fp16_mul`), or list them with
  `targets`.
- **`run it from inside the bankside repo`**: `cd` into the repo first.
- **A test passes alone but fails in `regress`**: it depends on state from
  outside its own simulator run, or on the seed. Replay the failing seed with
  `run`.
- **The guard refused a command**: you ran `docker` or `opendv` directly. Use
  the wrapper.
