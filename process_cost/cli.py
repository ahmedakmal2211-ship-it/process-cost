"""Command-line interface: estimate, breakeven, sensitivity, report, materials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .breakeven import breakeven, line_for
from .charts import svg_chart
from .cost import estimate, optimum_speeds
from .models import InputError, JobFile, Outsource, load_job_file
from .report import (format_breakeven, format_estimate, format_materials, format_outsource,
                     format_sensitivity, heading, lines_title)
from .sensitivity import sensitivity, steps_for

COMMANDS = ("estimate", "breakeven", "sensitivity", "report", "materials")


def _header(jf: JobFile) -> str:
    return heading(f"process-cost {__version__}: {jf.title}")


def _estimate_text(jf: JobFile) -> str:
    parts = []
    for sc in jf.scenarios:
        if isinstance(sc, Outsource):
            parts.append(format_outsource(sc))
        else:
            parts.append(format_estimate(estimate(sc), optimum_speeds(sc)))
    return "\n\n".join(parts)


def _breakeven(jf: JobFile, svg: str | None):
    if len(jf.scenarios) != 2:
        raise InputError(
            f"break-even needs exactly 2 scenarios in 'scenarios' (found {len(jf.scenarios)})")
    a, b = (line_for(s) for s in jf.scenarios)
    be = breakeven(a, b)
    text = format_breakeven(be)
    if svg:
        q = be.q_star if be.kind == "crossing" else None
        Path(svg).write_text(svg_chart([a, b], q, f"Cost per part: {lines_title([a, b])}"),
                             encoding="utf-8")
        text += f"\n\nSVG chart written to {svg}"
    return text


def _sensitivity_text(jf: JobFile, step: float) -> str:
    jobs = jf.jobs
    if not jobs:
        raise InputError("sensitivity needs at least one machining scenario")
    return "\n\n".join(format_sensitivity(sensitivity(j, step)) for j in jobs)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="process-cost",
        description="Turning and milling cycle time and cost per part from speeds and feeds, "
                    "Taylor tool life, setup and batch size. Indicative data only.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in (("estimate", "cycle time, cost per part and optimum speeds"),
                            ("breakeven", "break-even batch size between 2 scenarios"),
                            ("sensitivity", "one-at-a-time sensitivity table"),
                            ("report", "estimate + break-even + sensitivity")):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("job", help="job file (JSON)")
        if name in ("breakeven", "report"):
            sp.add_argument("--svg", metavar="FILE", help="also write an SVG chart of cost per part vs Q")
        if name in ("sensitivity", "report"):
            sp.add_argument("--step", type=float, default=10.0,
                            help="percent step; table uses -2s, -s, +s, +2s (default 10)")
    sub.add_parser("materials", help="list the indicative cutting data table")
    return p


def run(argv: list[str]) -> str:
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["report", *argv]  # `process-cost job.json` == `process-cost report job.json`
    args = build_parser().parse_args(argv)
    if args.command == "materials":
        return format_materials()
    if hasattr(args, "step"):
        steps_for(args.step)  # validate before doing any work
    jf = load_job_file(args.job)
    head = _header(jf)
    if args.command == "estimate":
        return f"{head}\n\n{_estimate_text(jf)}"
    if args.command == "breakeven":
        return f"{head}\n\n{_breakeven(jf, args.svg)}"
    if args.command == "sensitivity":
        return f"{head}\n\n{_sensitivity_text(jf, args.step)}"
    if args.svg and len(jf.scenarios) != 2:
        raise InputError(f"--svg needs exactly 2 scenarios (found {len(jf.scenarios)})")
    parts = [head, _estimate_text(jf)]
    if len(jf.scenarios) == 2:
        parts.append(_breakeven(jf, args.svg))
    else:
        parts.append("(break-even skipped: needs exactly 2 scenarios)")
    parts.append(_sensitivity_text(jf, args.step))
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # non-ASCII names on cp1252 consoles
        except (AttributeError, ValueError):
            pass
    try:
        print(run(sys.argv[1:] if argv is None else argv))
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
