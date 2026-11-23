#!/usr/bin/env python3
"""Checks for the common doc (src/common/doc/README.md): bankside_pkg's constants.

The doc's constant tables ([CMN-4] to [CMN-7]) are read back from the doc and
checked against two sources the doc does not control:

  1. bankside_isa.yaml, through the top spec's own checker
     (src/top/doc/examples/check_isa.py, which parses the yaml and checks it
     against the programmer's guide): every width, opcode, operand code and
     field position in the doc equals the yaml, every yaml entry has its row,
     and no row is extra. The reserved codes are the yaml's gaps.
  2. pcu_decode's model (src/pcu_decode/doc/examples/dec_check.py, which runs
     its own checks first): the operand constants are the model's `opnd_e`
     codes and DEC-12's rows; the opcode of every legal word decodes to the
     dec_op_e value of the same name (case B); the field constants, applied to
     words, give the fields the model decodes (case C).
  3. The SystemVerilog block in the doc ([CMN-8]) is exactly what this script
     renders from the yaml, and, if Verilator is on the PATH, it lints clean
     with -Wall inside a package file named bankside_pkg.sv, with a module
     that uses every constant. The enum-versus-localparam case of the doc's
     "Choices weighed" is run through Verilator too (case D).
  4. The package's contents table ([CMN-2]) names exactly the items of the
     doc's tables and of DEC-11, DEC-12 and DEC-14, and its links resolve.

Run from the repo root (about a minute, most of it dec_check.py):
    .venv/bin/python src/common/doc/examples/pkg_check.py
Exits non-zero if a check fails or a table or block differs from the doc.
"""
import contextlib
import io
import random
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOC = HERE.parent / "README.md"
SRC = HERE.parents[2]
SPEC = DOC.read_text()
FLAT = re.sub(r"\s+", " ", SPEC)       # prose with line breaks folded
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def done(group):
    if failures:
        print(f"FAIL {group}")
        for f in failures[:40]:
            print("   ", f)
        sys.exit(1)
    print(f"ok   {group}")


