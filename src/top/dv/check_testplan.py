#!/usr/bin/env python3
"""Check src/top/dv/README.md against the top spec.

- every requirement ID the spec defines (**[TOP-...]** in src/top/doc/*.md)
  has exactly one row in the Requirement coverage table, and the table has
  no row for an ID the spec doesn't define;
- every row's "Checked by" cell names a VER item or says "uncovered";
- every [TOP-...] the README cites is defined in the spec;
- every module ID the README cites ([CTRL-n], [DP-n], [FMUL-n], ...) is
  defined exactly once in that module's merged doc (src/*/doc/*.md);
- every VER-n is defined (**[VER-n]**) exactly once in the README, and every
  VER-n the README, the spec or the yaml cites is defined;
- every relative link and anchor in the README resolves.

Run from the repo root: .venv/bin/python src/top/dv/check_testplan.py
Exits non-zero on any failure.
"""
import re
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
SRC = TOP.parent
DOC = TOP / "doc"
README = TOP / "dv" / "README.md"
ID = r"TOP-[A-Z]+-\d+"
VER = r"VER-\d+"

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def key(i):
    _, area, n = i.split("-")
    return (area, int(n))


# Spec definitions and references.
spec_docs = sorted(DOC.glob("*.md"))
defined = {}
for p in spec_docs:
    for m in re.finditer(rf"\*\*\[({ID})\]\*\*", p.read_text()):
        defined.setdefault(m.group(1), []).append(p.name)
for i, where in defined.items():
    check(len(where) == 1, f"spec: {i} defined {len(where)} times ({where})")

text = README.read_text()

# Coverage table: the rows after the "## Requirement coverage" heading.
section = text.split("## Requirement coverage", 1)
check(len(section) == 2, "README: no '## Requirement coverage' section")
rows = {}
if len(section) == 2:
    body = section[1].split("\n## ", 1)[0]
    for line in body.splitlines():
        m = re.match(rf"^\| \[({ID})\] \| (.*?) \| (.*) \|$", line)
        if not m:
            continue
        i, _, by = m.groups()
        check(i not in rows, f"table: {i} has more than one row")
        rows[i] = by
        check(re.search(VER, by) or by.startswith("uncovered"),
              f"table: {i} names no VER item and is not marked uncovered")
for i in sorted(set(defined) - set(rows), key=key):
    check(False, f"table: {i} is defined in the spec but has no row")
for i in sorted(set(rows) - set(defined), key=key):
    check(False, f"table: {i} has a row but is not defined in the spec")

# Every TOP ID cited in the README exists.
for i in sorted(set(re.findall(rf"\[({ID})\]", text)) - set(defined), key=key):
    check(False, f"README: cites {i}, which the spec doesn't define")

# Module IDs (one-part prefix, e.g. CTRL-4, DP-16, FMUL-2): every one the
# README cites is defined once in some module doc other than top's.
MOD = r"(?!VER-)[A-Z]+-\d+"
mod_defined = {}
for p in sorted(SRC.glob("*/doc/*.md")):
    if p.parent == DOC:
        continue
    for m in re.finditer(rf"\*\*\[({MOD})\]\*\*", p.read_text()):
        mod_defined.setdefault(m.group(1), []).append(str(p.relative_to(SRC)))
mod_cited = set(re.findall(rf"\[({MOD})\]", text))
for i in sorted(mod_cited):
    where = mod_defined.get(i, [])
    check(len(where) == 1,
          f"README: cites {i}, defined {len(where)} times in the module docs {where}")


# VER items: defined once here; every citation (README, spec, yaml) defined.
ver_defs = re.findall(rf"\*\*\[({VER})\]", text)
for v in sorted(set(ver_defs)):
    check(ver_defs.count(v) == 1, f"README: {v} defined {ver_defs.count(v)} times")
cited = set(re.findall(rf"\b({VER})\b", text))
for p in spec_docs + [DOC / "bankside_isa.yaml"]:
    cited |= set(re.findall(rf"\b({VER})\b", p.read_text()))
for v in sorted(cited - set(ver_defs), key=lambda s: int(s.split("-")[1])):
    check(False, f"{v} is cited but not defined in the README")


# Links and anchors (GitHub heading slugs, as check_isa.py computes them).
def slugs(path):
    out = set()
    for h in re.findall(r"^#+ (.*)$", path.read_text(), re.M):
        out.add(re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-"))
    return out


links = 0
for target in re.findall(r"\]\(([^)]+)\)", text):
    if re.match(r"https?:", target):
        continue
    file, _, anchor = target.partition("#")
    dest = (README.parent / file).resolve() if file else README
    check(dest.exists(), f"link: {target} missing")
    if anchor and dest.exists() and dest.suffix == ".md":
        check(anchor in slugs(dest), f"link: anchor {target} not found")
    links += 1

uncovered = sorted((i for i, by in rows.items() if "uncovered" in by), key=key)
print(f"spec IDs defined: {len(defined)}; table rows: {len(rows)}")
print(f"rows with an uncovered part: {len(uncovered)}: {', '.join(uncovered)}")
print(f"module IDs cited: {len(mod_cited)}: {', '.join(sorted(mod_cited))}")
print(f"VER items defined: {len(set(ver_defs))}; cited: {len(cited)}")
print(f"relative links checked: {links}")
for f in fails:
    print("FAIL", f)
print("ok" if not fails else f"{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
