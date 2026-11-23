#!/usr/bin/env python3
"""The whole spec check suite, in one command.

What it runs and checks:
  1. Every example script of every module's spec (src/*/doc/examples/*.py),
     in parallel, with this interpreter. Each must exit 0. Where the saved
     .out file is the output of the script's default command, the new output
     must equal it byte for byte (--update rewrites those files instead).
     Scripts whose saved .out comes from a fuller command (the NumPy and
     ANEMOS runs) are run in their default form and checked for exit 0
     only; --full also runs their full form (below).
  2. The diagrams: .claude/skills/diagrams/scripts/render.py --check src/
     (every SVG exists and matches its source).
  3. Requirement IDs across all modules: every ID defined (in bold,
     **[PFX-...-n]**) in src/*/doc/ is defined exactly once, in the doc of
     the module whose prefix it carries; every prefix is one of the
     [TOP-HIER-1] table; and every ID referenced in src/*/doc/ is defined
     (VER-n: in src/top/dv/README.md, DV's testplan).
  4. Links: every relative link and reference definition in src/*/doc/ and
     src/*/README.md resolves to a file, and every #anchor to a heading.

Not run: paper_table3.py, which needs your own copy of the ISCA 2021 PDF
(see src/top/doc/examples/README.md).

Run from the repo root:
    .venv/bin/python src/top/doc/examples/spec_check.py            # about 6 minutes
    .venv/bin/python src/top/doc/examples/spec_check.py --full     # adds the NumPy and
        ANEMOS runs (about 45 minutes; needs --numpy-python, an interpreter
        with NumPy and PyYAML, default python3, and the saved anemos_*.out)
Exits non-zero if anything fails.
"""
import argparse
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
RENDER = ROOT / ".claude" / "skills" / "diagrams" / "scripts" / "render.py"
SKIP = {"paper_table3.py", "spec_check.py"}

# Scripts whose saved .out comes from a fuller command than the default.
# (script, arguments of the full command, relative to the repo root)
FULL = {
    "src/fp16_mul/doc/examples/fmul_check.py":
        ["--numpy", "--exhaustive", "--anemos", "src/fp16_mul/doc/examples/anemos_fmul.out"],
    "src/fp16_add/doc/examples/fadd_check.py":
        ["--numpy", "--exhaustive", "--anemos", "src/fp16_add/doc/examples/anemos_fadd.out"],
    "src/top/doc/examples/fp_relu_nan.py":
        ["--numpy", "--anemos", "src/top/doc/examples/anemos_fp.out"],
}
# [TOP-HIER-1]: module -> prefix
PREFIX = {"top": "TOP", "pcu_ctrl": "CTRL", "pcu_decode": "DEC", "pcu_datapath": "DP",
          "fp16_mul": "FMUL", "fp16_add": "FADD", "pcu_regfile": "RF", "common": "CMN"}

failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL {msg}")


def run(cmd):
    t = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p, time.time() - t


# 1. Example scripts ---------------------------------------------------------
def scripts(args):
    jobs = []
    for s in sorted(SRC.glob("*/doc/examples/*.py")):
        if s.name in SKIP:
            continue
        rel = str(s.relative_to(ROOT))
        jobs.append((rel, [sys.executable, rel], rel not in FULL))
        if args.full and rel in FULL:
            jobs.append((rel + " (full)", [args.numpy_python, rel] + FULL[rel], True))
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda j: (j, run(j[1])), jobs))
    for (name, cmd, compare), (p, dt) in results:
        script = name.split()[0]
        out = ROOT / script.replace(".py", ".out")
        if p.returncode != 0:
            fail(f"1 {name}: exit {p.returncode}\n{p.stdout[-2000:]}{p.stderr[-2000:]}")
            continue
        note = "exit 0"
        if compare and out.exists():
            if args.update:
                if out.read_text() != p.stdout:
                    out.write_text(p.stdout)
                    note = "exit 0, .out rewritten"
                else:
                    note = "exit 0, .out unchanged"
            elif out.read_text() != p.stdout:
                fail(f"1 {name}: output differs from {out.relative_to(ROOT)} (rerun with --update "
                     "if the change is intended)")
                continue
            else:
                note = "exit 0, output == saved .out"
        elif not compare:
            note = "exit 0 (saved .out is from the full command, --full)"
        print(f"ok   1 {name}: {note} ({dt:.0f} s)")


