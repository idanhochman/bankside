# util

Owner: the user. Agents run these tools but never change them.

- `new_module.py`: creates `src/<name>/` from `template/`. Run by the
  architect:

      python3 src/common/util/new_module.py fp16_mul --prefix FMUL

  `--parent` (default `top`) names the module whose doc describes how the new
  one connects; use `--parent none` for `top` and `common`. The prefix is the
  module's requirement ID prefix and is checked against every other module's.
  Nothing is ever overwritten; `--dry-run` lists the files first.
- `opendv`: runs [opendv](https://github.com/idanhochman/opendv) (Verilator +
  cocotb) in its Docker image, pinned to the release bankside is tested with
  (`OPENDV_VERSION`). Use it instead of an `opendv` on your PATH, from anywhere
  inside the repo:

      src/common/util/opendv run fp16_mul:test_basic --seed 3

  It mounts this repo and nothing else, and refuses to run outside it.
  Agents reach Docker only through it (the `sim` skill).
- `template/`: what every module starts as. `{{module}}`, `{{PREFIX}}` and
  `{{parent_line}}` are filled in by the script.

DV adds each new module to the root `opendv.yaml` right away. Until it has a
test, `opendv lint` checks it and `opendv regress` skips it.
