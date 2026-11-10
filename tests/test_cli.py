import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from process_cost.breakeven import Line
from process_cost.charts import ascii_chart, svg_chart
from process_cost.cli import main

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def run(*args):
    return subprocess.run([sys.executable, "-m", "process_cost", *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


def test_bare_json_runs_full_report():
    r = run("examples/turning_shaft.json")
    assert r.returncode == 0, r.stderr
    for text in ("Estimate: CNC lathe", "Estimate: Manual lathe", "Break-even batch size",
                 "Sensitivity: CNC lathe", "min cost"):
        assert text in r.stdout


def test_estimate_milling_shows_cap_warning_and_outsource():
    r = run("estimate", "examples/milling_plate.json")
    assert r.returncode == 0, r.stderr
    assert "WARNING   : spindle capped at 8000 rpm" in r.stdout
    assert "Outsource: Outsource quote" in r.stdout


def test_breakeven_writes_valid_svg(tmp_path):
    out = tmp_path / "chart.svg"
    r = run("breakeven", "examples/turning_shaft.json", "--svg", str(out))
    assert r.returncode == 0, r.stderr
    assert "<- break-even" in r.stdout
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert len(root.findall("{http://www.w3.org/2000/svg}polyline")) == 2


def test_sensitivity_custom_step():
    r = run("sensitivity", "examples/turning_shaft.json", "--step", "5")
    assert r.returncode == 0, r.stderr
    assert "-10% $/part" in r.stdout and "+5% $/part" in r.stdout


def test_materials_command():
    r = run("materials")
    assert r.returncode == 0
    for key in ("aisi_1018", "aisi_1045", "ss_304", "al_6061", "grey_cast_iron",
                "brass_free_cutting", "ti_6al_4v", "INDICATIVE"):
        assert key in r.stdout


def test_output_is_ascii():
    r = run("report", "examples/milling_plate.json")
    assert r.returncode == 0, r.stderr
    r.stdout.encode("ascii")


def _write(tmp_path, data):
    p = tmp_path / "job.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return str(p)


def test_bad_input_exit_2(tmp_path, turning_dict):
    r = run("estimate", _write(tmp_path, turning_dict(op={"D0_mm": -1})))
    assert r.returncode == 2
    assert r.stderr.startswith("error:") and "D0_mm" in r.stderr


def test_breakeven_needs_two_scenarios_exit_2(tmp_path, turning_dict, capsys):
    assert main(["breakeven", _write(tmp_path, turning_dict())]) == 2
    assert "exactly 2 scenarios" in capsys.readouterr().err


def test_missing_file_exit_2(capsys):
    assert main(["estimate", "does_not_exist.json"]) == 2
    assert "not found" in capsys.readouterr().err


def test_invalid_json_exit_2(tmp_path, capsys):
    assert main(["estimate", _write(tmp_path, "{oops")]) == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_bad_step_exit_2(capsys):
    assert main(["sensitivity", str(EX / "turning_shaft.json"), "--step", "60"]) == 2


def test_unknown_command_exit_2():
    with pytest.raises(SystemExit) as exc:
        main(["--bogus"])
    assert exc.value.code == 2


def test_single_job_report_skips_breakeven(tmp_path, turning_dict, capsys):
    assert main(["report", _write(tmp_path, turning_dict())]) == 0
    assert "break-even skipped" in capsys.readouterr().out


def test_ascii_chart_marks_break_even():
    a, b = Line("A", 100, 5), Line("B", 20, 7)
    text = ascii_chart([a, b], 40.0)
    lines = text.splitlines()
    assert len(lines) == 16 + 4
    col = 12 + round(math.log10(40) / 4 * 60)  # label (10) + " |" then Q* column
    marks = [ln.ljust(80)[col] for ln in lines[:16]]
    assert all(m in "|AB*" for m in marks)  # curves may draw over the marker where they cross
    assert marks.count("|") >= 14
    assert "A = A" in text and "| = break-even" in text


def test_svg_escapes_names_and_marks_q_star():
    svg = svg_chart([Line("R&D <cell>", 100, 5), Line("B", 20, 7)], 40.0)
    root = ET.fromstring(svg)  # parses only if escaped correctly
    assert "R&amp;D &lt;cell&gt;" in svg
    assert any(el.get("stroke-dasharray") for el in root.iter("{http://www.w3.org/2000/svg}line"))
    assert "Q* = 40.0" in svg


def test_svg_with_one_scenario_is_an_error(tmp_path, turning_dict, capsys):
    out = tmp_path / "c.svg"
    assert main(["report", _write(tmp_path, turning_dict()), "--svg", str(out)]) == 2
    assert "--svg needs exactly 2 scenarios" in capsys.readouterr().err
    assert not out.exists()


def test_extreme_step_does_not_crash():
    assert main(["sensitivity", str(EX / "turning_shaft.json"), "--step", "49.9"]) == 0


def test_sensitivity_never_prints_negative_zero():
    r = run("sensitivity", str(EX / "turning_shaft.json"))
    assert "-0.0 " not in r.stdout and not r.stdout.rstrip().endswith("-0.0")


def test_non_ascii_scenario_name_does_not_crash(tmp_path, turning_dict):
    d = turning_dict()
    d["name"] = "Welle äö – test"
    r = run("estimate", _write(tmp_path, d))
    assert r.returncode == 0, r.stderr
