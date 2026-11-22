# pcu_datapath

Stages S2 to S5 of the pipeline: source reads, SRF broadcast and ReLU, 16 lanes of FP16
multiply and add, the MAC accumulator read, and the S5 register-file and bank writes.
The spec is [doc/README.md](doc/README.md).

- **Requirement ID prefix:** `DP` (e.g. `[DP-1]`). Never reused.
- **Parent:** [top](../top/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/pcu_datapath.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
