import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from process_cost.models import parse_job_file  # noqa: E402

TURNING = {
    "name": "test turning",
    "batch_size": 10,
    "operation": {
        "type": "turning", "material": "aisi_1045", "tool_material": "coated_carbide",
        "D0_mm": 40, "D1_mm": 36, "length_mm": 120, "ap_mm": 1.0,
        "feed_mm_per_rev": 0.25, "approach_mm": 2.0, "Vc_m_per_min": 200,
    },
    "costs": {
        "machine_rate_per_h": 60, "setup_min": 30, "handling_min": 1.0,
        "tool_change_min": 2.0, "cost_per_edge": 5.0, "material_cost_per_part": 4.0,
    },
}

MILLING = {
    "name": "test milling",
    "batch_size": 20,
    "operation": {
        "type": "milling", "material": "al_6061", "tool_material": "coated_carbide",
        "tool_diameter_mm": 16, "teeth": 3, "feed_mm_per_tooth": 0.1,
        "cut_length_mm": 500, "passes": 2, "lead_in_out_mm": 10,
        "ap_mm": 4, "ae_mm": 8, "Vc_m_per_min": 300,
    },
    "costs": {
        "machine_rate_per_h": 90, "setup_min": 45, "handling_min": 2.0,
        "tool_change_min": 3.0, "cost_per_edge": 30.0, "material_cost_per_part": 10.0,
    },
}


def _build(base, op=None, costs=None, drop=(), **top):
    d = copy.deepcopy(base)
    d["operation"].update(op or {})
    d["costs"].update(costs or {})
    d.update(top)
    for path in drop:
        sect, _, key = path.partition(".")
        if key:
            d[sect].pop(key, None)
        else:
            d.pop(sect, None)
    return d


@pytest.fixture
def turning_dict():
    return lambda **kw: _build(TURNING, **kw)


@pytest.fixture
def milling_dict():
    return lambda **kw: _build(MILLING, **kw)


@pytest.fixture
def turning_job(turning_dict):
    return lambda **kw: parse_job_file(turning_dict(**kw)).scenarios[0]


@pytest.fixture
def milling_job(milling_dict):
    return lambda **kw: parse_job_file(milling_dict(**kw)).scenarios[0]
