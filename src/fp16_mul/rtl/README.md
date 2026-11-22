# fp16_mul: RTL

Owner: designer. DV reads only the filelist, and the RTL itself only when
debugging a failure.

- `fp16_mul.f`: the filelist opendv and synthesis read (Verilator `-F`
  syntax, paths relative to this file).
- One module per file, named after the module.
- `doc/`: review pages.
