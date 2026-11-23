# fp16_add

One lane of the S4 add: a purely combinational IEEE 754 binary16 adder,
round to nearest even, subnormals in and out, an exact zero sum +0 (−0 only
for −0 + −0), NaN results 0x7E00, no flags.

- **Requirement ID prefix:** `FADD` (e.g. `[FADD-1]`). Never reused.
- **Parent:** [pcu_datapath](../pcu_datapath/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/fp16_add.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