def load(path):
    """Run another spec script quietly; return its globals."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            return runpy.run_path(str(path))
    except SystemExit as e:
        print(out.getvalue())
        sys.exit(f"FAIL {path.name} exited with {e.code}")


isa = load(SRC / "top" / "doc" / "examples" / "check_isa.py")
dec = load(SRC / "pcu_decode" / "doc" / "examples" / "dec_check.py")
Y = isa["isa"]                      # the parsed yaml
INS, OPS, FMTS = isa["INS"], isa["OPS"], isa["FMTS"]


def rows(prefix):
    """Table rows of the doc whose first cell starts with `prefix`."""
    out = []
    for line in SPEC.splitlines():
        line = line.strip()
        if line.startswith("| " + prefix):
            out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def code(cell):
    return cell.strip("`")


# ---------------------------------------------------------------------------
# What the yaml says the constants are. Everything below is derived from it.
# ---------------------------------------------------------------------------
def width(rng):
    return rng[0] - rng[1] + 1


# Every field name has one bit range in every format that has it ([CMN-7]).
FIELD_POS, FIELD_FMTS = {}, {}
for fmt, spec in FMTS.items():
    for name, rng in spec["fields"].items():
        if name in FIELD_POS:
            check(FIELD_POS[name] == tuple(rng),
                  f"yaml: field {name} at {FIELD_POS[name]} and {rng} ({fmt})")
        FIELD_POS.setdefault(name, tuple(rng))
        FIELD_FMTS.setdefault(name, []).append(fmt)
OPND_FIELDS = ["dst", "src0", "src1", "src2"]
WIDTHS = {
    "INSTR_W": Y["instruction_width"],
    "OPCODE_W": width(FIELD_POS["opcode"]),
    "OPND_W": width(FIELD_POS["dst"]),
}
check(len({width(FIELD_POS[f]) for f in OPND_FIELDS}) == 1, "yaml: operand fields differ in width")
check(max(v["code"] for v in OPS.values()) < (1 << WIDTHS["OPND_W"]), "yaml: operand code too wide")
OPCODES = {f"OPCODE_{k}": v["opcode"] for k, v in INS.items()}
OPERANDS = {f"OPND_{k}": v["code"] for k, v in OPS.items()}
RSV_OPC = [v for v in range(1 << WIDTHS["OPCODE_W"]) if v not in OPCODES.values()]
RSV_OPND = [v for v in range(1 << WIDTHS["OPND_W"]) if v not in OPERANDS.values()]
FLD = {}
for name, (msb, lsb) in FIELD_POS.items():
    FLD[f"FLD_{name.upper()}_MSB"] = msb
    FLD[f"FLD_{name.upper()}_LSB"] = lsb
FMT_NAME = {"control": "control", "data": "data", "alu": "ALU"}


def ranges(vals):
    """[3, 6, 7, 12, 13, 14, 15] -> '3, 6, 7, 12–15'."""
    out, i = [], 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[j] + 1:
            j += 1
        out.append(str(vals[i]) if j - i < 2 else f"{vals[i]}–{vals[j]}")
        if j - i == 1:
            out[-1] = f"{vals[i]}, {vals[j]}"
        i = j + 1
    return ", ".join(out)


# 1. the doc's tables against the yaml ---------------------------------------------
doc_w = {code(r[0]): int(r[1]) for r in rows("`") if code(r[0]).endswith("_W") and r[1].isdigit()}
check(doc_w == WIDTHS, f"[CMN-4] widths: doc {doc_w}, yaml {WIDTHS}")

doc_opc = {code(r[0]): (int(r[1]), r[2], r[3]) for r in rows("`OPCODE_") if len(r) == 4 and not code(r[0]).endswith("_W")}
check(set(doc_opc) == set(OPCODES), f"[CMN-5] opcode rows {sorted(doc_opc)} vs yaml {sorted(OPCODES)}")
for name, val in OPCODES.items():
    if name in doc_opc:
        v, key, fmt = doc_opc[name]
        mn = name[len("OPCODE_"):]
        check(v == val, f"[CMN-5] {name} = {v}, yaml {val}")
        check(key == f"`{mn}`", f"[CMN-5] {name}: yaml key cell {key}")
        check(fmt == FMT_NAME[INS[mn]["format"]], f"[CMN-5] {name}: format {fmt}")
check(f"Values {ranges(RSV_OPC)} have no member" in FLAT,
      f"[CMN-5] reserved opcodes sentence: want 'Values {ranges(RSV_OPC)} have no member'")

doc_opnd = {code(r[2]): (r[0], int(r[1])) for r in rows("`") if r[2:] and code(r[2]).startswith("OPND_")}
check(set(doc_opnd) == set(OPERANDS), f"[CMN-6] operand rows {sorted(doc_opnd)} vs yaml {sorted(OPERANDS)}")
for name, val in OPERANDS.items():
    if name in doc_opnd:
        key, v = doc_opnd[name]
        check(v == val, f"[CMN-6] {name} = {v}, yaml {val}")
        check(key == f"`{name[5:]}`", f"[CMN-6] {name}: yaml key cell {key}")
check(f"Codes {ranges(RSV_OPND)} have no member" in FLAT,
      f"[CMN-6] reserved operand codes sentence: want 'Codes {ranges(RSV_OPND)} have no member'")

doc_fld = {}
for r in (r for r in rows("`FLD_") if r[1][:1].isdigit()):
    names = [code(c.strip()) for c in r[0].split(",")]
    vals = [int(v) for v in r[1].split(",")]
    check(len(names) == 2 and len(vals) == 2, f"[CMN-7] row {r}")
    doc_fld.update(zip(names, vals))
    yname = code(r[2])
    check(names == [f"FLD_{yname.upper()}_MSB", f"FLD_{yname.upper()}_LSB"], f"[CMN-7] names {names} for {yname}")
    if yname in FIELD_FMTS:
        want = ", ".join(FMT_NAME[f] for f in FIELD_FMTS[yname])
        check(r[3] == want, f"[CMN-7] {yname}: formats '{r[3]}', yaml '{want}'")
check(doc_fld == FLD, f"[CMN-7] field constants differ: "
      f"{ {k: (doc_fld.get(k), FLD.get(k)) for k in set(doc_fld) | set(FLD) if doc_fld.get(k) != FLD.get(k)} }")
print(f"       widths {WIDTHS}")
print(f"       opcodes {OPCODES}, reserved {RSV_OPC}")
print(f"       operand codes {OPERANDS}, reserved {RSV_OPND}")
print(f"       {len(FIELD_POS)} fields, one bit range each across {len(FMTS)} formats")
check(f"`.num()` is {len(OPCODES)} for `opcode_e` and {len(OPERANDS)} for `opnd_e`" in FLAT,
      "[CMN-9] member counts differ from the yaml")
done("1 [CMN-4] to [CMN-7] tables == bankside_isa.yaml")

# 2. against pcu_decode's model -------------------------------------------------------
check(dec["CODE"] == {k[5:]: v for k, v in OPERANDS.items()}, "[CMN-6] != dec_check CODE (opnd_e)")
dec_doc = (SRC / "pcu_decode" / "doc" / "README.md").read_text()
for name, val in OPERANDS.items():
    check(f"| `{name}` | {val} |" in dec_doc, f"[CMN-6] {name} = {val} not a row of DEC-12")
check(WIDTHS["OPND_W"] == dict(dec["LAYOUT"])["dst"], "[CMN-4] OPND_W != dec_instr_t dst width")

# Case B: the opcode of each legal word, and the dec_op_e value the model gives it.
assemble = isa["assemble"]
EXAMPLE = {"NOP": "NOP 3", "JUMP": "JUMP -1, 2", "EXIT": "EXIT",
           "MOV": "MOV GRF_A[1], EVEN_BANK", "FILL": "FILL GRF_B[4], ODD_BANK",
           "ADD": "ADD GRF_A[0], GRF_B[1], SRF_A[2]", "MUL": "MUL GRF_B[3], GRF_A[1], SRF_M[4]",
           "MAD": "MAD GRF_A[0], GRF_B[1], EVEN_BANK, SRF_A[5]",
           "MAC": "MAC GRF_B[0], GRF_A[1], GRF_A[2]"}
check(set(EXAMPLE) == set(INS), "case B covers every instruction")
lines = ["| `opcode_e` member | Value | Word | Instruction | `dec_instr.op` (model) |",
         "|---|---|---|---|---|"]
for name, val in sorted(OPCODES.items(), key=lambda kv: kv[1]):
    mn = name[len("OPCODE_"):]
    w = assemble(EXAMPLE[mn])
    ill, _, _, d = dec["model"](w)
    check(ill == 0, f"case B: {EXAMPLE[mn]} illegal in the model")
    check((w >> FLD["FLD_OPCODE_LSB"]) & ((1 << WIDTHS["OPCODE_W"]) - 1) == val, f"case B: opcode of {EXAMPLE[mn]}")
    want = mn if mn in dec["DEC_OP"] else "NONE"
    check(d["op"] == dec["DEC_OP"][want], f"case B: {EXAMPLE[mn]} op {d['op']}, want DEC_OP_{want}")
    lines.append(f"| `{name}` | {val} | `0x{w:08X}` | `{EXAMPLE[mn]}` | "
                 f"`{'DEC_OP_' + dec['DEC_OP_NAME'][d['op']]}` |")
for v in RSV_OPC:
    ill, _, _, d = dec["model"](v << FLD["FLD_OPCODE_LSB"])
    check(ill == 1 and d == dec["DEC_NOP"], f"case B: reserved opcode {v} not illegal in the model")
lines.append(f"| – | {ranges(RSV_OPC)} | opcode *v* in bits 31–28, the rest 0 | reserved | "
             f"`DEC_OP_NONE`, illegal |")
CASE_B = "\n".join(lines)
check(CASE_B in SPEC, "case B table differs from the doc:\n" + CASE_B)

# Case C: the field constants, applied to words, against the model's decode.
def get(w, f):
    msb, lsb = doc_fld[f"FLD_{f.upper()}_MSB"], doc_fld[f"FLD_{f.upper()}_LSB"]
    return (w >> lsb) & ((1 << (msb - lsb + 1)) - 1)


rnd = random.Random(53)
DATA_OPC = [v["opcode"] for v in INS.values() if v["format"] != "control"]
checked = tries = 0
while checked < 20000:
    # a data or ALU opcode, every other bit random; keep the legal words
    tries += 1
    w = (rnd.choice(DATA_OPC) << 28) | rnd.getrandbits(28)
    ill, _, _, d = dec["model"](w)
    if ill:
        continue
    mn = dec["DEC_OP_NAME"][d["op"]]
    alu = INS[mn]["format"] == "alu"
    banks = dec["BANK_CODES"]
    check(get(w, "opcode") == OPCODES[f"OPCODE_{mn}"], f"case C 0x{w:08X} opcode")
    check(get(w, "dst") == d["dst"] and get(w, "src0") == d["src0"], f"case C 0x{w:08X} dst/src0")
    if alu:
        check(get(w, "src1") == d["src1"], f"case C 0x{w:08X} src1")
    if d["dst"] not in banks:
        check(get(w, "dst_idx") == d["dst_idx"], f"case C 0x{w:08X} dst_idx")
    if d["src0"] not in banks:
        check(get(w, "src0_idx") == d["src0_idx"], f"case C 0x{w:08X} src0_idx")
    if alu and (d["src1"] not in banks or mn == "MAD"):
        check(get(w, "src1_idx") == d["src1_idx"], f"case C 0x{w:08X} src1_idx")
    if mn == "MOV":
        check(get(w, "relu") == d["relu"], f"case C 0x{w:08X} relu")
    checked += 1
print(f"       case C: {checked} random legal words, fields by the FLD_* constants == the model's dec_instr")

w = assemble("MUL GRF_B[3], GRF_A[1], SRF_M[4]")
_, _, _, d = dec["model"](w)
inv_opnd = {v: k for k, v in OPERANDS.items()}
lines = ["| Field | Bits (`FLD_*_MSB`:`FLD_*_LSB`) | Value | Constant | `dec_instr` field (model) |",
         "|---|---|---|---|---|"]
for f in ("opcode", "dst", "src0", "src1", "src2", "aam", "dst_idx", "src0_idx", "src1_idx"):
    msb, lsb = FIELD_POS[f]
    v = get(w, f)
    const = None
    if f == "opcode":
        const = f"`{ {v2: k for k, v2 in OPCODES.items()}[v]}`"
    if f in OPND_FIELDS:
        const = f"`{inv_opnd[v]}`"
    model_cell = f"`{f}` = {d[f]}" if f in d else ("not in `dec_instr`: MUL ignores it ([TOP-ISA-10])" if f == "src2" else
                                                     "not in `dec_instr`: 1 is illegal in v1 ([TOP-ISA-2])" if f == "aam" else
                                                     f"`op` = `DEC_OP_{dec['DEC_OP_NAME'][d['op']]}`")
    lines.append(f"| `{f}` | {msb}:{lsb} | {v} | {const or '–'} | {model_cell} |")
CASE_C = "\n".join(lines)
check(f"`0x{w:08X}`" in SPEC, f"case C word 0x{w:08X} not in the doc")
check(CASE_C in SPEC, "case C table differs from the doc:\n" + CASE_C)
done("2 [CMN-6] == opnd_e of DEC-12 and dec_check; case B (opcode -> dec_op_e); case C (FLD_* -> fields)")


# 3. the SystemVerilog block ------------------------------------------------------------
def render():
    out = ["// The constants of [CMN-4] to [CMN-7], from bankside_isa.yaml.",
           "// Widths [CMN-4]"]
    pad = max(len(k) for k in WIDTHS)
    for k, v in WIDTHS.items():
        out.append(f"localparam int {k:<{pad}} = {v};")
    out.append("")
    out.append("// Opcodes [CMN-5]; reserved values have no member")
    out.append("typedef enum logic [OPCODE_W-1:0] {")
    items = sorted(OPCODES.items(), key=lambda kv: kv[1])
    pad = max(len(k) for k, _ in items)
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        out.append(f"  {k:<{pad}} = {WIDTHS['OPCODE_W']}'d{v}{comma}")
    out.append("} opcode_e;")
    out.append("")
    out.append("// Instruction field positions [CMN-7], [msb:lsb] in the 32-bit word")
    pad = max(len(k) for k in FLD)
    for name in FIELD_POS:
        for end in ("MSB", "LSB"):
            k = f"FLD_{name.upper()}_{end}"
            out.append(f"localparam int {k:<{pad}} = {FLD[k]};")
    return "\n".join(out)


SV = render()
m = re.search(r"```systemverilog\n(// The constants of \[CMN-4\].*?)\n```", SPEC, re.S)
check(m is not None, "[CMN-8] SystemVerilog block not found in the doc")
if m:
    check(m.group(1) == SV, "[CMN-8] SystemVerilog block differs from the yaml rendering:\n" + SV)

USE = """
module bankside_pkg_use
  import bankside_pkg::*;
