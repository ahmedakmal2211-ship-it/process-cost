"""Job-file parsing and validation into resolved, frozen dataclasses.

A job file is JSON. Either the top level is one complete job, or it holds a
"scenarios" list; each scenario is deep-merged over the top-level keys (one
level deep for the "operation" and "costs" sections), so shared data is written
once. An outsource scenario ({"type": "outsource"}) does not inherit machining
keys. Unknown keys are rejected so typos never fall back to silent defaults.
"""

from __future__ import annotations

import difflib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import formulas
from .materials import MATERIALS, TOOL_MATERIALS, lookup

DEFAULT_APPROACH_MM = 2.0  # turning approach + overtravel per pass, see docs/MODEL.md


class InputError(ValueError):
    """Raised for any invalid job file or argument; the CLI maps it to exit code 2."""


@dataclass(frozen=True)
class TurningGeometry:
    d0_mm: float
    d1_mm: float
    length_mm: float
    ap_mm: float
    feed_mm_rev: float
    approach_mm: float

    @property
    def mean_diameter_mm(self) -> float:
        return formulas.mean_diameter(self.d0_mm, self.d1_mm)

    @property
    def passes(self) -> int:
        return formulas.turning_passes(self.d0_mm, self.d1_mm, self.ap_mm)

    @property
    def length_per_pass_mm(self) -> float:
        return self.length_mm + self.approach_mm

    @property
    def feed(self) -> float:
        return self.feed_mm_rev


@dataclass(frozen=True)
class MillingGeometry:
    tool_diameter_mm: float
    teeth: int
    feed_mm_tooth: float
    cut_length_mm: float
    passes: int
    lead_in_out_mm: float
    ap_mm: float | None = None
    ae_mm: float | None = None

    @property
    def length_per_pass_mm(self) -> float:
        return self.cut_length_mm + self.lead_in_out_mm

    @property
    def feed(self) -> float:
        return self.feed_mm_tooth


@dataclass(frozen=True)
class Job:
    name: str
    kind: str  # "turning" | "milling"
    geometry: TurningGeometry | MillingGeometry
    material: str
    tool_material: str
    vc_m_min: float
    taylor_n: float
    taylor_c: float
    machine_rate_h: float
    setup_rate_h: float
    setup_min: float
    handling_min: float
    tool_change_min: float
    cost_per_edge: float
    material_cost: float
    batch_size: float
    scrap_rate: float = 0.0
    spindle_max_rpm: float | None = None
    feed_max_mm_min: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def feed_unit(self) -> str:
        return "mm/rev" if self.kind == "turning" else "mm/tooth"


@dataclass(frozen=True)
class Outsource:
    name: str
    price_per_part: float
    fixed_fee: float
    batch_size: float
    kind: str = "outsource"


Scenario = Job | Outsource


@dataclass(frozen=True)
class JobFile:
    title: str
    scenarios: tuple[Scenario, ...]
    has_scenarios: bool

    @property
    def jobs(self) -> list[Job]:
        return [s for s in self.scenarios if isinstance(s, Job)]


# --- validation helpers ------------------------------------------------------

_TOP_KEYS = {"name", "description", "batch_size", "operation", "costs", "scenarios"}
_SCENARIO_KEYS = {"name", "description", "batch_size", "operation", "costs", "type"}
_OUTSOURCE_KEYS = {"name", "description", "type", "price_per_part", "fixed_fee", "batch_size"}
_COMMON_OP = {"type", "material", "tool_material", "Vc_m_per_min", "taylor_n", "taylor_C",
              "spindle_max_rpm", "feed_max_mm_per_min"}
_TURNING_OP = _COMMON_OP | {"D0_mm", "D1_mm", "length_mm", "ap_mm", "feed_mm_per_rev", "approach_mm"}
_MILLING_OP = _COMMON_OP | {"tool_diameter_mm", "teeth", "feed_mm_per_tooth", "cut_length_mm",
                            "passes", "total_depth_mm", "ap_mm", "ae_mm", "lead_in_out_mm"}
_COST_KEYS = {"machine_rate_per_h", "setup_rate_per_h", "setup_min", "handling_min",
              "tool_change_min", "cost_per_edge", "material_cost_per_part", "scrap_rate"}


def _check_keys(d: dict, allowed: set[str], where: str) -> None:
    for k in d:
        if k not in allowed:
            hint = difflib.get_close_matches(k, sorted(allowed), n=1)
            extra = f" (did you mean '{hint[0]}'?)" if hint else ""
            raise InputError(f"{where}: unknown key '{k}'{extra}")


