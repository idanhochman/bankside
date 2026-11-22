# pcu_regfile

A parameterised register file (depth, width, number of read ports) with one
write port, combinational write-through reads, a debug read port and no reset.
`top` uses it for the CRF, GRF_A, GRF_B, SRF_M and SRF_A. Spec: [doc/](doc/README.md).

- **Requirement ID prefix:** `RF` (e.g. `[RF-1]`). Never reused.
- **Parent:** [top](../top/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/pcu_regfile.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
