# fp16_mul: RTL review pages

Owner: designer. Each page shows, with toy examples, that a feature of the RTL
works. Images go in `img/`; examples' harness in `examples/`. Each page names
the commit and the command that produced it.

| Page | Shows |
|---|---|
| [fp16_mul.md](fp16_mul.md) | The datapath, lint, and toy examples for every worked case of the spec: exact products, ties, subnormals, overflow, zero × Inf, NaN; a NumPy sanity sweep; the full-flow PPA |
