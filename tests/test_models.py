import json

import pytest

from process_cost.materials import MATERIALS, TABLE, TOOL_MATERIALS, lookup
from process_cost.models import DEFAULT_APPROACH_MM, InputError, Outsource, load_job_file, parse_job_file


def err(d):
    with pytest.raises(InputError) as exc:
        parse_job_file(d)
    return str(exc.value)


def test_valid_turning_parses(turning_job):
    job = turning_job()
    assert job.kind == "turning"
    assert job.geometry.passes == 2
    assert job.vc_m_min == 200
    assert job.taylor_c == pytest.approx(185 * 15 ** 0.3)


@pytest.mark.parametrize("key,value,needle", [
    ("D0_mm", -40, "D0_mm: must be > 0"),
    ("length_mm", 0, "length_mm: must be > 0"),
    ("feed_mm_per_rev", 0, "feed_mm_per_rev: must be > 0"),
    ("ap_mm", -1, "ap_mm: must be > 0"),
    ("Vc_m_per_min", 0, "Vc_m_per_min: must be > 0"),
    ("taylor_n", 1.0, "strictly between 0 and 1"),
    ("taylor_n", 0, "strictly between 0 and 1"),
    ("taylor_C", -3, "taylor_C: must be > 0"),
    ("approach_mm", -1, "approach_mm: must be >= 0"),
    ("D0_mm", True, "must be a number"),
    ("D0_mm", "40", "must be a number"),
])
def test_bad_operation_values(turning_dict, key, value, needle):
    assert needle in err(turning_dict(op={key: value}))


@pytest.mark.parametrize("key,value,needle", [
    ("machine_rate_per_h", 0, "machine_rate_per_h: must be > 0"),
    ("setup_min", -1, "setup_min: must be >= 0"),
    ("cost_per_edge", -0.5, "cost_per_edge: must be >= 0"),
    ("scrap_rate", 1.0, "scrap_rate: must be in [0, 1)"),
    ("scrap_rate", -0.1, "scrap_rate: must be in [0, 1)"),
])
def test_bad_cost_values(turning_dict, key, value, needle):
    assert needle in err(turning_dict(costs={key: value}))


def test_d1_not_smaller_than_d0(turning_dict):
    assert "must be smaller than D0_mm" in err(turning_dict(op={"D1_mm": 40}))


def test_unknown_material(turning_dict):
    assert "unknown material 'unobtainium'" in err(turning_dict(op={"material": "unobtainium"}))


def test_unknown_tool_material(turning_dict):
    assert "unknown tool_material" in err(turning_dict(op={"tool_material": "diamond"}))


def test_missing_required_field(turning_dict):
    msg = err(turning_dict(drop=["costs.machine_rate_per_h"]))
    assert "missing required field 'machine_rate_per_h'" in msg


def test_missing_feed_is_not_defaulted(turning_dict):
    assert "feed_mm_per_rev" in err(turning_dict(drop=["operation.feed_mm_per_rev"]))


def test_missing_batch_size(turning_dict):
    assert "batch_size" in err(turning_dict(drop=["batch_size"]))


def test_non_integer_batch_size(turning_dict):
    assert "whole number" in err(turning_dict(batch_size=10.5))


def test_typo_key_suggests_fix(turning_dict):
    d = turning_dict()
    d["costs"]["machine_rate"] = 60
    assert "did you mean 'machine_rate_per_h'" in err(d)


def test_wrong_operation_type(turning_dict):
    assert "'turning' or 'milling'" in err(turning_dict(op={"type": "grinding"}))


def test_approach_default_is_documented_not_silent(turning_dict):
    job = parse_job_file(turning_dict(drop=["operation.approach_mm"])).scenarios[0]
    assert job.geometry.approach_mm == DEFAULT_APPROACH_MM == 2.0
    assert any("approach_mm not given" in n for n in job.notes)


def test_setup_rate_defaults_to_machine_rate_with_note(turning_job):
    job = turning_job()
    assert job.setup_rate_h == job.machine_rate_h
    assert any("setup_rate_per_h" in n for n in job.notes)


def test_vc_from_table_with_note(turning_dict):
    job = parse_job_file(turning_dict(drop=["operation.Vc_m_per_min"])).scenarios[0]
    assert job.vc_m_min == TABLE[("aisi_1045", "coated_carbide")].vc_turning
    assert any("from indicative table" in n for n in job.notes)


def test_taylor_n_override_rederives_c(turning_dict):
    job = parse_job_file(turning_dict(op={"taylor_n": 0.25})).scenarios[0]
    assert job.taylor_c == pytest.approx(185 * 15 ** 0.25)


