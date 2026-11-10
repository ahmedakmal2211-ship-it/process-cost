import math

import pytest

from process_cost.cost import estimate

N_RPM = 1000 * 200 / (math.pi * 38)   # Vc 200 at Dm = (40+36)/2
VF = 0.25 * N_RPM
TM = 2 * (120 + 2) / VF               # 2 passes x (L + approach)
C_TABLE = 185 * 15 ** 0.3             # AISI 1045 / coated carbide, T_ref 15 min, n 0.3
T_LIFE = (C_TABLE / 200) ** (1 / 0.3)
EDGES = TM / T_LIFE


def test_turning_kinematics(turning_job):
    e = estimate(turning_job())
    assert e.n_rpm == pytest.approx(N_RPM)
    assert e.vf_mm_min == pytest.approx(VF)
    assert e.passes == 2
    assert e.length_per_pass_mm == pytest.approx(122)
    assert e.tm_min == pytest.approx(TM)


def test_turning_tool_life_and_edges(turning_job):
    e = estimate(turning_job())
    assert e.tool_life_min == pytest.approx(T_LIFE)
    assert e.edges_per_part == pytest.approx(EDGES)


def test_time_per_part(turning_job):
    e = estimate(turning_job())
    assert e.tp_min == pytest.approx(1.0 + TM + EDGES * 2.0)


def test_cost_components(turning_job):
    e = estimate(turning_job())
    co_min = 60 / 60
    assert e.cost_machining == pytest.approx(co_min * (1.0 + TM))
    assert e.cost_tool_change == pytest.approx(co_min * EDGES * 2.0)
    assert e.cost_tooling == pytest.approx(EDGES * 5.0)
    assert e.cost_material == pytest.approx(4.0)
    assert e.fixed_per_batch == pytest.approx(30 / 60 * 60)
    assert e.cost_setup == pytest.approx(30.0 / 10)


def test_cost_per_part_total(turning_job):
    e = estimate(turning_job())
    expected = 4.0 + 60 * (1.0 + TM + EDGES * 2.0) / 60 + EDGES * 5.0 + 30.0 / 10
    assert e.cost_per_part == pytest.approx(expected)


def test_batch_cost_and_time(turning_job):
    e = estimate(turning_job())
    assert e.batch_cost == pytest.approx(e.fixed_per_batch + e.variable_per_part * 10)
    assert e.batch_time_min == pytest.approx(30 + 10 * e.tp_min)
    assert e.batch_cost == pytest.approx(e.cost_per_part * 10)


def test_split_sums_to_100(turning_job):
    split = estimate(turning_job()).split()
    assert set(split) == {"setup", "machining", "tool change", "tooling", "material"}
    assert sum(split.values()) == pytest.approx(100.0)


def test_setup_rate_separate_from_machine_rate(turning_job):
    e = estimate(turning_job(costs={"setup_rate_per_h": 120}))
    assert e.fixed_per_batch == pytest.approx(30 / 60 * 120)


def test_scrap_rate_scales_variable_cost_only(turning_job):
    base = estimate(turning_job())
    s = estimate(turning_job(costs={"scrap_rate": 0.1}))
    assert s.variable_per_part == pytest.approx(base.variable_per_part / 0.9)
    assert s.fixed_per_batch == pytest.approx(base.fixed_per_batch)
    assert s.parts_started == pytest.approx(10 / 0.9)
    assert s.batch_time_min == pytest.approx(30 + 10 / 0.9 * base.tp_min)


def test_zero_tool_change_time_gives_zero_tool_change_cost(turning_job):
    e = estimate(turning_job(costs={"tool_change_min": 0}))
    assert e.cost_tool_change == 0
    assert e.tp_min == pytest.approx(1.0 + TM)


def test_cutting_time_inverse_to_speed(turning_job):
    job = turning_job()
    assert estimate(job, vc=100).tm_min == pytest.approx(2 * estimate(job, vc=200).tm_min)


def test_batch_size_override(turning_job):
    job = turning_job()
    e = estimate(job, batch_size=30)
    assert e.cost_setup == pytest.approx(30.0 / 30)


def test_spindle_cap_reduces_speed_and_extends_life(turning_job):
    e = estimate(turning_job(op={"spindle_max_rpm": 1000}))
    assert e.n_rpm == 1000
    assert e.vc_effective == pytest.approx(math.pi * 38 * 1000 / 1000)
    assert e.tool_life_min == pytest.approx((C_TABLE / e.vc_effective) ** (1 / 0.3))
    assert e.vf_mm_min == pytest.approx(250)
    assert any("spindle capped" in w for w in e.warnings)


def test_spindle_cap_not_triggered_below_limit(turning_job):
    e = estimate(turning_job(op={"spindle_max_rpm": 5000}))
    assert e.warnings == ()
    assert e.vc_effective == 200


def test_feed_cap(turning_job):
    e = estimate(turning_job(op={"feed_max_mm_per_min": 300}))
    assert e.vf_mm_min == 300
    assert e.feed_effective == pytest.approx(300 / N_RPM)
    assert e.tm_min == pytest.approx(2 * 122 / 300)
    assert any("feed rate capped" in w for w in e.warnings)


def test_milling_kinematics_and_mrr(milling_job):
    e = estimate(milling_job())
    n = 1000 * 300 / (math.pi * 16)
    vf = 0.1 * 3 * n
    assert e.n_rpm == pytest.approx(n)
    assert e.vf_mm_min == pytest.approx(vf)
    assert e.tm_min == pytest.approx(2 * (500 + 10) / vf)
    assert e.mrr_mm3_min == pytest.approx(4 * 8 * vf)


def test_milling_mrr_absent_without_ae(milling_job, milling_dict):
    from process_cost.models import parse_job_file
    d = milling_dict()
    del d["operation"]["ae_mm"]
    e = estimate(parse_job_file(d).scenarios[0])
    assert e.mrr_mm3_min is None


def test_milling_tool_life_uses_milling_table_speed(milling_job):
    # al_6061 / coated carbide milling: Vc_rec 500, T_ref 15, n 0.3
    e = estimate(milling_job())
    c = 500 * 15 ** 0.3
    assert e.tool_life_min == pytest.approx((c / 300) ** (1 / 0.3))
