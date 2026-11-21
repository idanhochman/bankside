#!/usr/bin/env python3
"""Render bankside diagram sources to SVG, preview them as PNG, or check them.

Sources, found by extension under the given paths (files or directories):
  *.dot        Graphviz: block diagrams, flows, state machines
  *.wave.json  WaveDrom: timing diagrams
  *.reg.json   WaveDrom: bitfields (instruction and register layouts)

Each source renders to an SVG beside it with the same stem:
  img/pcu_top.dot -> img/pcu_top.svg, img/hazard.wave.json -> img/hazard.svg

Usage (from the repo root):
  .venv/bin/python .claude/skills/diagrams/scripts/render.py PATH...
  .venv/bin/python .claude/skills/diagrams/scripts/render.py --png DIR PATH...
  .venv/bin/python .claude/skills/diagrams/scripts/render.py --check PATH...

--png DIR  also writes a PNG of each diagram into DIR, to look at. Keep DIR
           outside the repo (your scratch directory): PNGs are not committed.
--check    renders nothing in place; reports sources whose SVG is missing or
           out of date, and exits 1 if there are any.

Needs: Graphviz (`dot`), `rsvg-convert` (for --png), and the `wavedrom` Python
package (in the repo's .venv).
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUFFIXES = (".wave.json", ".reg.json", ".dot")


def kind(path: Path):
    name = path.name
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return None


def svg_path(src: Path) -> Path:
    return src.with_name(src.name[: -len(kind(src))] + ".svg")


def find_sources(paths):
    found = []
    for p in map(Path, paths):
        if p.is_dir():
            found += [f for f in sorted(p.rglob("*")) if f.is_file() and kind(f)]
        elif p.is_file() and kind(p):
            found.append(p)
        else:
            sys.exit(f"not a diagram source or directory: {p}")
    return found


def render(src: Path, out: Path):
    """Render src to the SVG file out. Raises RuntimeError with a readable message."""
    k = kind(src)
    if k == ".dot":
        r = subprocess.run(["dot", "-Tsvg", str(src), "-o", str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "dot failed")
        if r.stderr.strip():  # warnings: treat as errors, they usually mean a typo
            raise RuntimeError("dot warning: " + r.stderr.strip())
    else:
        text = src.read_text()
        try:
            data = json.loads(text)  # strict JSON: clear error messages, no JSON5
        except json.JSONDecodeError as e:
            raise RuntimeError(f"invalid JSON: {e}")
        if k == ".reg.json" and "reg" not in data:
            raise RuntimeError('a .reg.json file needs a top-level "reg" list')
        if k == ".wave.json" and "signal" not in data:
            raise RuntimeError('a .wave.json file needs a top-level "signal" list')
        import wavedrom  # imported here so .dot-only runs don't need the venv
        try:
            wavedrom.render(text).saveas(str(out))
        except Exception as e:  # wavedrom's own errors are terse
            raise RuntimeError(f"wavedrom failed: {e!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--png", metavar="DIR", help="also write PNG previews into DIR")
    ap.add_argument("--check", action="store_true",
                    help="report missing or stale SVGs; exit 1 if any")
    args = ap.parse_args()

    sources = find_sources(args.paths)
    if not sources:
        sys.exit("no diagram sources found")

    failed, stale = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for src in sources:
            target = svg_path(src)
            out = Path(tmp) / target.name if args.check else target
            try:
                render(src, out)
            except RuntimeError as e:
                failed.append(src)
                print(f"FAIL   {src}: {e}")
                continue
            if args.check:
                if not target.exists():
                    stale.append(src)
                    print(f"MISSING {target}")
                elif target.read_bytes() != out.read_bytes():
                    stale.append(src)
                    print(f"STALE  {target} (re-render {src})")
                else:
                    print(f"ok     {target}")
            else:
                print(f"ok     {src} -> {target}")
            if args.png:
                png = Path(args.png) / (target.stem + ".png")
                png.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["rsvg-convert", "--zoom", "2", str(out), "-o", str(png)],
                               check=True)
                print(f"       preview {png}")

    if failed or stale:
        sys.exit(1)


if __name__ == "__main__":
    main()
