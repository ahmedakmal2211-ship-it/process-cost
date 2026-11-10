"""Plain-text formatting: aligned tables with units in headers (ASCII only)."""

from __future__ import annotations

from .breakeven import BreakEven, Line, comparison_sizes
from .charts import ascii_chart
from .cost import Estimate, OptimumSpeed
from .materials import INDICATIVE_NOTE, MATERIALS, TABLE, TOOL_MATERIALS
from .models import Outsource, TurningGeometry
from .sensitivity import Sensitivity


def table(headers: list[str], rows: list[list[str]], align: str | None = None) -> str:
    """Aligned text table. `align` is one char per column: 'l' or 'r' (default: first l, rest r)."""
    align = align or ("l" + "r" * (len(headers) - 1))
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]

    def fmt(cells):
        return "  ".join(str(c).ljust(w) if a == "l" else str(c).rjust(w)
                         for c, w, a in zip(cells, widths, align)).rstrip()

    lines = [fmt(headers), "  ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows]
    return "\n".join(lines)


def heading(text: str, ch: str = "=") -> str:
    return f"{text}\n{ch * len(text)}"


def money(x: float) -> str:
    return f"{x:,.2f}"


def format_estimate(est: Estimate, optimum: tuple[OptimumSpeed, OptimumSpeed]) -> str:
    j = est.job
    g = j.geometry
    out = [heading(f"Estimate: {j.name}", "-")]
    if isinstance(g, TurningGeometry):
        op = (f"turning D0 {g.d0_mm:g} -> D1 {g.d1_mm:g} mm, L {g.length_mm:g} mm, "
              f"ap {g.ap_mm:g} mm, f {g.feed_mm_rev:g} mm/rev (Dm = {g.mean_diameter_mm:g} mm)")
    else:
        op = (f"milling D {g.tool_diameter_mm:g} mm, z {g.teeth}, fz {g.feed_mm_tooth:g} mm/tooth, "
              f"Lc {g.cut_length_mm:g} mm x {g.passes} passes")
    out.append(f"Operation : {op}")
    out.append(f"Material  : {MATERIALS.get(j.material, j.material)} / "
               f"{TOOL_MATERIALS.get(j.tool_material, j.tool_material)}")
    out.append(f"Taylor    : n = {j.taylor_n:g}, C = {j.taylor_c:.1f}   Batch Q = {est.batch_size:g} good parts"
               + (f", scrap {100 * j.scrap_rate:g}%" if j.scrap_rate else ""))
    for note in j.notes:
        out.append(f"Note      : {note}")
    for w in est.warnings:
        out.append(f"WARNING   : {w}")
    out.append("")
    mrr = "-" if est.mrr_mm3_min is None else f"{est.mrr_mm3_min:,.0f}"
    out.append(table(
        ["Cutting", "Value", "Unit"],
        [["cutting speed Vc", f"{est.vc_effective:.1f}", "m/min"],
         ["spindle speed n", f"{est.n_rpm:.1f}", "rpm"],
         ["feed rate vf", f"{est.vf_mm_min:.1f}", "mm/min"],
         ["passes N", f"{est.passes}", "-"],
         ["length per pass", f"{est.length_per_pass_mm:.1f}", "mm"],
         ["cutting time Tm", f"{est.tm_min:.3f}", "min"],
         ["tool life T", f"{est.tool_life_min:.1f}", "min"],
         ["edges per part Tm/T", f"{est.edges_per_part:.4f}", "-"],
         ["material removal rate", mrr, "mm^3/min"],
         ["cycle time per part tp", f"{est.tp_min:.3f}", "min"],
         ["batch time Ts + Q*tp/(1-s)", f"{est.batch_time_min:.1f}", "min"],
         ["batch time", f"{est.batch_time_min / 60:.2f}", "h"]],
        "lrl"))
    out.append("")
    split = est.split()
    rows = [[k, money(v), f"{split[k]:.1f}"] for k, v in (
        ("setup", est.cost_setup), ("machining", est.cost_machining),
        ("tool change", est.cost_tool_change), ("tooling", est.cost_tooling),
        ("material", est.cost_material))]
    rows.append(["cost per part", money(est.cost_per_part), "100.0"])
    out.append(table(["Cost per good part", "$/part", "%"], rows))
    out.append(f"Batch cost: ${money(est.batch_cost)}  (setup ${money(est.fixed_per_batch)} "
               f"+ variable ${money(est.variable_per_part)}/part x {est.batch_size:g})")
    out.append("")
    rows = [["your Vc", f"{est.vc_effective:.1f}", f"{est.tool_life_min:.1f}",
             f"{est.tp_min:.3f}", money(est.cost_per_part)]]
    notes = []
    for o in optimum:
        if o.estimate is None:
            rows.append([o.label, "undefined", "-", "-", "-"])
            notes.append(f"{o.label}: {o.reason}")
        else:
            e = o.estimate
            rows.append([o.label, f"{e.vc_effective:.1f}", f"{e.tool_life_min:.1f}",
                         f"{e.tp_min:.3f}", money(e.cost_per_part)])
            if e.warnings:
                notes.append(f"{o.label}: ideal Vc {o.vc_m_min:.1f} m/min limited by machine caps")
    out.append(table(["Speed (feed held)", "Vc m/min", "T min", "tp min", "$/part"], rows))
    out.extend(f"  {n}" for n in notes)
    return "\n".join(out)


def format_outsource(o: Outsource) -> str:
    q = o.batch_size
    per = o.fixed_fee / q + o.price_per_part
    return "\n".join([
        heading(f"Outsource: {o.name}", "-"),
        f"Price ${money(o.price_per_part)}/part + fixed fee ${money(o.fixed_fee)} per order",
        f"At Q = {q:g}: ${money(per)}/part, ${money(o.fixed_fee + o.price_per_part * q)} per batch",
    ])


def format_breakeven(be: BreakEven) -> str:
    a, b = be.a, be.b
    out = [heading("Break-even batch size", "-")]
    out.append(table(["Scenario", "Fixed F $/batch", "Variable v $/part"],
                     [[ln.name, money(ln.fixed), money(ln.variable)] for ln in (a, b)]))
    out.append("Q* = (F_A - F_B)/(v_B - v_A)")
    out.append(f"Result: {be.message}")
    if be.kind == "crossing":
        q = be.q_min
        out.append(f"Check : Q = {q - 1}: A ${money(a.per_part(q - 1))} vs B ${money(b.per_part(q - 1))}/part; "
                   f"Q = {q}: A ${money(a.per_part(q))} vs B ${money(b.per_part(q))}/part")
    out.append("")
    rows = []
    for q in comparison_sizes(be):
        ca, cb = a.per_part(q), b.per_part(q)
        cheaper = a.name if ca < cb else (b.name if cb < ca else "equal")
        mark = "  <- break-even" if be.kind == "crossing" and q == be.q_min else ""
        rows.append([str(q), money(ca), money(cb), cheaper + mark])
    out.append(table(["Q parts", f"A {a.name} $/part", f"B {b.name} $/part", "cheaper"], rows, "rrrl"))
    out.append("")
    q_mark = be.q_star if be.kind == "crossing" else None
    out.append(ascii_chart([a, b], q_mark))
    return "\n".join(out)


def format_sensitivity(s: Sensitivity) -> str:
    out = [heading(f"Sensitivity: {s.job_name}", "-"),
           f"Base cost per part ${money(s.base_cost)}; one factor varied at a time "
           f"(Taylor C fixed); sorted by largest |change|."]
    headers = ["Parameter", "Base", "Unit"]
    for p in s.steps:
        headers.append(f"{p:+g}% $/part")
        headers.append("chg %")
    rows = []
    for r in s.rows:
        row = [r.label, f"{r.base_value:g}", r.unit]
        for c, d in zip(r.costs, r.changes):
            row += (["n/a", "n/a"] if c is None else [money(c), f"{(d if round(d, 1) != 0 else 0.0):+.1f}"])
        rows.append(row)
    out.append(table(headers, rows, "lrl" + "r" * (2 * len(s.steps))))
    return "\n".join(out)


def format_materials() -> str:
    rows = []
    for (mat, tool), d in TABLE.items():
        rows.append([mat, tool, f"{d.vc_turning:g}", f"{d.vc_milling:g}", f"{d.f_turning:g}",
                     f"{d.fz_milling:g}", f"{d.taylor_n:g}", f"{d.t_ref:g}"])
    return "\n".join([
        heading("Indicative cutting data"),
        INDICATIVE_NOTE,
        "",
        table(["material", "tool_material", "Vc turn m/min", "Vc mill m/min", "f mm/rev",
               "fz mm/tooth", "Taylor n", "T_ref min"], rows, "llrrrrrr"),
        "",
        "Taylor C = Vc_rec * T_ref^n per operation. 'custom' material needs Vc, taylor_n and taylor_C.",
    ])


def lines_title(lines: list[Line]) -> str:
    return " vs ".join(ln.name for ln in lines)
