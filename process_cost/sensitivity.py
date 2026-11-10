"""One-at-a-time sensitivity of cost per part (tornado-style ordering)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable

from .cost import estimate
from .models import InputError, Job

# key, label, unit, getter, setter(job, new_value) -> job
_Param = tuple[str, str, str, Callable[[Job], float], Callable[[Job, float], Job]]


def _set(field: str) -> Callable[[Job, float], Job]:
    return lambda job, v: dataclasses.replace(job, **{field: v})


def _set_feed(job: Job, v: float) -> Job:
    g = job.geometry
    name = "feed_mm_rev" if job.kind == "turning" else "feed_mm_tooth"
    return dataclasses.replace(job, geometry=dataclasses.replace(g, **{name: v}))


PARAMS: tuple[_Param, ...] = (
    ("Vc", "cutting speed Vc", "m/min", lambda j: j.vc_m_min, _set("vc_m_min")),
    ("feed", "feed (f or fz)", "",lambda j: j.geometry.feed, _set_feed),
    ("Co", "machine rate Co", "$/h", lambda j: j.machine_rate_h, _set("machine_rate_h")),
    ("Ts", "setup time Ts", "min", lambda j: j.setup_min, _set("setup_min")),
    ("Ce", "cost per edge Ce", "$", lambda j: j.cost_per_edge, _set("cost_per_edge")),
    ("Tt", "tool change time Tt", "min", lambda j: j.tool_change_min, _set("tool_change_min")),
    ("Th", "handling time Th", "min", lambda j: j.handling_min, _set("handling_min")),
    ("Cm", "material cost Cm", "$", lambda j: j.material_cost, _set("material_cost")),
    ("Q", "batch size Q", "parts", lambda j: j.batch_size, _set("batch_size")),
    ("n", "Taylor n (C fixed)", "-", lambda j: j.taylor_n, _set("taylor_n")),
)


@dataclass(frozen=True)
class SensRow:
    key: str
    label: str
    unit: str
    base_value: float
    costs: tuple[float | None, ...]     # cost per part at each step
    changes: tuple[float | None, ...]   # % change vs base at each step

    @property
    def impact(self) -> float:
        vals = [abs(c) for c in self.changes if c is not None]
        return max(vals) if vals else 0.0


@dataclass(frozen=True)
class Sensitivity:
    job_name: str
    base_cost: float
    steps: tuple[float, ...]   # percent, e.g. (-20, -10, 10, 20)
    rows: tuple[SensRow, ...]  # sorted by impact, largest first


def steps_for(step_pct: float) -> tuple[float, ...]:
    if not 0 < step_pct < 50:
        raise InputError(f"--step must be > 0 and < 50 percent (got {step_pct:g})")
    return (-2 * step_pct, -step_pct, step_pct, 2 * step_pct)


def _cost_or_none(job: Job) -> float | None:
    if not 0 < job.taylor_n < 1:
        return None
    try:
        return estimate(job).cost_per_part
    except OverflowError:  # extreme Taylor life, treated as not computable
        return None


def sensitivity(job: Job, step_pct: float = 10.0) -> Sensitivity:
    steps = steps_for(step_pct)
    base = estimate(job).cost_per_part
    rows = []
    for key, label, unit, get, put in PARAMS:
        v0 = get(job)
        costs, changes = [], []
        for p in steps:
            new = v0 * (1 + p / 100.0)
            if key in ("Vc", "feed", "Co", "Q") and not new > 0:
                c = None
            else:
                c = _cost_or_none(put(job, new))
            costs.append(c)
            changes.append(None if c is None else 100.0 * (c - base) / base)
        if key == "feed":
            unit = job.feed_unit
        rows.append(SensRow(key, label, unit, v0, tuple(costs), tuple(changes)))
    rows.sort(key=lambda r: r.impact, reverse=True)  # stable: ties keep PARAMS order
    return Sensitivity(job.name, base, steps, tuple(rows))