def test_custom_material_requires_all_taylor_data(turning_dict):
    msg = err(turning_dict(op={"material": "custom", "taylor_n": 0.3}))
    assert "taylor_C" in msg
    job = parse_job_file(turning_dict(op={"material": "custom", "taylor_n": 0.3, "taylor_C": 400})).scenarios[0]
    assert job.taylor_c == 400


def test_milling_passes_from_depth(milling_dict):
    d = milling_dict(drop=["operation.passes"], op={"total_depth_mm": 12, "ap_mm": 5})
    assert parse_job_file(d).scenarios[0].geometry.passes == 3  # ceil(12/5)


def test_milling_passes_and_depth_conflict(milling_dict):
    assert "not both" in err(milling_dict(op={"total_depth_mm": 12}))


def test_milling_needs_passes_or_depth(milling_dict):
    assert "milling needs" in err(milling_dict(drop=["operation.passes"]))


def test_milling_lead_in_required(milling_dict):
    assert "lead_in_out_mm" in err(milling_dict(drop=["operation.lead_in_out_mm"]))


def test_milling_teeth_whole_number(milling_dict):
    assert "whole number" in err(milling_dict(op={"teeth": 2.5}))


def test_turning_key_rejected_in_milling(milling_dict):
    assert "unknown key 'D0_mm'" in err(milling_dict(op={"D0_mm": 40}))


def _scen(base, scenarios):
    d = dict(base)
    d["scenarios"] = scenarios
    return d


def test_scenarios_inherit_and_override(turning_dict):
    d = _scen(turning_dict(), [{"name": "A"}, {"name": "B", "costs": {"machine_rate_per_h": 99}}])
    jf = parse_job_file(d)
    a, b = jf.scenarios
    assert a.machine_rate_h == 60 and b.machine_rate_h == 99
    assert b.handling_min == a.handling_min
    assert jf.has_scenarios


def test_duplicate_scenario_names(turning_dict):
    assert "duplicate" in err(_scen(turning_dict(), [{"name": "A"}, {"name": "A"}]))


def test_empty_scenarios(turning_dict):
    assert "non-empty list" in err(_scen(turning_dict(), []))


def test_unknown_scenario_type(turning_dict):
    assert "'machining' or 'outsource'" in err(_scen(turning_dict(), [{"name": "A", "type": "magic"}]))


def test_outsource_scenario(turning_dict):
    d = _scen(turning_dict(), [{"name": "A"},
                               {"name": "Buy", "type": "outsource", "price_per_part": 20, "fixed_fee": 0}])
    out = parse_job_file(d).scenarios[1]
    assert isinstance(out, Outsource)
    assert out.batch_size == 10


def test_outsource_requires_price(turning_dict):
    d = _scen(turning_dict(), [{"name": "Buy", "type": "outsource", "fixed_fee": 0}])
    assert "price_per_part" in err(d)


def test_load_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"name": "x",', encoding="utf-8")
    with pytest.raises(InputError, match="invalid JSON"):
        load_job_file(p)


def test_load_missing_file(tmp_path):
    with pytest.raises(InputError, match="not found"):
        load_job_file(tmp_path / "nope.json")


def test_load_round_trip(tmp_path, turning_dict):
    p = tmp_path / "job.json"
    p.write_text(json.dumps(turning_dict()), encoding="utf-8")
    assert load_job_file(p).scenarios[0].name == "test turning"


def test_materials_table_complete_and_in_ranges():
    assert len(MATERIALS) >= 7 and set(TOOL_MATERIALS) == {"hss", "carbide", "coated_carbide"}
    for (mat, tool), d in TABLE.items():
        if tool == "hss":
            assert 0.08 <= d.taylor_n <= 0.2
        else:
            assert 0.2 <= d.taylor_n <= 0.5
        assert 0.15 <= d.f_turning <= 0.4
        assert 0.05 <= d.fz_milling <= 0.2
        hss = TABLE[(mat, "hss")].vc_turning
        assert 0.20 <= hss / TABLE[(mat, "coated_carbide")].vc_turning <= 0.35


@pytest.mark.parametrize("mat,lo,hi", [
    ("aisi_1018", 180, 250), ("aisi_1045", 150, 220), ("ss_304", 100, 160), ("al_6061", 300, 600),
    ("grey_cast_iron", 100, 180), ("brass_free_cutting", 200, 300), ("ti_6al_4v", 40, 80)])
def test_carbide_turning_speeds_in_published_ranges(mat, lo, hi):
    for tool in ("carbide", "coated_carbide"):
        assert lo <= lookup(mat, tool).vc_turning <= hi
