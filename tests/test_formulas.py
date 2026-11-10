import math

import pytest

from process_cost import formulas as f


def test_spindle_speed_d40_vc200():
    # 1000*200/(pi*40) = 1591.549 rpm
    assert f.spindle_speed_rpm(200, 40) == pytest.approx(1591.549, abs=1e-3)


def test_spindle_speed_inverse_round_trip():
    n = f.spindle_speed_rpm(185, 38)
    assert f.cutting_speed_m_min(n, 38) == pytest.approx(185)


@pytest.mark.parametrize("vc,d", [(0, 40), (-5, 40), (200, 0), (200, -1)])
def test_spindle_speed_rejects_non_positive(vc, d):
    with pytest.raises(ValueError):
        f.spindle_speed_rpm(vc, d)


def test_mean_diameter():
    assert f.mean_diameter(40, 36) == 38


@pytest.mark.parametrize("d0,d1,ap,expected", [
    (40, 36, 1.0, 2),      # 2 mm radial / 1 mm = 2 exactly
    (40, 36, 2.0, 1),      # one pass removes it all
    (40, 36, 0.9, 3),      # 2/0.9 = 2.22 -> 3
    (40, 36, 1.99, 2),     # 2/1.99 = 1.005 -> 2
    (40, 36, 5.0, 1),      # ap larger than stock still needs one pass
    (40, 36.6, 0.85, 2),   # 1.7/0.85 is 2.0000000000000036 in floats -> still 2
])
def test_turning_passes_ceil_boundaries(d0, d1, ap, expected):
    assert f.turning_passes(d0, d1, ap) == expected


def test_ceil_count_just_above_boundary():
    assert f.ceil_count(12.0001, 4) == 4
    assert f.ceil_count(12.0, 4) == 3


def test_feed_rates():
    assert f.feed_rate_turning(0.25, 1600) == pytest.approx(400.0)
    assert f.feed_rate_milling(0.1, 3, 5000) == pytest.approx(1500.0)


def test_cutting_time():
    # 2 passes * 122 mm / 400 mm/min = 0.61 min
    assert f.cutting_time_min(2, 122, 400) == pytest.approx(0.61)


def test_mrr():
    assert f.mrr_turning(200, 0.25, 1.0) == pytest.approx(1000 * 200 * 0.25 * 1.0)
    assert f.mrr_milling(4, 8, 1500) == pytest.approx(4 * 8 * 1500)


def test_taylor_constant_and_life_at_reference():
    c = f.taylor_constant(185, 15, 0.3)
    assert c == pytest.approx(185 * 15 ** 0.3)
    assert f.taylor_tool_life(185, c, 0.3) == pytest.approx(15)


@pytest.mark.parametrize("v,n,c", [(150, 0.25, 600), (90, 0.125, 120), (400, 0.4, 1500)])
def test_taylor_round_trip(v, n, c):
    t = f.taylor_tool_life(v, c, n)
    assert f.taylor_speed(t, c, n) == pytest.approx(v)
    assert v * t ** n == pytest.approx(c)


def test_taylor_life_halving_speed():
    # T2/T1 = (V1/V2)^(1/n) = 2^(1/0.25) = 16
    c, n = 500, 0.25
    assert f.taylor_tool_life(100, c, n) / f.taylor_tool_life(200, c, n) == pytest.approx(16)


def test_min_cost_tool_life_formula():
    # (1/0.25 - 1)*(2 + 5/(60/60)) = 3*7 = 21 min
    assert f.min_cost_tool_life(0.25, 2, 5, 60) == pytest.approx(21)


def test_max_rate_tool_life_formula():
    # (1/0.25 - 1)*2 = 6 min
    assert f.max_rate_tool_life(0.25, 2) == pytest.approx(6)


def test_optimum_lives_undefined_cases():
    assert f.max_rate_tool_life(0.25, 0) is None
    assert f.min_cost_tool_life(0.25, 0, 0, 60) is None
    assert f.min_cost_tool_life(0.25, 0, 5, 60) == pytest.approx(3 * 5)
    for n in (1.0, 1.5, 0.0, -0.2):
        assert f.min_cost_tool_life(n, 2, 5, 60) is None
        assert f.max_rate_tool_life(n, 2) is None


def test_min_cost_life_longer_than_max_rate_life():
    assert f.min_cost_tool_life(0.3, 1, 4, 90) > f.max_rate_tool_life(0.3, 1)
    assert math.isfinite(f.min_cost_tool_life(0.3, 1, 4, 90))
