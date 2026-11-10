"""Cycle time and cost per part (Groover-style), plus optimum cutting speeds."""

from __future__ import annotations

from dataclasses import dataclass

from . import formulas
from .models import Job, MillingGeometry, TurningGeometry


@dataclass(frozen=True)
class Estimate:
    job: Job
    vc_requested: float      # m/min
    vc_effective: float      # m/min, after spindle cap
    n_rpm: float
    vf_mm_min: float
    feed_effective: float    # mm/rev or mm/tooth after feed cap
    passes: int
    length_per_pass_mm: float
    tm_min: float            # cutting time per part
    tool_life_min: float     # Taylor T at vc_effective
    edges_per_part: float    # Tm/T
    tp_min: float            # time per piece started: Th + Tm + (Tm/T)*Tt
    mrr_mm3_min: float | None
    # cost per GOOD part, $ (variable items already divided by (1 - scrap))
    cost_machining: float    # Co*(Th + Tm)/60
    cost_tool_change: float  # Co*(Tm/T)*Tt/60
    cost_tooling: float      # (Tm/T)*Ce
    cost_material: float     # Cm
    cost_setup: float        # F/Q
    fixed_per_batch: float   # F = Ts/60*Cs
    variable_per_part: float  # v: cost per good part excluding setup
    cost_per_part: float
    batch_size: float
    parts_started: float     # Q/(1 - s)
    batch_time_min: float    # Ts + parts_started*tp
    batch_cost: float        # F + v*Q
    warnings: tuple[str, ...]

    def split(self) -> dict[str, float]:
        """Cost split per good part, percent of cost_per_part."""
        items = {
            "setup": self.cost_setup,
            "machining": self.cost_machining,
            "tool change": self.cost_tool_change,
            "tooling": self.cost_tooling,
            "material": self.cost_material,
        }
        total = self.cost_per_part
        return {k: (100.0 * v / total if total > 0 else 0.0) for k, v in items.items()}


def estimate(job: Job, vc: float | None = None, batch_size: float | None = None) -> Estimate:
    """Estimate one job. `vc` overrides the cutting speed (feed held), `batch_size` overrides Q."""
    vc_req = job.vc_m_min if vc is None else vc
    q = job.batch_size if batch_size is None else batch_size
    if not q > 0:
        raise ValueError(f"batch size must be > 0 (got {q})")
    g = job.geometry
    warnings: list[str] = []

    d = g.mean_diameter_mm if isinstance(g, TurningGeometry) else g.tool_diameter_mm
    n_rpm = formulas.spindle_speed_rpm(vc_req, d)
    vc_eff = vc_req
    if job.spindle_max_rpm is not None and n_rpm > job.spindle_max_rpm:
        n_rpm = job.spindle_max_rpm
        vc_eff = formulas.cutting_speed_m_min(n_rpm, d)
        warnings.append(
            f"spindle capped at {n_rpm:g} rpm: Vc reduced from {vc_req:.1f} to {vc_eff:.1f} m/min")

    if isinstance(g, TurningGeometry):
        vf = formulas.feed_rate_turning(g.feed_mm_rev, n_rpm)
        per_rev = n_rpm
    else:
        assert isinstance(g, MillingGeometry)
        vf = formulas.feed_rate_milling(g.feed_mm_tooth, g.teeth, n_rpm)
        per_rev = n_rpm * g.teeth
    feed_eff = g.feed
    if job.feed_max_mm_min is not None and vf > job.feed_max_mm_min:
        warnings.append(
            f"feed rate capped at {job.feed_max_mm_min:g} mm/min (requested {vf:.0f} mm/min)")
        vf = job.feed_max_mm_min
        feed_eff = vf / per_rev
        warnings[-1] += f": effective feed {feed_eff:.4f} {job.feed_unit}"

    passes = g.passes
    lpp = g.length_per_pass_mm
    tm = formulas.cutting_time_min(passes, lpp, vf)
    t_life = formulas.taylor_tool_life(vc_eff, job.taylor_c, job.taylor_n)
    edges = tm / t_life
    tp = job.handling_min + tm + edges * job.tool_change_min

    if isinstance(g, TurningGeometry):
        mrr = formulas.mrr_turning(vc_eff, feed_eff, min(g.ap_mm, (g.d0_mm - g.d1_mm) / 2.0))
    elif g.ap_mm is not None and g.ae_mm is not None:
        mrr = formulas.mrr_milling(g.ap_mm, g.ae_mm, vf)
    else:
        mrr = None

    good = 1.0 - job.scrap_rate
    co_min = job.machine_rate_h / 60.0
    c_mach = co_min * (job.handling_min + tm) / good
    c_tc = co_min * edges * job.tool_change_min / good
    c_tool = edges * job.cost_per_edge / good
    c_mat = job.material_cost / good
    fixed = job.setup_min / 60.0 * job.setup_rate_h
    variable = c_mach + c_tc + c_tool + c_mat
    started = q / good
    return Estimate(
        job=job, vc_requested=vc_req, vc_effective=vc_eff, n_rpm=n_rpm, vf_mm_min=vf,
        feed_effective=feed_eff, passes=passes, length_per_pass_mm=lpp, tm_min=tm,
        tool_life_min=t_life, edges_per_part=edges, tp_min=tp, mrr_mm3_min=mrr,
        cost_machining=c_mach, cost_tool_change=c_tc, cost_tooling=c_tool, cost_material=c_mat,
        cost_setup=fixed / q, fixed_per_batch=fixed, variable_per_part=variable,
        cost_per_part=variable + fixed / q, batch_size=q, parts_started=started,
        batch_time_min=job.setup_min + started * tp, batch_cost=fixed + variable * q,
        warnings=tuple(warnings))


@dataclass(frozen=True)
class OptimumSpeed:
    label: str
    tool_life_min: float | None
    vc_m_min: float | None
    estimate: Estimate | None
    reason: str = ""


def optimum_speeds(job: Job) -> tuple[OptimumSpeed, OptimumSpeed]:
    """Speeds for minimum cost and maximum production rate (feed held constant)."""
    n, c = job.taylor_n, job.taylor_c
    out = []
    for label, t in (
        ("min cost", formulas.min_cost_tool_life(n, job.tool_change_min, job.cost_per_edge,
                                                 job.machine_rate_h)),
        ("max production rate", formulas.max_rate_tool_life(n, job.tool_change_min)),
    ):
        if t is None:
            if not 0 < n < 1:
                why = f"undefined: Taylor n = {n:g} is not in (0, 1)"
            elif label == "max production rate":
                why = "undefined: tool change time Tt = 0 gives unbounded speed"
            else:
                why = "undefined: Tt = 0 and Ce = 0 give unbounded speed"
            out.append(OptimumSpeed(label, None, None, None, why))
            continue
        v = formulas.taylor_speed(t, c, n)
        out.append(OptimumSpeed(label, t, v, estimate(job, vc=v)))
    return out[0], out[1]
