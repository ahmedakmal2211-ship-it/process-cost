import dataclasses

import pytest

from process_cost.cost import estimate, optimum_speeds


def test_min_cost_speed_matches_formula(turning_job):
    job = turning_job()
    mc, _ = optimum_speeds(job)
    tc = (1 / 0.3 - 1) * (2.0 + 5.0 / (60 / 60))
    assert mc.tool_life_min == pytest.approx(tc)
    assert mc.vc_m_min == pytest.approx(job.taylor_c / tc ** 0.3)
    assert mc.estimate.tool_life_min == pytest.approx(tc)


def test_max_rate_speed_matches_formula(turning_job):
    job = turning_job()
    _, mp = optimum_speeds(job)
    tp = (1 / 0.3 - 1) * 2.0
    assert mp.vc_m_min == pytest.approx(job.taylor_c / tp ** 0.3)


@pytest.mark.parametrize("factor", [0.8, 0.95, 0.99, 1.01, 1.05, 1.25])
def test_cost_is_minimum_at_min_cost_speed(turning_job, factor):
    job = turning_job()
    mc, _ = optimum_speeds(job)
    v = mc.vc_m_min
    assert mc.estimate.cost_per_part <= estimate(job, vc=v * factor).cost_per_part + 1e-12


@pytest.mark.parametrize("factor", [0.8, 0.97, 1.03, 1.25])
def test_time_is_minimum_at_max_rate_speed(milling_job, factor):
    job = milling_job()
    _, mp = optimum_speeds(job)
    assert mp.estimate.tp_min <= estimate(job, vc=mp.vc_m_min * factor).tp_min + 1e-12


def test_max_rate_speed_faster_than_min_cost_speed(turning_job):
    mc, mp = optimum_speeds(turning_job())
    assert mp.vc_m_min > mc.vc_m_min


def test_tt_zero_max_rate_undefined_min_cost_defined(turning_job):
    mc, mp = optimum_speeds(turning_job(costs={"tool_change_min": 0}))
    assert mp.vc_m_min is None and "Tt = 0" in mp.reason
    assert mc.vc_m_min is not None
    assert mc.tool_life_min == pytest.approx((1 / 0.3 - 1) * 5.0)


def test_tt_and_ce_zero_both_undefined(turning_job):
    mc, mp = optimum_speeds(turning_job(costs={"tool_change_min": 0, "cost_per_edge": 0}))
    assert mc.estimate is None and mp.estimate is None


@pytest.mark.parametrize("n", [1.0, 1.3])
def test_n_ge_one_does_not_crash(turning_job, n):
    job = dataclasses.replace(turning_job(), taylor_n=n)
    mc, mp = optimum_speeds(job)
    assert mc.vc_m_min is None and mp.vc_m_min is None
    assert "not in (0, 1)" in mc.reason
