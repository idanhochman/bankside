# pcu_ctrl

Stage S1: the trigger, the PC, the loop state and the NOP counter, the CRF fetch
with the zero-slot JUMP, the bank read request, `err_illegal`, and the S1/S2
register that issues each slot to `pcu_datapath`. Spec: [doc/](doc/README.md).

- **Requirement ID prefix:** `CTRL` (e.g. `[CTRL-1]`). Never reused.
- **Parent:** [top](../top/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/pcu_ctrl.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
