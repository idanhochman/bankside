# fp16_add: RTL review pages

Owner: designer. Each page shows, with toy examples, that a feature of the RTL
works. Images go in `img/`; examples' harness in `examples/`. Each page names
the commit and the command that produced it.

| Page | Shows |
|---|---|
| [fp16_add.md](fp16_add.md) | The datapath, lint, and toy examples for every worked case of the spec and the double-rounding rows: exact sums, ties, the sticky bit, overflow, exact subnormal sums, signed zeros, a zero operand, Inf + (−Inf), NaN; a NumPy sanity sweep; a quick synthesis estimate |
