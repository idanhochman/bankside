# util

Owner: the user. Agents run these tools but never change them.

- `new_module.py`: creates `src/<name>/` from `template/`. Run by the
  architect:

      python3 src/common/util/new_module.py fp16_mul --prefix FMUL

  `--parent` (default `top`) names the module whose doc describes how the new
  one connects; use `--parent none` for `top` and `common`. The prefix is the
  module's requirement ID prefix and is checked against every other module's.
  Nothing is ever overwritten; `--dry-run` lists the files first.
- `template/`: what every module starts as. `{{module}}`, `{{PREFIX}}` and
  `{{parent_line}}` are filled in by the script.

A new module isn't added to the root `opendv.yaml` until it has a test: opendv
refuses a target with no test, and that breaks the whole project file. DV adds
it.
