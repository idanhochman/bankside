"""Synthesize one bankside module with ORFS on ASAP7 (the synth skill).

Runs inside the ORFS image; call it through ./synth. Reads the module's
filelist (rtl/<module>.f), the common orfs.mk and constraint.sdc next to this
script, and the module's own syn/orfs.mk or syn/constraint.sdc if it has them.
Works in /work (the repo's synth/<module>/). Writes /work/ppa.yaml; the
wrapper copies it into the module's syn/ after a full run at the spec clock.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path("/work")
ORFS = Path("/OpenROAD-flow-scripts")
SPEC_CLOCK_PS = 3333  # [TOP-ARCH-3]


class Error(Exception):
    pass


def read_filelist(path: Path, seen=None) -> tuple[list[Path], list[Path], list[str]]:
    """Verilator-style filelist: source files, -F nested lists, +incdir+, +define+.
    Paths are relative to the list's own folder; // and # start comments."""
    seen = seen or set()
    if path in seen:
        raise Error(f"{path}: the filelists include each other")
    seen.add(path)
    if not path.is_file():
        raise Error(f"no filelist at {path}")
    files, incdirs, defines = [], [], []
    words = []
    for line in path.read_text().splitlines():
        line = re.split(r"//|#", line, maxsplit=1)[0]
        words += line.split()
    it = iter(words)
    for w in it:
        if w == "-F":
            f, i, d = read_filelist((path.parent / next(it)).resolve(), seen)
            files += f
            incdirs += i
            defines += d
        elif w.startswith("+incdir+"):
            incdirs += [(path.parent / p).resolve() for p in w[8:].split("+") if p]
        elif w.startswith("+define+"):
            defines += [d for d in w[8:].split("+") if d]
        elif w.startswith(("-", "+")):
            raise Error(f"{path}: '{w}' isn't supported here (only files, -F, +incdir+, +define+)")
        else:
            f = (path.parent / w).resolve()
            if not f.is_file():
                raise Error(f"{path}: no file {f}")
            files.append(f)
    return files, incdirs, defines


def toplevel(mod_dir: Path, module: str) -> str:
    y = mod_dir / "opendv.yaml"
    if y.is_file():
        m = re.search(r"^toplevel:\s*([A-Za-z_]\w*)", y.read_text(), re.M)
        if m:
            return m.group(1)
    return module


def metrics(stage_json: str) -> dict:
    hits = list((WORK / "logs").rglob(stage_json))
    return json.loads(hits[0].read_text()) if hits else {}


