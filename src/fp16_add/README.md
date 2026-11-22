# fp16_add

<!-- One or two lines: what this module does. The architect fills this in. -->

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
