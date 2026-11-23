# fp16_mul

One lane of the S3 multiply: a purely combinational IEEE 754 binary16 multiplier,
round to nearest even, subnormals in and out, NaN results 0x7E00, no flags.
`pcu_datapath` has 16. Spec: [doc/](doc/README.md).

- **Requirement ID prefix:** `FMUL` (e.g. `[FMUL-1]`). Never reused.
- **Parent:** [pcu_datapath](../pcu_datapath/doc/), whose doc describes how this module connects

| Path | What it holds | Owner |
|---|---|---|
| `doc/` | The spec: ports, timing, behaviour, requirement IDs | architect |
| `rtl/` | The RTL and its filelist `rtl/fp16_mul.f`; review pages in `rtl/doc/` | designer |
| `syn/` | Synthesis scripts and the PPA summary | designer |
| `dv/` | The testplan (`dv/README.md`), `env/`, `tests/`; review pages in `dv/doc/` | DV |
| `opendv.yaml` | The verification target | DV |

Created with `src/common/util/new_module.py`.
