"""跨批次白纸差值汇总测试。"""

from uuid import uuid4

import pytest

from src.export_pairs import export_run
from src.report import append_color_record, append_quality_record
from src.summarize_white_runs import main, summarize_white_runs


def _run(tmp_path, name, before, after=None):
    folder = tmp_path / name
    folder.mkdir()
    quality, color, target = (folder / filename for filename in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    append_quality_record(1, before, 0, 0, 5, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    if after is not None:
        append_quality_record(2, after, 0, 0, 7, 12, quality, run_id=run_id)
        append_color_record(2, 99, 100, 101, color,
                            scene_label="white_restored", run_id=run_id)
    export_run(run_id, quality, color, target)
    return target, run_id


def test_two_runs_are_counted_once_each(tmp_path, capsys):
    first, first_id = _run(tmp_path, "first", 100, 120)
    second, second_id = _run(tmp_path, "second", 130, 125)
    before = first.read_bytes(), second.read_bytes()

    result = summarize_white_runs([first, second])
    assert result["run_count"] == 2
    assert set(result["runs"]) == {first_id, second_id}
    assert result["ranges"]["brightness"] == {"min": -5, "max": 20}
    assert result["runs"][first_id]["before_count"] == 1
    assert main([str(first), str(second)]) == 0
    assert "跨 2 个批次" in capsys.readouterr().out
    assert (first.read_bytes(), second.read_bytes()) == before


def test_one_run_does_not_claim_cross_run_range(tmp_path, capsys):
    report, _ = _run(tmp_path, "single", 100, 120)
    result = summarize_white_runs([report])
    assert result["run_count"] == 1
    assert result["ranges"] is None
    assert main([str(report)]) == 0
    assert "尚不能给出跨批次范围" in capsys.readouterr().out


def test_duplicate_run_id_is_rejected_even_with_other_filename(tmp_path, capsys):
    report, run_id = _run(tmp_path, "original", 100, 120)
    alias = tmp_path / "alias.json"
    alias.write_bytes(report.read_bytes())
    with pytest.raises(ValueError, match=run_id):
        summarize_white_runs([report, alias])
    assert main([str(report), str(alias)]) == 1
    assert "重复的 run_id" in capsys.readouterr().err


def test_missing_restored_scene_is_rejected(tmp_path):
    report, _ = _run(tmp_path, "incomplete", 100)
    with pytest.raises(ValueError, match="white_restored"):
        summarize_white_runs([report])


def test_no_input_is_rejected():
    with pytest.raises(ValueError, match="至少提供"):
        summarize_white_runs([])
