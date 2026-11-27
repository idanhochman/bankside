#!/usr/bin/env python3
"""Create a bankside module from the template.

    python3 src/common/util/new_module.py NAME --prefix PREFIX [--parent PARENT]

Copies src/common/util/template/ to src/NAME/, filling in the module's name,
its requirement ID prefix and its parent. Nothing is overwritten: if any file
it would create already exists, it stops before writing anything. Folders
that exist are fine, which is how src/common/ (already holding util/) is
created.

- NAME: snake_case, e.g. fp16_mul.
- --prefix: the requirement ID prefix, upper case, e.g. FMUL for [FMUL-3].
  It must not be used by any other module, past or present.
- --parent: the module whose doc describes how this one connects (default
  top). Use "none" for top and common.

The architect runs this; the template and the script are the user's. After it:
describe the module in its parent's doc; DV adds it to the root opendv.yaml
(right away: opendv lints a target before it has tests).
"""
import argparse
import re
import sys
from pathlib import Path

UTIL = Path(__file__).resolve().parent
TEMPLATE = UTIL / "template"
ROOT = UTIL.parents[2]  # src/common/util -> the repo root
PREFIX_LINE = re.compile(r"\*\*Requirement ID prefix:\*\* `([A-Z][A-Z0-9]*)`")


def used_prefixes(src: Path) -> dict[str, str]:
    """Prefixes recorded in the modules' READMEs: prefix -> module."""
    found = {}
    for readme in sorted(src.glob("*/README.md")):
        m = PREFIX_LINE.search(readme.read_text())
        if m:
            found[m.group(1)] = readme.parent.name
    return found


def fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        sys.exit(f"new_module: template placeholder(s) left unfilled: {', '.join(left)}")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("name")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--parent", default="top")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="repo root (default: the one holding this script)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the files without writing them")
    a = ap.parse_args(argv)

    src = a.root.resolve() / "src"
    if not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", a.name):
        sys.exit(f"new_module: '{a.name}' isn't snake_case (e.g. fp16_mul)")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*", a.prefix):
        sys.exit(f"new_module: prefix '{a.prefix}' must be upper case letters and "
                 "digits, starting with a letter (e.g. FMUL)")
    owner = used_prefixes(src).get(a.prefix)
    if owner and owner != a.name:
        sys.exit(f"new_module: prefix {a.prefix} is already used by {owner}")
    if a.parent == "none":
        parent_line = "none"
    else:
        if not (src / a.parent / "doc").is_dir():
            sys.exit(f"new_module: parent '{a.parent}' has no src/{a.parent}/doc/; "
                     "create it first, or pass --parent none")
        parent_line = (f"[{a.parent}](../{a.parent}/doc/), whose doc describes "
                       "how this module connects")

    values = {"module": a.name, "PREFIX": a.prefix, "parent_line": parent_line}
    dest = src / a.name
    plan = []
    for f in sorted(p for p in TEMPLATE.rglob("*") if p.is_file()):
        rel = Path(fill(str(f.relative_to(TEMPLATE)), values))
        plan.append((f, dest / rel))
    clash = [str(t.relative_to(a.root.resolve())) for _, t in plan if t.exists()]
    if clash:
        sys.exit("new_module: these already exist, nothing was written:\n  "
                 + "\n  ".join(clash))

    for f, target in plan:
        print(target.relative_to(a.root.resolve()))
        if not a.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(fill(f.read_text(), values))
    if a.dry_run:
        print("(dry run: nothing written)")
    else:
        step = "" if a.parent == "none" else f"describe it in src/{a.parent}/doc/; "
        print(f"\nCreated src/{a.name}/. Next: {step}"
              "DV adds it to the root opendv.yaml.")


if __name__ == "__main__":
    main()
