"""Pure machining formulas. Units: mm, m/min, rpm, mm/rev, mm/min, min, $/h.

No validation of business rules here beyond guarding against division by zero;
input validation lives in models.py.
"""

from __future__ import annotations

import math

_CEIL_TOL = 1e-9


def _pos(name: str, value: float) -> None:
    if not value > 0:
        raise ValueError(f"{name} must be > 0 (got {value})")


def spindle_speed_rpm(vc_m_min: float, d_mm: float) -> float:
    """n = 1000*Vc/(pi*D)  [rpm]."""
    _pos("Vc", vc_m_min)
    _pos("D", d_mm)
    return 1000.0 * vc_m_min / (math.pi * d_mm)


def cutting_speed_m_min(n_rpm: float, d_mm: float) -> float:
    """Inverse of spindle_speed_rpm: Vc = pi*D*n/1000  [m/min]."""
    return math.pi * d_mm * n_rpm / 1000.0


def mean_diameter(d0_mm: float, d1_mm: float) -> float:
    """Mean diameter of cut Dm = (D0 + D1)/2  [mm]."""
    return (d0_mm + d1_mm) / 2.0


def ceil_count(total: float, step: float) -> int:
    """ceil(total/step), tolerant of float noise (e.g. 1.7/0.85), minimum 1."""
    _pos("step", step)
    return max(1, math.ceil(total / step - _CEIL_TOL))


def turning_passes(d0_mm: float, d1_mm: float, ap_mm: float) -> int:
    """N = ceil(((D0 - D1)/2)/ap)."""
    return ceil_count((d0_mm - d1_mm) / 2.0, ap_mm)


def feed_rate_turning(f_mm_rev: float, n_rpm: float) -> float:
    """vf = f*n  [mm/min]."""
    return f_mm_rev * n_rpm


def feed_rate_milling(fz_mm_tooth: float, teeth: int, n_rpm: float) -> float:
    """vf = fz*z*n  [mm/min]."""
    return fz_mm_tooth * teeth * n_rpm


def cutting_time_min(passes: int, length_per_pass_mm: float, vf_mm_min: float) -> float:
    """Tm = N*L_pass/vf  [min]."""
    _pos("vf", vf_mm_min)
    return passes * length_per_pass_mm / vf_mm_min


def mrr_turning(vc_m_min: float, f_mm_rev: float, ap_mm: float) -> float:
    """MRR ~= 1000*Vc*f*ap  [mm^3/min] (Vc taken at the mean diameter)."""
    return 1000.0 * vc_m_min * f_mm_rev * ap_mm


def mrr_milling(ap_mm: float, ae_mm: float, vf_mm_min: float) -> float:
    """MRR = ap*ae*vf  [mm^3/min]."""
    return ap_mm * ae_mm * vf_mm_min


# --- Taylor tool life: V * T^n = C ------------------------------------------

def taylor_constant(v_ref: float, t_ref: float, n: float) -> float:
    """C = V_ref * T_ref^n."""
    return v_ref * t_ref**n


def taylor_tool_life(v: float, c: float, n: float) -> float:
    """T = (C/V)^(1/n)  [min]."""
    _pos("V", v)
    _pos("n", n)
    return (c / v) ** (1.0 / n)


def taylor_speed(t: float, c: float, n: float) -> float:
    """V = C/T^n  [m/min]."""
    _pos("T", t)
    return c / t**n


# --- Optimum speeds (Groover-style, single-pass economics) -------------------

def min_cost_tool_life(n: float, tt_min: float, ce: float, co_per_h: float) -> float | None:
    """Tool life for minimum cost: Tc = (1/n - 1)*(Tt + Ce/(Co/60)).

    Returns None when undefined (n outside (0,1), or Tc <= 0 e.g. Tt = Ce = 0).
    """
    if not 0 < n < 1 or co_per_h <= 0:
        return None
    t = (1.0 / n - 1.0) * (tt_min + ce / (co_per_h / 60.0))
    return t if t > 0 else None


def max_rate_tool_life(n: float, tt_min: float) -> float | None:
    """Tool life for maximum production rate: Tp = (1/n - 1)*Tt.

    Returns None when undefined (n outside (0,1), or Tt = 0 which implies an
    unbounded speed).
    """
    if not 0 < n < 1:
        return None
    t = (1.0 / n - 1.0) * tt_min
    return t if t > 0 else None