def mode() -> str:
    for log in (WORK / "logs").rglob("*.log"):
        m = re.search(r"bankside-sdc: (clocked|combinational)", log.read_text(errors="replace"))
        if m:
            return m.group(1)
    return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="synth", description=__doc__.split("\n\n")[0])
    ap.add_argument("module")
    ap.add_argument("--quick", action="store_true", help="synthesis and a pre-placement timing estimate only")
    ap.add_argument("--clock-ps", type=int, help=f"explore another clock period (default {SPEC_CLOCK_PS})")
    a = ap.parse_args(argv)
    repo = Path(os.environ["BANKSIDE_REPO"])
    mod = repo / "src" / a.module
    try:
        if not mod.is_dir():
            raise Error(f"no module src/{a.module}")
        files, incdirs, defines = read_filelist(mod / "rtl" / f"{a.module}.f")
        if not files:
            raise Error(f"src/{a.module}/rtl/{a.module}.f lists no source file yet")
        top = toplevel(mod, a.module)
        syn = mod / "syn"
        sdc = syn / "constraint.sdc" if (syn / "constraint.sdc").is_file() else HERE / "constraint.sdc"
        own_mk = syn / "orfs.mk"
        clock = a.clock_ps or SPEC_CLOCK_PS

        for d in ("logs", "objects", "reports", "results"):
            shutil.rmtree(WORK / d, ignore_errors=True)
        (WORK / "ppa.yaml").unlink(missing_ok=True)
        cfg = WORK / "config.mk"
        cfg.write_text("\n".join([
            "# Written by the synth skill for this run.",
            f"export DESIGN_NAME     = {top}",
            f"export DESIGN_NICKNAME = {a.module}",
            "export VERILOG_FILES   = " + " ".join(map(str, files)),
            "export VERILOG_INCLUDE_DIRS = " + " ".join(map(str, incdirs)),
            "export VERILOG_DEFINES = " + " ".join(f"-D{d}" for d in defines),
            f"export SDC_FILE        = {sdc}",
            *([f"include {own_mk}"] if own_mk.is_file() else []),
            f"include {HERE / 'orfs.mk'}",
            "",
        ]))
        target = "floorplan" if a.quick else "finish"
        print(f"synth {a.module} ({top}): {'quick' if a.quick else 'full flow'}, clock {clock} ps, "
              f"{len(files)} source file(s)\n  work: {os.environ.get('BANKSIDE_WORK', WORK)}", flush=True)
        env = {**os.environ, "BANKSIDE_CLOCK_PS": str(clock)}
        t0 = time.monotonic()
        with open(WORK / "flow.log", "w") as log:
            p = subprocess.run(["bash", "-c", f"source {ORFS}/env.sh >/dev/null 2>&1 && "
                                f"make -C {ORFS}/flow DESIGN_CONFIG={cfg} WORK_HOME={WORK} {target}"],
                               stdout=log, stderr=subprocess.STDOUT, env=env)
        secs = time.monotonic() - t0
        if p.returncode:
            tail = "\n".join((WORK / "flow.log").read_text(errors="replace").splitlines()[-30:])
            raise Error(f"the flow failed after {secs:.0f} s; the end of {WORK / 'flow.log'}:\n{tail}")

        synth = metrics("1_synth.json")
        kind = mode()
        if a.quick:
            m, pre = metrics("2_1_floorplan.json"), "floorplan__"
        else:
            m, pre = metrics("6_report.json"), "finish__"
        get = lambda k, d=None: m.get(pre + k, d)  # noqa: E731
        ws = get("timing__setup__ws")
        timing = {"setup_slack_ps": round(ws, 1) if ws is not None else None}
        if kind == "combinational":
            timing["delay_ps"] = round(clock - ws, 1) if ws is not None else None
        else:
            hold = get("timing__hold__ws")
            timing["hold_slack_ps"] = round(hold, 1) if hold is not None else None
            fmax = get("timing__fmax")
            timing["fmax_mhz"] = round(fmax / 1e6) if fmax else None
        ppa = {
            "module": a.module,
            "toplevel": top,
            "flow": "quick" if a.quick else "full",
            "commit": os.environ.get("BANKSIDE_COMMIT", "unknown"),
            "clean": os.environ.get("BANKSIDE_CLEAN") == "1",
            "orfs": os.environ.get("BANKSIDE_ORFS", "unknown"),
            "platform": "asap7",
            "kind": kind,
            "clock_ps": clock,
            "constraint": "own" if sdc.parent == syn else "common",
            "settings": "own + common" if own_mk.is_file() else "common",
            "area_um2": {"cells_after_synth": round(synth.get("synth__design__instance__area__stdcell", 0), 1),
                         "cells": round(get("design__instance__area__stdcell", 0), 1)},
            "cells": {"after_synth": synth.get("synth__design__instance__count__stdcell")},
            "timing": timing,
        }
        if not a.quick:
            ppa["area_um2"]["die"] = round(get("design__die__area", 0), 1)
            ppa["cells"].update(total=get("design__instance__count__stdcell"),
                                flops=get("design__instance__count__class:sequential_cell", 0),
                                timing_buffers=get("design__instance__count__class:timing_repair_buffer", 0))
            power = get("power__total")
            ppa["power_mw"] = {"total": round(power * 1e3, 3) if power is not None else None,
                               "activity": "default"}
            drc = metrics("5_2_route.json").get("detailedroute__route__drc_errors")
            ppa["drc_violations"] = drc
        ppa["runtime_s"] = round(secs)
        write_yaml(WORK / "ppa.yaml", ppa)
        print((WORK / "ppa.yaml").read_text())
        return 0
    except Error as e:
        print(f"synth: {e}", file=sys.stderr)
        return 2


def write_yaml(path: Path, d: dict):
    import yaml

    head = ("# Written by .claude/skills/synth/scripts/synth. Don't edit.\n"
            "# power_mw.activity default: OpenSTA's guess (inputs toggle on 10% of cycles), not a simulation.\n")
    path.write_text(head + yaml.safe_dump(d, sort_keys=False, default_flow_style=False))


if __name__ == "__main__":
    sys.exit(main())