# 2. Diagrams ----------------------------------------------------------------
def diagrams():
    p, _ = run([sys.executable, str(RENDER.relative_to(ROOT)), "--check", "src/"])
    if p.returncode != 0:
        fail(f"2 render.py --check src/:\n{p.stdout}{p.stderr}")
    else:
        n = len([l for l in p.stdout.splitlines() if l.strip()])
        print(f"ok   2 render.py --check src/: every SVG matches its source ({n} lines of report)")


# 3. Requirement IDs -----------------------------------------------------------
ID = r"[A-Z]+(?:-[A-Z]+)?-\d+"


def ids():
    docs = sorted(SRC.glob("*/doc/**/*.md"))
    defs, refs = {}, {}
    for p in docs:
        module = p.relative_to(SRC).parts[0]
        text = p.read_text()
        for m in re.finditer(rf"\*\*\[({ID})\]\*\*", text):
            defs.setdefault(m.group(1), []).append((module, p))
        for m in re.finditer(rf"\[({ID})\]", re.sub(r"`[^`\n]*`", "", text)):
            refs.setdefault(m.group(1), set()).add(p)
    ver = set(re.findall(r"\b(VER-\d+)\b", (SRC / "top" / "dv" / "README.md").read_text()))
    n_bad = len(failures)
    for i, where in sorted(defs.items()):
        pfx = i.split("-")[0]
        if len(where) != 1:
            fail(f"3 {i} defined {len(where)} times: {[str(p.relative_to(ROOT)) for _, p in where]}")
        if pfx not in PREFIX.values():
            fail(f"3 {i}: prefix {pfx} is not in [TOP-HIER-1]")
        elif PREFIX.get(where[0][0]) != pfx:
            fail(f"3 {i} defined in {where[0][1].relative_to(ROOT)}, not in its module's doc")
    for i, where in sorted(refs.items()):
        if i.startswith("VER-"):
            ok = i in ver
        else:
            ok = i in defs
        if not ok:
            fail(f"3 {i} referenced in {sorted(str(p.relative_to(ROOT)) for p in where)} but never defined")
    if len(failures) == n_bad:
        per = {}
        for i in defs:
            per[i.split("-")[0]] = per.get(i.split("-")[0], 0) + 1
        print(f"ok   3 {len(defs)} requirement IDs, each defined once, in its own module's doc: "
              + ", ".join(f"{k} {v}" for k, v in sorted(per.items())))
        print(f"ok   3 {len(refs)} distinct IDs referenced, all defined (VER-n in src/top/dv/README.md)")


# 4. Links -----------------------------------------------------------------------
def slugs(path, cache={}):
    if path not in cache:
        out = set()
        text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
        for h in re.findall(r"^#+ (.*)$", text, re.M):
            h = re.sub(r"[`*]", "", h)
            out.add(re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-"))
        cache[path] = out
    return cache[path]


def links():
    files = sorted(SRC.glob("*/doc/**/*.md")) + sorted(SRC.glob("*/README.md"))
    n, n_bad = 0, len(failures)
    for p in files:
        text = re.sub(r"```.*?```", "", p.read_text(), flags=re.S)
        targets = re.findall(r"\]\(([^)\s]+)\)", text)
        targets += re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, re.M)
        for target in targets:
            if re.match(r"(https?|mailto):", target):
                continue
            file, _, anchor = target.partition("#")
            dest = (p.parent / file).resolve() if file else p
            n += 1
            if not dest.exists():
                fail(f"4 {p.relative_to(ROOT)}: {target} missing")
            elif anchor and dest.suffix == ".md" and anchor not in slugs(dest):
                fail(f"4 {p.relative_to(ROOT)}: anchor {target}")
    if len(failures) == n_bad:
        print(f"ok   4 {n} relative links in {len(files)} files resolve, anchors included")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="rewrite the saved .out files that differ")
    ap.add_argument("--full", action="store_true", help="also run the NumPy and ANEMOS forms")
    ap.add_argument("--numpy-python", default="python3", help="interpreter with NumPy, for --full")
    ap.add_argument("--jobs", type=int, default=6, help="scripts run in parallel")
    args = ap.parse_args()
    t = time.time()
    ids()
    links()
    diagrams()
    scripts(args)
    print()
    if failures:
        print(f"FAIL {len(failures)} check(s) failed ({time.time() - t:.0f} s)")
        sys.exit(1)
    print(f"ok   the whole spec check suite passes ({time.time() - t:.0f} s)")


if __name__ == "__main__":
    main()
