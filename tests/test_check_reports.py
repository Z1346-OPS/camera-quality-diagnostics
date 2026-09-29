"""跨报告关联键检查测试。"""

import csv
from uuid import uuid4

import pytest

from src.check_reports import (
    COLOR_FIELDS,
    QUALITY_FIELDS,
    main,
    reconcile_reports,
)
from src.report import append_color_record, append_quality_record


def test_reconcile_reports_detects_both_unmatched_sides(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_quality_record(2, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    append_color_record(3, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    before_quality, before_color = quality.read_bytes(), color.read_bytes()
    assert reconcile_reports(quality, color) == (
        {(run_id, 1)}, {(run_id, 2)}, {(run_id, 3)}
    )
    assert main([str(quality), str(color)]) == 1
    output = capsys.readouterr().out
    assert "匹配: 1 条；仅质量: 1 条；仅颜色: 1 条" in output
    assert f"仅质量: run_id={run_id} frame_count=2" in output
    assert f"仅颜色: run_id={run_id} frame_count=3" in output
    assert quality.read_bytes() == before_quality
    assert color.read_bytes() == before_color


def test_reconcile_reports_all_matched(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    append_quality_record(7, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(7, 100, 100, 100, color,
                        scene_label="unspecified", run_id=run_id)
    assert main([str(quality), str(color)]) == 0
    assert "一一对应" in capsys.readouterr().out


def test_reconcile_reports_can_check_one_run_without_hiding_history(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    selected, historical = uuid4().hex, uuid4().hex
    append_quality_record(7, 100, 0, 0, 10, 10, quality, run_id=selected)
    append_color_record(7, 100, 100, 100, color,
                        scene_label="white_paper", run_id=selected)
    append_color_record(8, 100, 100, 100, color,
                        scene_label="unspecified", run_id=historical)
    assert main([str(quality), str(color)]) == 1
    capsys.readouterr()
    assert reconcile_reports(quality, color, run_id=selected) == (
        {(selected, 7)}, set(), set()
    )
    assert main(["--run-id", selected, str(quality), str(color)]) == 0
    output = capsys.readouterr().out
    assert f"检查批次: {selected}" in output
    assert "不代表全部历史记录均配对" in output


def test_selected_run_still_reports_missing_records(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(2, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    assert main(["--run-id", run_id, str(quality), str(color)]) == 1
    output = capsys.readouterr().out
    assert "匹配: 0 条；仅质量: 1 条；仅颜色: 1 条" in output
    assert f"仅质量: run_id={run_id} frame_count=1" in output
    assert f"仅颜色: run_id={run_id} frame_count=2" in output


def test_selected_run_rejects_unknown_or_invalid_id(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    assert main(["--run-id", uuid4().hex, str(quality), str(color)]) == 2
    assert "所选批次没有记录" in capsys.readouterr().err
    assert main(["--run-id", "../bad", str(quality), str(color)]) == 2
    assert "run_id 必须" in capsys.readouterr().err


def test_selected_run_does_not_hide_invalid_history(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    selected, historical = uuid4().hex, uuid4().hex
    append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=selected)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="white_paper", run_id=selected)
    for _ in range(2):
        append_color_record(2, 100, 100, 100, color,
                            scene_label="unspecified", run_id=historical)
    assert main(["--run-id", selected, str(quality), str(color)]) == 2
    assert "重复" in capsys.readouterr().err


@pytest.mark.parametrize("field,value", [
    ("frame_count", "0"), ("frame_count", "abc"),
    ("run_id", "=1+1"), ("run_id", ""),
])
def test_reconcile_reports_rejects_bad_keys(tmp_path, field, value, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="unspecified", run_id=run_id)
    with quality.open("a", newline="", encoding="utf-8") as report:
        row = ["time", 2, 100, 0, 0, 10, 10, run_id]
        row[QUALITY_FIELDS.index(field)] = value
        csv.writer(report).writerow(row)
    assert main([str(quality), str(color)]) == 2
    assert "检查失败" in capsys.readouterr().err


def test_reconcile_reports_rejects_duplicate_key(tmp_path):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    run_id = uuid4().hex
    for _ in range(2):
        append_quality_record(1, 100, 0, 0, 10, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="unspecified", run_id=run_id)
    with pytest.raises(ValueError, match="重复"):
        reconcile_reports(quality, color)


def test_reconcile_reports_rejects_wrong_header_and_missing_file(tmp_path, capsys):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    with quality.open("w", newline="", encoding="utf-8-sig") as report:
        csv.writer(report).writerow(COLOR_FIELDS)
    with color.open("w", newline="", encoding="utf-8-sig") as report:
        csv.writer(report).writerow(COLOR_FIELDS)
    assert main([str(quality), str(color)]) == 2
    assert "表头不匹配" in capsys.readouterr().err
    quality.unlink()
    assert main([str(quality), str(color)]) == 2
    assert "检查失败" in capsys.readouterr().err
