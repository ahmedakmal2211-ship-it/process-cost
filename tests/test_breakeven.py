from pathlib import Path

import pytest

from process_cost.breakeven import BATCH_SIZES, Line, breakeven, comparison_sizes, line_for
from process_cost.cost import estimate
from process_cost.models import Outsource, load_job_file

EX = Path(__file__).resolve().parents[1] / "examples"


def test_integer_break_even_costs_equal_at_q_star():
    a, b = Line("A", 100, 5), Line("B", 20, 7)
    be = breakeven(a, b)
    assert be.kind == "crossing"
    assert be.q_star == pytest.approx((100 - 20) / (7 - 5))  # 40
    assert a.total(40) == pytest.approx(b.total(40))
    assert be.q_min == 41  # equal at 40, strictly cheaper from 41
    assert be.small_winner == "B" and be.scale_winner == "A"


def test_fractional_break_even_rounds_up_and_flips():
    a, b = Line("A", 100, 5), Line("B", 21, 7)
    be = breakeven(a, b)
    assert be.q_star == pytest.approx(79 / 2)  # 39.5
    assert be.q_min == 40
    assert b.per_part(39) < a.per_part(39)
    assert a.per_part(40) < b.per_part(40)


def test_break_even_symmetric_in_order():
    a, b = Line("A", 100, 5), Line("B", 21, 7)
    assert breakeven(a, b).q_star == pytest.approx(breakeven(b, a).q_star)
    assert breakeven(b, a).q_min == 40


def test_parallel_lines_no_break_even():
    be = breakeven(Line("A", 100, 5), Line("B", 50, 5))
    assert be.kind == "parallel"
    assert be.q_star is None
    assert be.scale_winner == "B"


def test_identical_lines():
    assert breakeven(Line("A", 10, 5), Line("B", 10, 5)).kind == "identical"


def test_negative_q_star_one_dominates():
    be = breakeven(Line("A", 10, 5), Line("B", 50, 7))
    assert be.q_star == pytest.approx(-20)
    assert be.kind == "dominant"
    assert be.scale_winner == "A"
    assert "every batch size" in be.message


def test_q_star_below_one_part_dominates():
    be = breakeven(Line("A", 10.5, 5), Line("B", 10, 7))
    assert be.q_star == pytest.approx(0.25)
    assert be.kind == "dominant" and be.q_min == 1


def test_line_for_job_matches_estimate(turning_job):
    job = turning_job()
    ln = line_for(job)
    e = estimate(job)
    assert ln.fixed == pytest.approx(30.0)
    assert ln.per_part(job.batch_size) == pytest.approx(e.cost_per_part)


def test_line_for_outsource():
    ln = line_for(Outsource("buy", price_per_part=20, fixed_fee=50, batch_size=10))
    assert (ln.fixed, ln.variable) == (50, 20)
    assert ln.per_part(10) == pytest.approx(25)


def test_comparison_sizes_include_break_even_neighbours():
    be = breakeven(Line("A", 100, 5), Line("B", 21, 7))
    sizes = comparison_sizes(be)
    assert 39 in sizes and 40 in sizes
    assert set(BATCH_SIZES) <= set(sizes)
    assert sizes == sorted(sizes)


def test_turning_example_break_even_is_sensible():
    jf = load_job_file(EX / "turning_shaft.json")
    a, b = (line_for(s) for s in jf.scenarios)
    be = breakeven(a, b)
    assert be.kind == "crossing"
    assert 10 <= be.q_min <= 1000
    assert a.total(be.q_star) == pytest.approx(b.total(be.q_star))
    # CNC (higher setup) wins at scale
    assert be.scale_winner == "CNC lathe"


def test_milling_example_outsource_break_even():
    jf = load_job_file(EX / "milling_plate.json")
    lines = [line_for(s) for s in jf.scenarios]
    be = breakeven(*lines)
    assert be.kind == "crossing"
    assert be.small_winner == "Outsource quote"
    assert 10 <= be.q_min <= 1000
