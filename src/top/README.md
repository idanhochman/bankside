# top

The whole bankside unit: one near-bank FP16 SIMD compute unit serving a pair of DRAM banks. Its spec is in [doc/](doc/README.md), with the ISA in [doc/bankside_isa.yaml](doc/bankside_isa.yaml).

- **Requirement ID prefix:** `TOP` (e.g. `[TOP-1]`). Never reused.
- **Parent:** none

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/top.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
