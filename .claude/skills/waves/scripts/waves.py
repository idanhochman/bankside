"""Waveforms from opendv's dump.fst: text tables for debugging, GTKWave images
for review pages. Runs inside the waves image; call it through ./waves.

  waves list  DUMP                                  the signals in a dump
  waves table DUMP --signals a,b [--clock clk|none] [--from T] [--to T]
  waves png   SPEC.waves.yaml...                    write SPEC.png next to each spec
  waves png   --check PATH...                       every *.waves.yaml under PATH:
                                                    its PNG exists and matches

Times are numbers with a unit: 150ns, 2.5us, 1200ps.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNITS = {"s": 1, "ms": Fraction(1, 10**3), "us": Fraction(1, 10**6), "ns": Fraction(1, 10**9),
         "ps": Fraction(1, 10**12), "fs": Fraction(1, 10**15)}
FORMATS = {"hex": "Hex", "dec": "Decimal", "signed": "Signed_Decimal", "bin": "Binary"}
# Pixel geometry of a grab (GTKWave 3.3.116, the fonts in gtkwaverc): the toolbar
# to crop off the top, and the height of the header row and of each signal row.
TOOLBAR, HEADER, ROW = 44, 25, 23


class Error(Exception):
    pass


def seconds(text: str) -> Fraction:
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(s|ms|us|ns|ps|fs)\s*", str(text))
    if not m:
        raise Error(f"'{text}' isn't a time: use a number and a unit, e.g. 150ns")
    return Fraction(m.group(1)) * UNITS[m.group(2)]


# -- reading a dump ---------------------------------------------------------

class Dump:
    """A dump's header: its timescale and its signals (full name -> (id, width))."""

    def __init__(self, path: Path):
        if not path.is_file():
            raise Error(f"no dump at {path}")
        self.path = path
        self.proc = subprocess.Popen(["fst2vcd", "-f", str(path)], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        self.lines = self.proc.stdout
        self.signals: dict[str, tuple[str, int]] = {}
        self.timescale = Fraction(1, 10**12)
        scope: list[str] = []
        for line in self.lines:
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "$timescale":
                spec = " ".join(tok[1:-1]) if tok[-1] == "$end" else next(self.lines).strip()
                self.timescale = seconds(spec.replace(" ", ""))
            elif tok[0] == "$scope":
                scope.append(tok[2])
            elif tok[0] == "$upscope":
                scope.pop()
            elif tok[0] == "$var":
                # cocotb's $rootio scope repeats the toplevel's ports: skip it
                if scope and not scope[0].startswith("$"):
                    self.signals[".".join([*scope, tok[4]])] = (tok[3], int(tok[2]))
            elif tok[0] == "$enddefinitions":
                break

    def resolve(self, name: str) -> str:
        """A full name, or a unique ending of one (`irq`, `regfile.irq`)."""
        if name in self.signals:
            return name
        hits = [n for n in self.signals if n.endswith("." + name)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise Error(f"'{name}' matches several signals: {', '.join(hits)}; give more of the path")
        raise Error(f"no signal '{name}' in {self.path} (`waves list` shows them)")

    def changes(self, ids: set[str]):
        """(time in seconds, id, value) for the given ids, in time order."""
        t = Fraction(0)
        for line in self.lines:
            line = line.strip()
            if not line:
                continue
            c = line[0]
            if c == "#":
                t = int(line[1:]) * self.timescale
            elif c in "01xzXZ" and line[1:] in ids:
                yield t, line[1:], line[0].lower()
            elif c in "bB":
                value, ident = line[1:].split()
                if ident in ids:
                    yield t, ident, value.lower()

    def close(self):
        self.proc.kill()
        self.proc.wait()


def show(value: str, width: int) -> str:
    """A value as the spec writes it: a bit as 0/1, a bus in hex (0x3C00), x/z as is."""
    if width == 1:
        return value[-1]
    if re.search(r"[xz]", value):
        return "x" if "x" in value else "z"
    return f"0x{int(value, 2):0{(width + 3) // 4}X}"


def cmd_list(a) -> int:
    d = Dump(Path(a.dump))
    for name, (_, width) in d.signals.items():
        print(f"{name}{'' if width == 1 else f' [{width - 1}:0]'}")
    d.close()
    return 0


def cmd_table(a) -> int:
    d = Dump(Path(a.dump))
    if a.clock == "none" or (a.clock is None and not any(n == "clk" or n.endswith(".clk") for n in d.signals)):
        return table_by_change(a, d)
    clock = d.resolve(a.clock or "clk")
    names = [d.resolve(n.strip()) for n in a.signals.split(",") if n.strip()]
    start = seconds(a.start) if a.start else Fraction(0)
    end = seconds(a.end) if a.end else None
    ids = {d.signals[n][0] for n in [clock, *names]}
    clk_id = d.signals[clock][0]
    now: dict[str, str] = {}
    pending: list[tuple[str, str]] = []  # changes at the current time, applied after an edge samples
    rows, cycle, t_cur, prev_clk = [], -1, None, "x"

    def flush():
        for ident, value in pending:
            now[ident] = value
        pending.clear()

    for t, ident, value in d.changes(ids):
        if t != t_cur:
            flush()
            t_cur = t
            if end is not None and t > end:
                break
        if ident == clk_id and prev_clk == "0" and value == "1":
            cycle += 1
            if t >= start:  # the values just before the edge: what the flops sample
                rows.append((cycle, t, [now.get(d.signals[n][0], "x") for n in names]))
        if ident == clk_id:
            prev_clk = value
        pending.append((ident, value))
    d.close()

    unit = "ns"
    head = ["cycle", f"time({unit})", *[n.rsplit(".", 1)[1] for n in names]]
    body = [[str(c), f"{float(t / UNITS[unit]):g}",
             *[show(v, d.signals[n][1]) for v, n in zip(vals, names)]] for c, t, vals in rows]
    widths = [max(len(r[i]) for r in [head, *body]) for i in range(len(head))]
    print(f"# {d.path}: {', '.join(names)}, sampled just before each rising edge of {clock}")
    for r in [head, *body]:
        print("  ".join(x.rjust(w) for x, w in zip(r, widths)))
    if not body:
        print("(no rising edge of the clock in that window)")
    return 0


def table_by_change(a, d: Dump) -> int:
    """No clock (a combinational module): one row per time at which any listed
    signal changes, with the values once that time has settled."""
    names = [d.resolve(n.strip()) for n in a.signals.split(",") if n.strip()]
    start = seconds(a.start) if a.start else Fraction(0)
    end = seconds(a.end) if a.end else None
    ids = {d.signals[n][0] for n in names}
    now: dict[str, str] = {}
    rows, t_cur, changed = [], None, False

    def emit():
        if t_cur is not None and changed and t_cur >= start:
            rows.append((t_cur, [now.get(d.signals[n][0], "x") for n in names]))

    for t, ident, value in d.changes(ids):
        if t != t_cur:
            emit()
            t_cur, changed = t, False
            if end is not None and t > end:
                t_cur = None
                break
        changed |= now.get(ident) != value
        now[ident] = value
    emit()
    d.close()

    unit = "ns"
    head = [f"time({unit})", *[n.rsplit(".", 1)[1] for n in names]]
    body = [[f"{float(t / UNITS[unit]):g}", *[show(v, d.signals[n][1]) for v, n in zip(vals, names)]]
            for t, vals in rows]
    widths = [max(len(r[i]) for r in [head, *body]) for i in range(len(head))]
    print(f"# {d.path}: {', '.join(names)}, one row per change (no clock), values once that time settled")
    for r in [head, *body]:
        print("  ".join(x.rjust(w) for x, w in zip(r, widths)))
    if not body:
        print("(no change of these signals in that window)")
    return 0


# -- images -----------------------------------------------------------------

def load_spec(path: Path, root: Path) -> dict:
    import yaml

    spec = yaml.safe_load(path.read_text())
    if not isinstance(spec, dict):
        raise Error(f"{path}: expected a mapping")
    unknown = set(spec) - {"dump", "run", "signals", "from", "to", "markers", "width"}
    if unknown:
        raise Error(f"{path}: unknown key(s) {', '.join(sorted(unknown))}")
    for key in ("dump", "run", "signals", "from", "to"):
        if key not in spec:
            raise Error(f"{path}: missing '{key}'")
    spec["dump"] = root / spec["dump"]
    return spec


def tcl_script(spec: dict, d: Dump, out: Path) -> str:
    ticks = lambda t: int(seconds(t) / d.timescale)  # noqa: E731
    lines, fmt = [], []
    names = []
    for s in spec["signals"]:
        s = {"name": s} if isinstance(s, str) else s
        full = d.resolve(s["name"])
        names.append(full)
        f = s.get("format", "hex")
        if f not in FORMATS:
            raise Error(f"signal {s['name']}: format '{f}' isn't one of {', '.join(FORMATS)}")
        fmt.append((full, FORMATS[f]))
    lines.append("gtkwave::addSignalsFromList [list " + " ".join(f"{{{n}}}" for n in names) + "]")
    for i, (_, menu) in enumerate(fmt):  # by position: a signal may be shown twice
        lines += ["gtkwave::/Edit/UnHighlight_All", f"gtkwave::setTraceHighlightFromIndex {i} on",
                  f"gtkwave::/Edit/Data_Format/{menu}"]
    lines.append("gtkwave::/Edit/UnHighlight_All")
    for letter, m in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", spec.get("markers") or []):
        label = str(m["label"])
        if re.search(r"[{}\[\]\\$\"]", label):
            raise Error(f"marker label '{label}': no braces, brackets, quotes, $ or backslashes")
        lines.append(f"gtkwave::setNamedMarker {letter} {ticks(m['at'])} {{{label}}}")
    lines.append(f"gtkwave::setZoomRangeTimes {ticks(spec['from'])} {ticks(spec['to'])}")
    lines.append(f"gtkwave::/File/Grab_To_File {{{out}}}")
    lines.append("gtkwave::/File/Quit")
    return "\n".join(lines) + "\n"


def render(spec_path: Path, root: Path, out: Path):
    """Draw one spec into `out` (a PNG)."""
    from PIL import Image

    spec = load_spec(spec_path, root)
    if not spec["dump"].is_file():
        raise Error(f"{spec_path}: no dump at {spec['dump']}. Rerun it first:\n    {spec['run']}")
    d = Dump(spec["dump"])
    n = len(spec["signals"])
    width = int(spec.get("width", 1200))
    height = HEADER + (n + 1) * ROW
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        grab = tmp / "grab.png"
        (tmp / "script.tcl").write_text(tcl_script(spec, d, grab))
        d.close()
        rc = (HERE / "gtkwaverc").read_text() + \
            f"initial_window_x {width}\ninitial_window_y {TOOLBAR + height + 60}\n"
        (tmp / "gtkwaverc").write_text(rc)
        screen = f"-screen 0 {width + 100}x{TOOLBAR + height + 200}x24"
        p = subprocess.run(["xvfb-run", "-a", "-s", screen, "gtkwave", "-M", "-r", str(tmp / "gtkwaverc"),
                            "-S", str(tmp / "script.tcl"), str(spec["dump"])],
                           capture_output=True, text=True, timeout=120, cwd=tmp)
        if not grab.exists():
            msg = "\n".join(line for line in (p.stdout + p.stderr).splitlines() if "FSTLOAD" not in line)
            raise Error(f"{spec_path}: GTKWave drew nothing:\n{msg.strip()}")
        Image.open(grab).crop((0, TOOLBAR, width, TOOLBAR + height)).save(out, optimize=False)


def png_of(spec_path: Path) -> Path:
    return spec_path.with_name(spec_path.name.removesuffix(".waves.yaml") + ".png")


def cmd_png(a) -> int:
    root = Path(os.environ.get("BANKSIDE_REPO", ".")).resolve()
    specs = []
    for p in map(Path, a.paths):
        if p.is_dir():
            specs += sorted(p.rglob("*.waves.yaml"))
        elif p.name.endswith(".waves.yaml"):
            specs.append(p)
        else:
            raise Error(f"{p}: a spec is named <name>.waves.yaml")
    if not specs:
        raise Error("no *.waves.yaml found")
    bad = 0
    for s in specs:
        out = png_of(s)
        if not a.check:
            render(s, root, out)
            print(f"wrote {out}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "fresh.png"
            try:
                render(s, root, fresh)
            except Error as e:
                print(f"CANNOT CHECK {s}: {e}")
                bad += 1
                continue
            if not out.exists():
                print(f"MISSING {out}")
                bad += 1
            elif out.read_bytes() != fresh.read_bytes():
                print(f"STALE   {out}: doesn't match {s.name} (rerun `waves png {s}`)")
                bad += 1
            else:
                print(f"ok      {out}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="waves", description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    li = sub.add_parser("list", help="the signals in a dump")
    li.add_argument("dump")
    li.set_defaults(fn=cmd_list)
    t = sub.add_parser("table", help="signal values at each clock edge, as text")
    t.add_argument("dump")
    t.add_argument("--signals", required=True, help="comma-separated names (a unique ending of the path is enough)")
    t.add_argument("--clock", help="the clock to sample on (default clk); 'none', or a dump without clk: "
                   "a row at each change instead")
    t.add_argument("--from", dest="start", help="first time, e.g. 50ns (default: the start)")
    t.add_argument("--to", dest="end", help="last time (default: the end)")
    t.set_defaults(fn=cmd_table)
    p = sub.add_parser("png", help="GTKWave images from *.waves.yaml specs")
    p.add_argument("paths", nargs="+", help="specs, or folders to search for them")
    p.add_argument("--check", action="store_true", help="redraw into a temp file and compare, write nothing")
    p.set_defaults(fn=cmd_png)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Error as e:
        print(f"waves: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