(
  input  logic [INSTR_W-1:0] instr,
  output logic               is_jump,
  output opcode_e            opc,
  output logic [7:0]         imm0,
  output int                 n_opc
);
  assign is_jump = (instr[FLD_OPCODE_MSB:FLD_OPCODE_LSB] == OPCODE_JUMP);
  assign opc     = opcode_e'(instr[FLD_OPCODE_MSB:FLD_OPCODE_LSB]);
  assign imm0    = instr[FLD_IMM0_MSB:FLD_IMM0_LSB];
  assign n_opc   = opc.num();
  // every other constant, so -Wall sees each one used
  logic unused;
  assign unused = ^{instr[FLD_DST_MSB:FLD_DST_LSB], instr[FLD_SRC0_MSB:FLD_SRC0_LSB],
                    instr[FLD_SRC1_MSB:FLD_SRC1_LSB], instr[FLD_SRC2_MSB:FLD_SRC2_LSB],
                    instr[FLD_AAM_MSB:FLD_AAM_LSB], instr[FLD_RELU_MSB:FLD_RELU_LSB],
                    instr[FLD_DST_IDX_MSB:FLD_DST_IDX_LSB], instr[FLD_SRC0_IDX_MSB:FLD_SRC0_IDX_LSB],
                    instr[FLD_SRC1_IDX_MSB:FLD_SRC1_IDX_LSB], instr[FLD_IMM1_MSB:FLD_IMM1_LSB],
                    OPND_W[2:0], OPCODE_NOP, OPCODE_EXIT, OPCODE_MOV, OPCODE_FILL,
                    OPCODE_ADD, OPCODE_MUL, OPCODE_MAD, OPCODE_MAC};
