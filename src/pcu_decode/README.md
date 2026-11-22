# pcu_decode

Combinational instruction decoder: one 32-bit word to its illegal flag, its bank read and the
decoded instruction `dec_instr_t` that `pcu_ctrl` issues to `pcu_datapath`. Spec: [doc/](doc/README.md).

- **Requirement ID prefix:** `DEC` (e.g. `[DEC-1]`). Never reused.
- **Parent:** [pcu_ctrl](../pcu_ctrl/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/pcu_decode.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
