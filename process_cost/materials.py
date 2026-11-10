"""Indicative cutting data for common work materials and tool materials.

INDICATIVE STARTING ASSUMPTIONS ONLY. These numbers are textbook-order values
chosen to be broadly consistent with ranges quoted for general references (Kalpakjian &
Schmid, "Manufacturing Engineering and Technology"; Groover, "Fundamentals of
Modern Manufacturing"; Machinery's Handbook speed and feed tables; public
Sandvik Coromant / Kennametal catalogue ranges). They are NOT machining data
sheet values for any specific insert grade, coating, geometry or machine.
Real tool life must be checked against the tool maker's data and shop trials.

Each cell gives, for one (work material, tool material) pair:
    vc_turning   recommended turning cutting speed      [m/min]
    vc_milling   recommended milling cutting speed      [m/min]
    f_turning    recommended turning feed hint          [mm/rev]
    fz_milling   recommended milling feed-per-tooth hint [mm/tooth]
    taylor_n     Taylor exponent n in V*T^n = C         [-]
    t_ref        reference tool life at the recommended speed [min]
The Taylor constant is derived as C = Vc_rec * T_ref**n (see docs/MODEL.md).
"""

from __future__ import annotations

from dataclasses import dataclass

INDICATIVE_NOTE = (
    "INDICATIVE textbook-order values: starting assumptions, not machining data "
    "sheet values. Check real tool life against the tool maker's data."
)


@dataclass(frozen=True)
class CuttingData:
    vc_turning: float
    vc_milling: float
    f_turning: float
    fz_milling: float
    taylor_n: float
    t_ref: float


MATERIALS: dict[str, str] = {
    "aisi_1018": "Low-carbon steel, AISI 1018",
    "aisi_1045": "Medium-carbon steel, AISI 1045",
    "ss_304": "Austenitic stainless steel, 304",
    "al_6061": "Aluminium alloy 6061-T6",
    "grey_cast_iron": "Grey cast iron",
    "brass_free_cutting": "Free-cutting brass (C36000)",
    "ti_6al_4v": "Titanium alloy Ti-6Al-4V",
}

TOOL_MATERIALS: dict[str, str] = {
    "hss": "High-speed steel",
    "carbide": "Uncoated cemented carbide",
    "coated_carbide": "Coated cemented carbide",
}

# Taylor n and reference life per tool material (Kalpakjian & Schmid give
# n ~0.08-0.2 for HSS and ~0.2-0.5 for carbides; Groover's tables use 0.125
# for HSS and 0.25 for carbide). Carbide catalogues commonly quote 15 min life.
_N = {"hss": 0.125, "carbide": 0.25, "coated_carbide": 0.30}
_TREF = {"hss": 30.0, "carbide": 15.0, "coated_carbide": 15.0}

# (vc_turning, vc_milling) per tool material, then (f_turning, fz_milling).
_SPEEDS: dict[str, dict[str, tuple[float, float]]] = {
    "aisi_1018": {"coated_carbide": (220, 200), "carbide": (185, 165), "hss": (55, 45)},
    "aisi_1045": {"coated_carbide": (185, 170), "carbide": (155, 150), "hss": (45, 38)},
    "ss_304": {"coated_carbide": (130, 115), "carbide": (105, 100), "hss": (28, 25)},
    "al_6061": {"coated_carbide": (450, 500), "carbide": (350, 400), "hss": (110, 110)},
    "grey_cast_iron": {"coated_carbide": (150, 140), "carbide": (110, 105), "hss": (35, 30)},
    "brass_free_cutting": {"coated_carbide": (260, 240), "carbide": (210, 200), "hss": (75, 70)},
    "ti_6al_4v": {"coated_carbide": (65, 55), "carbide": (45, 40), "hss": (15, 14)},
}
_FEEDS: dict[str, tuple[float, float]] = {
    "aisi_1018": (0.30, 0.12),
    "aisi_1045": (0.25, 0.10),
    "ss_304": (0.20, 0.08),
    "al_6061": (0.30, 0.15),
    "grey_cast_iron": (0.30, 0.12),
    "brass_free_cutting": (0.25, 0.12),
    "ti_6al_4v": (0.15, 0.06),
}

TABLE: dict[tuple[str, str], CuttingData] = {}
for _mat, _by_tool in _SPEEDS.items():
    for _tool, (_vt, _vm) in _by_tool.items():
        _ft, _fz = _FEEDS[_mat]
        TABLE[(_mat, _tool)] = CuttingData(
            vc_turning=float(_vt),
            vc_milling=float(_vm),
            f_turning=_ft,
            fz_milling=_fz,
            taylor_n=_N[_tool],
            t_ref=_TREF[_tool],
        )


def lookup(material: str, tool_material: str) -> CuttingData:
    """Return the cutting data for a pair, or raise KeyError with a clear message."""
    if material not in MATERIALS:
        raise KeyError(
            f"unknown material '{material}'; known: {', '.join(sorted(MATERIALS))} "
            "(or 'custom' with Vc, taylor_n and taylor_C given)"
        )
    if tool_material not in TOOL_MATERIALS:
        raise KeyError(
            f"unknown tool_material '{tool_material}'; known: {', '.join(sorted(TOOL_MATERIALS))}"
        )
    return TABLE[(material, tool_material)]