def _section(d: dict, key: str, where: str) -> dict:
    if key not in d:
        raise InputError(f"{where}: missing required section '{key}'")
    v = d[key]
    if not isinstance(v, dict):
        raise InputError(f"{where}.{key}: must be a JSON object")
    return v


_RULES = {
    "pos": ("> 0", lambda x: x > 0),
    "nonneg": (">= 0", lambda x: x >= 0),
    "frac": ("in [0, 1)", lambda x: 0 <= x < 1),
    "open01": ("strictly between 0 and 1", lambda x: 0 < x < 1),
}


def _num(d: dict, key: str, where: str, rule: str = "pos", required: bool = True) -> float | None:
    if key not in d or d[key] is None:
        if required:
            raise InputError(f"{where}: missing required field '{key}'")
        return None
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InputError(f"{where}.{key}: must be a number (got {v!r})")
    v = float(v)
    if not math.isfinite(v):
        raise InputError(f"{where}.{key}: must be finite (got {v})")
    text, ok = _RULES[rule]
    if not ok(v):
        raise InputError(f"{where}.{key}: must be {text} (got {v:g})")
    return v


def _int(d: dict, key: str, where: str, required: bool = True) -> int | None:
    v = _num(d, key, where, "pos", required)
    if v is None:
        return None
    if v != int(v):
        raise InputError(f"{where}.{key}: must be a whole number (got {v:g})")
    return int(v)


def _str(d: dict, key: str, where: str) -> str:
    if key not in d:
        raise InputError(f"{where}: missing required field '{key}'")
    v = d[key]
    if not isinstance(v, str) or not v.strip():
        raise InputError(f"{where}.{key}: must be a non-empty string")
    return v.strip()


