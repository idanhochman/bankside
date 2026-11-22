# pcu_decode: RTL

Owner: designer. DV reads only the filelist, and the RTL itself only when
debugging a failure.

- `pcu_decode.f`: the filelist opendv and synthesis read (Verilator `-F`
  syntax, paths relative to this file).
- One module per file, named after the module.
- `doc/`: review pages.
