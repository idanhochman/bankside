# common

Shared SystemVerilog: the package `bankside_pkg`, which holds the encoding constants of the ISA yaml and
the decoder's types. It has no module. Spec: [doc/](doc/README.md).

- **Requirement ID prefix:** `CMN` (e.g. `[CMN-1]`). Never reused.
- **Parent:** none

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/common.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
