"""Break-even batch size between two scenarios with linear batch cost F + v*Q."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .cost import estimate
from .models import Job, Outsource, Scenario

# Log-spaced batch sizes for the comparison table and charts.
BATCH_SIZES = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000)


@dataclass(frozen=True)
class Line:
    """Batch cost model: total(Q) = fixed + variable*Q; cost per part = fixed/Q + variable."""
    name: str
    fixed: float      # $ per batch (setup cost or outsource fixed fee)
    variable: float   # $ per good part

    def total(self, q: float) -> float:
        return self.fixed + self.variable * q

    def per_part(self, q: float) -> float:
        return self.fixed / q + self.variable


def line_for(scenario: Scenario) -> Line:
    if isinstance(scenario, Outsource):
        return Line(scenario.name, scenario.fixed_fee, scenario.price_per_part)
    assert isinstance(scenario, Job)
    est = estimate(scenario)
    return Line(scenario.name, est.fixed_per_batch, est.variable_per_part)


@dataclass(frozen=True)
class BreakEven:
    a: Line
    b: Line
    kind: str                 # "crossing" | "dominant" | "parallel" | "identical"
    q_star: float | None      # algebraic break-even (may be <= 0 or < 1)
    q_min: int | None         # smallest integer Q where the at-scale option is strictly cheaper
    small_winner: str | None  # cheaper below the break-even
    scale_winner: str | None  # cheaper above the break-even (lower variable cost)
    message: str


def _strictly_less(x: float, y: float) -> bool:
    return x < y - 1e-9 * max(1.0, abs(x), abs(y))


def breakeven(a: Line, b: Line) -> BreakEven:
    """Q* = (F_A - F_B)/(v_B - v_A), with explicit handling of the degenerate cases."""
    dv = b.variable - a.variable
    df = a.fixed - b.fixed
    scale_tol = 1e-12 * max(1.0, abs(a.variable), abs(b.variable))
    if abs(dv) <= scale_tol:
        if abs(df) <= 1e-12 * max(1.0, abs(a.fixed), abs(b.fixed)):
            return BreakEven(a, b, "identical", None, None, None, None,
                             "identical cost lines: no difference at any batch size")
        win = a if a.fixed < b.fixed else b
        return BreakEven(a, b, "parallel", None, None, win.name, win.name,
                         f"parallel cost lines (same variable cost): no break-even; "
                         f"{win.name} is cheaper at every batch size")

    q_star = df / dv
    scale, small = (a, b) if a.variable < b.variable else (b, a)

    q = max(1, math.floor(q_star)) if q_star > 0 else 1
    while not _strictly_less(scale.total(q), small.total(q)):
        q += 1
    # verify the step below is not already strictly cheaper (guards rounding)
    while q > 1 and _strictly_less(scale.total(q - 1), small.total(q - 1)):
        q -= 1

    if q == 1:
        if q_star <= 0:
            why = f"Q* = {q_star:.2f} <= 0"
        else:
            why = f"Q* = {q_star:.2f} is below one part"
        return BreakEven(a, b, "dominant", q_star, 1, scale.name, scale.name,
                         f"{why}: {scale.name} is cheaper at every batch size")
    return BreakEven(
        a, b, "crossing", q_star, q, small.name, scale.name,
        f"break-even Q* = {q_star:.2f} parts: {small.name} is cheaper below, "
        f"{scale.name} is cheaper from Q = {q} parts")


def comparison_sizes(be: BreakEven) -> list[int]:
    sizes = set(BATCH_SIZES)
    if be.kind == "crossing" and be.q_min is not None:
        sizes.add(be.q_min)
        sizes.add(be.q_min - 1)
    return sorted(s for s in sizes if s >= 1)