def _merge(base: dict, over: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


# --- parsing -----------------------------------------------------------------

def _parse_operation(op: dict, where: str, notes: list[str]):
    kind = _str(op, "type", where)
    if kind not in ("turning", "milling"):
        raise InputError(f"{where}.type: must be 'turning' or 'milling' (got '{kind}')")
    _check_keys(op, _TURNING_OP if kind == "turning" else _MILLING_OP, where)

    material = _str(op, "material", where)
    tool = _str(op, "tool_material", where)
    vc = _num(op, "Vc_m_per_min", where, "pos", required=False)
    n = _num(op, "taylor_n", where, "open01", required=False)
    c = _num(op, "taylor_C", where, "pos", required=False)

    if material == "custom":
        if tool not in TOOL_MATERIALS:
            raise InputError(f"{where}.tool_material: unknown '{tool}'; known: {', '.join(sorted(TOOL_MATERIALS))}")
        missing = [k for k, v in (("Vc_m_per_min", vc), ("taylor_n", n), ("taylor_C", c)) if v is None]
        if missing:
            raise InputError(f"{where}: material 'custom' requires {', '.join(missing)}")
    else:
        try:
            data = lookup(material, tool)
        except KeyError as exc:
            raise InputError(f"{where}: {exc.args[0]}") from None
        if vc is None:
            vc = data.vc_turning if kind == "turning" else data.vc_milling
            notes.append(f"Vc = {vc:g} m/min from indicative table ({material}, {tool})")
        if n is None:
            n = data.taylor_n
        if c is None:
            c = formulas.taylor_constant(
                data.vc_turning if kind == "turning" else data.vc_milling, data.t_ref, n)
            notes.append(f"Taylor C = {c:.1f} from table (T_ref = {data.t_ref:g} min, n = {n:g})")

    caps = (_num(op, "spindle_max_rpm", where, "pos", required=False),
            _num(op, "feed_max_mm_per_min", where, "pos", required=False))

    if kind == "turning":
        d0 = _num(op, "D0_mm", where)
        d1 = _num(op, "D1_mm", where)
        if d1 >= d0:
            raise InputError(f"{where}: D1_mm ({d1:g}) must be smaller than D0_mm ({d0:g})")
        approach = _num(op, "approach_mm", where, "nonneg", required=False)
        if approach is None:
            approach = DEFAULT_APPROACH_MM
            notes.append(f"approach_mm not given: documented default {DEFAULT_APPROACH_MM:g} mm per pass used")
        geom = TurningGeometry(
            d0_mm=d0, d1_mm=d1, length_mm=_num(op, "length_mm", where), ap_mm=_num(op, "ap_mm", where),
            feed_mm_rev=_num(op, "feed_mm_per_rev", where), approach_mm=approach)
    else:
        passes = _int(op, "passes", where, required=False)
        depth = _num(op, "total_depth_mm", where, "pos", required=False)
        ap = _num(op, "ap_mm", where, "pos", required=False)
        if passes is not None and depth is not None:
            raise InputError(f"{where}: give either 'passes' or 'total_depth_mm' (with 'ap_mm'), not both")
        if passes is None:
            if depth is None or ap is None:
                raise InputError(f"{where}: milling needs 'passes', or 'total_depth_mm' and 'ap_mm'")
            passes = formulas.ceil_count(depth, ap)
        geom = MillingGeometry(
            tool_diameter_mm=_num(op, "tool_diameter_mm", where), teeth=_int(op, "teeth", where),
            feed_mm_tooth=_num(op, "feed_mm_per_tooth", where), cut_length_mm=_num(op, "cut_length_mm", where),
            passes=passes, lead_in_out_mm=_num(op, "lead_in_out_mm", where, "nonneg"),
            ap_mm=ap, ae_mm=_num(op, "ae_mm", where, "pos", required=False))
    return kind, geom, material, tool, vc, n, c, caps


def _parse_job(d: dict, name: str, where: str) -> Job:
    notes: list[str] = []
    op = _section(d, "operation", where)
    costs = _section(d, "costs", where)
    _check_keys(costs, _COST_KEYS, f"{where}.costs")
    kind, geom, material, tool, vc, n, c, (rpm_max, vf_max) = _parse_operation(op, f"{where}.operation", notes)
    cw = f"{where}.costs"
    co = _num(costs, "machine_rate_per_h", cw)
    cs = _num(costs, "setup_rate_per_h", cw, "nonneg", required=False)
    if cs is None:
        cs = co
        notes.append("setup_rate_per_h not given: machine rate used for setup")
    q = _int(d, "batch_size", where)
    return Job(
        name=name, kind=kind, geometry=geom, material=material, tool_material=tool,
        vc_m_min=vc, taylor_n=n, taylor_c=c,
        machine_rate_h=co, setup_rate_h=cs,
        setup_min=_num(costs, "setup_min", cw, "nonneg"),
        handling_min=_num(costs, "handling_min", cw, "nonneg"),
        tool_change_min=_num(costs, "tool_change_min", cw, "nonneg"),
        cost_per_edge=_num(costs, "cost_per_edge", cw, "nonneg"),
        material_cost=_num(costs, "material_cost_per_part", cw, "nonneg"),
        scrap_rate=_num(costs, "scrap_rate", cw, "frac", required=False) or 0.0,
        batch_size=float(q), spindle_max_rpm=rpm_max, feed_max_mm_min=vf_max, notes=tuple(notes))


def _parse_outsource(d: dict, name: str, where: str, batch: Any) -> Outsource:
    _check_keys(d, _OUTSOURCE_KEYS, where)
    tmp = {"batch_size": d.get("batch_size", batch)}
    return Outsource(
        name=name, price_per_part=_num(d, "price_per_part", where),
        fixed_fee=_num(d, "fixed_fee", where, "nonneg"),
        batch_size=float(_int(tmp, "batch_size", where)))


def parse_job_file(data: Any) -> JobFile:
    if not isinstance(data, dict):
        raise InputError("job file: top level must be a JSON object")
    _check_keys(data, _TOP_KEYS, "job")
    title = data.get("name", "job")
    if not isinstance(title, str):
        raise InputError("job.name: must be a string")
    if "scenarios" not in data:
        return JobFile(title=title, scenarios=(_parse_job(data, title, "job"),), has_scenarios=False)

    raw = data["scenarios"]
    if not isinstance(raw, list) or not raw:
        raise InputError("job.scenarios: must be a non-empty list")
    base = {k: v for k, v in data.items() if k not in ("scenarios", "name", "description")}
    out: list[Scenario] = []
    names: set[str] = set()
    for i, sc in enumerate(raw):
        where = f"scenarios[{i}]"
        if not isinstance(sc, dict):
            raise InputError(f"{where}: must be a JSON object")
        name = _str(sc, "name", where)
        where = f"scenarios[{i}] '{name}'"
        if name in names:
            raise InputError(f"{where}: duplicate scenario name")
        names.add(name)
        stype = sc.get("type", "machining")
        if stype == "outsource":
            out.append(_parse_outsource(sc, name, where, base.get("batch_size")))
        elif stype == "machining":
            _check_keys(sc, _SCENARIO_KEYS, where)
            merged = _merge(base, {k: v for k, v in sc.items() if k not in ("type", "description")})
            out.append(_parse_job(merged, name, where))
        else:
            raise InputError(f"{where}.type: must be 'machining' or 'outsource' (got {stype!r})")
    return JobFile(title=title, scenarios=tuple(out), has_scenarios=True)


def load_job_file(path: str | Path) -> JobFile:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"job file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{p}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}") from None
    return parse_job_file(data)
