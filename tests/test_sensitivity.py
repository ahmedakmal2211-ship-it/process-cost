import pytest

from process_cost.cost import estimate
from process_cost.models import InputError
from process_cost.sensitivity import PARAMS, sensitivity, steps_for


def test_steps_default_and_custom():
    assert steps_for(10) == (-20, -10, 10, 20)
    assert steps_for(5) == (-10, -5, 5, 10)


@pytest.mark.parametrize("bad", [0, -5, 50, 75])
def test_steps_invalid(bad):
    with pytest.raises(InputError):
        steps_for(bad)


def test_all_parameters_present(turning_job):
    s = sensitivity(turning_job())
    assert {r.key for r in s.rows} == {p[0] for p in PARAMS}
    assert {"Vc", "feed", "Co", "Ts", "Ce", "Tt", "Th", "Cm", "Q", "n"} == {r.key for r in s.rows}


def test_rows_sorted_by_absolute_impact(turning_job):
    s = sensitivity(turning_job())
    impacts = [r.impact for r in s.rows]
    assert impacts == sorted(impacts, reverse=True)


def test_material_cost_is_linear(turning_job):
    job = turning_job()
    s = sensitivity(job, 10)
    row = next(r for r in s.rows if r.key == "Cm")
    # +10% of Cm = 4.0 adds exactly 0.4 $/part; -20% removes 0.8
    assert row.costs[2] - s.base_cost == pytest.approx(0.1 * 4.0)
    assert row.costs[0] - s.base_cost == pytest.approx(-0.2 * 4.0)


def test_batch_size_variation_only_moves_setup_share(turning_job):
    job = turning_job()
    e = estimate(job)
    row = next(r for r in sensitivity(job, 10).rows if r.key == "Q")
    assert row.costs[3] == pytest.approx(e.variable_per_part + e.fixed_per_batch / (10 * 1.2))
    assert row.changes[3] < 0 < row.changes[0]


def test_setup_time_change(turning_job):
    s = sensitivity(turning_job(), 10)
    row = next(r for r in s.rows if r.key == "Ts")
    # F = Ts/60*Cs = 30 at base; +10% -> +3 per batch -> +0.3 per part at Q = 10
    assert row.costs[2] - s.base_cost == pytest.approx(0.3)


def test_zero_parameter_has_zero_impact(turning_job):
    s = sensitivity(turning_job(costs={"tool_change_min": 0}))
    row = next(r for r in s.rows if r.key == "Tt")
    assert row.impact == 0
    assert s.rows[-1].impact == 0


def test_taylor_n_keeps_c_fixed(turning_job):
    job = turning_job()
    row = next(r for r in sensitivity(job, 10).rows if r.key == "n")
    import dataclasses
    expected = estimate(dataclasses.replace(job, taylor_n=0.3 * 1.1)).cost_per_part
    assert row.costs[2] == pytest.approx(expected)
    # T = (C/V)^(1/n) with C fixed: when C/V > 1 a larger n shrinks the exponent,
    # so tool life falls and cost per part rises
    assert job.taylor_c / job.vc_m_min > 1
    assert row.changes[2] > 0


def test_base_cost_matches_estimate(milling_job):
    job = milling_job()
    assert sensitivity(job).base_cost == pytest.approx(estimate(job).cost_per_part)


def test_feed_unit_depends_on_operation(turning_job, milling_job):
    t = next(r for r in sensitivity(turning_job()).rows if r.key == "feed")
    m = next(r for r in sensitivity(milling_job()).rows if r.key == "feed")
    assert (t.unit, m.unit) == ("mm/rev", "mm/tooth")