endmodule
"""
WRONG = """
module wrong
  import bankside_pkg::*;
(
  input  logic [INSTR_W-1:0] instr,
  output logic               hit
);
  {decl} op;
  assign op  = OPND_EVEN_BANK;  // meant OPCODE_MOV
  assign hit = (instr[FLD_OPCODE_MSB:FLD_OPCODE_LSB] == op);
endmodule
"""
OPND_ENUM = ("typedef enum logic [2:0] {\n" +
             ",\n".join(f"  {k} = 3'd{v}" for k, v in OPERANDS.items()) + "\n} opnd_e;")


def lint(tmp, pkg_body, top, extra="", flags=()):
    (tmp / "bankside_pkg.sv").write_text(f"package bankside_pkg;\n{pkg_body}\n{extra}\nendpackage\n")
    (tmp / f"{top[0]}.sv").write_text(top[1])
    r = subprocess.run(["verilator", "--lint-only", "-Wall", *flags, "--top-module", top[0],
                        "bankside_pkg.sv", f"{top[0]}.sv"], cwd=tmp, capture_output=True, text=True)
    msgs = [l for l in r.stderr.splitlines() if l.startswith("%")]
    return r.returncode, msgs


if shutil.which("verilator"):
    ver = subprocess.run(["verilator", "--version"], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        rc, msgs = lint(tmp, SV, ("bankside_pkg_use", USE))
        check(rc == 0 and not msgs, f"[CMN-8] block does not lint clean: {msgs}")
        print(f"       {ver}: the block in bankside_pkg.sv, -Wall: {'clean' if rc == 0 else msgs}")
        # Case D: the same slip under (a) the enum and (b) a plain localparam logic [3:0].
        res = {}
        lines = ["| Option | `op` declared as | Verilator `-Wall -Wno-UNUSED` reports | Caught? |",
                 "|---|---|---|---|"]
        for opt, decl in (("a", "opcode_e"), ("b", "logic [OPCODE_W-1:0]")):
            rc, msgs = lint(tmp, SV, ("wrong", WRONG.replace("{decl}", decl)), OPND_ENUM,
                            ("-Wno-UNUSED",))
            kinds = sorted({re.match(r"%(\w+(-\w+)?)", m).group(1) for m in msgs} - {"Error"})
            res[opt] = kinds
            caught = ("yes: an error, by type" if "Error-ENUMVALUE" in kinds else
                      "only by the width mismatch" if kinds else "no")
            lines.append(f"| ({opt}) | `{decl}` | {', '.join(f'`{k}`' for k in kinds) or 'nothing'} | {caught} |")
        CASE_D = "\n".join(lines)
        print("       case D:\n" + "\n".join("         " + l for l in lines))
        check("Error-ENUMVALUE" in res["a"], "case D (a): no ENUMVALUE error")
        check("Error-ENUMVALUE" not in res["b"], "case D (b): unexpected ENUMVALUE error")
        check(CASE_D in SPEC, "case D table differs from the doc:\n" + CASE_D)
    done("3 [CMN-8] block == yaml rendering, lints clean; case D")
else:
    done("3 [CMN-8] block == yaml rendering (Verilator not on PATH: lint and case D skipped)")

# 4. the contents table and its links ----------------------------------------------------
m = re.search(r"\*\*\[CMN-2\]\*\*.*?\n\n( *\|.*?)\n\n", SPEC, re.S)
check(m is not None, "[CMN-2] table not found")
items = set()
if m:
    for line in m.group(1).splitlines()[2:]:
        cell = line.strip().split("|")[1]
        items |= set(re.findall(r"`([A-Za-z_*]+)`", cell))
want = ({"INSTR_W", "OPCODE_W", "OPND_W", "opcode_e", "FLD_*"} |
        {"dec_op_e", "opnd_e", "dec_instr_t", "DEC_NOP"})
check(items == want, f"[CMN-2] contents {sorted(items)}, want {sorted(want)}")
for rid, anchor in (("DEC-11", "the-decoded-instruction"), ("DEC-12", "the-decoded-instruction"),
                    ("DEC-14", "the-decoded-instruction"), ("DEC-15", "where-the-types-live")):
    check(f"**[{rid}]**" in dec_doc, f"{rid} not defined in pcu_decode's doc")
    check(f"[{rid}]: ../../pcu_decode/doc/README.md#{anchor}" in SPEC, f"{rid} link")


def slugs(path):
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
            for h in re.findall(r"^#+ (.*)$", path.read_text(), re.M)}


n = 0
for target in re.findall(r"\]\(([^)]+)\)", SPEC) + re.findall(r"^\[[^\]]+\]: (\S+)$", SPEC, re.M):
    if re.match(r"https?:", target):
        continue
    file, _, anchor = target.partition("#")
    dest = (DOC.parent / file).resolve() if file else DOC
    check(dest.exists(), f"link {target} missing")
    if anchor and dest.exists() and dest.suffix == ".md":
        check(anchor in slugs(dest), f"anchor {target}")
    n += 1
ids = re.findall(r"\*\*\[(CMN-\d+)\]\*\*", SPEC)
check(len(ids) == len(set(ids)), f"CMN IDs defined twice: {ids}")
for ref in set(re.findall(r"\[(CMN-\d+)\]", SPEC)):
    check(ref in ids, f"{ref} referenced, never defined")
print(f"       CMN IDs {ids}")
done(f"4 [CMN-2] contents == the tables and DEC-11/12/14; {n} links resolve; IDs defined once")
