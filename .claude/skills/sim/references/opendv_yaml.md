# opendv.yaml in bankside

Two kinds of file, both named `opendv.yaml`, both DV's. Paths inside a file are
relative to that file. opendv rejects an unknown key and names the one you
probably meant.

## The root project file

```yaml
version: 1
project: bankside
targets:                     # every module, listed as soon as it exists
  - src/fp16_mul
  - src/fp16_add
defaults:
  seeds: 8                   # random seeds per test in a regression
  waves: false               # FST dumps in regress (run always dumps)
  code_cov: false
  sim:
    build_args: [--x-initial, unique]       # random-capable initial values
    plusargs: [+verilator+rand+reset+2]     # randomise them from the seed ([TOP-ARCH-9])
```

## A module's target file

```yaml
version: 1
name: fp16_mul               # the target's name on the command line
toplevel: fp16_mul           # the RTL module at the top
rtl:
  filelist: rtl/fp16_mul.f   # the designer's; nested lists with -F
  parameters: {}             # toplevel parameters, passed as -G
dv:
  tests: [test_*]            # cocotb modules in dv/tests/ (globs allowed)
  pythonpath: [../common/dv] # shared DV code from other folders
coverage:
  functional: coverage.yml   # the file tests write with cocotb-coverage
seeds: 20                    # this target's seeds, instead of the default
waves: true                  # this target's waves, instead of the default
sim:
  build_args: []             # added after the project's
  plusargs: []               # added after the project's
```

Only `toplevel` and `rtl.filelist` are required. `dv/env/` goes on the
Python path by itself when it exists.

## Precedence

- `seeds` and `waves`: the command line, then the target, then `defaults`.
- `sim.build_args` and `sim.plusargs`: the project's, then the target's,
  both used.
