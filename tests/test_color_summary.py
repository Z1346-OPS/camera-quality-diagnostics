"""颜色报告只读汇总测试。"""

import csv

import pytest

from src.report import append_color_record
from src.summarize_colors import EXPECTED_FIELDS, main, summarize_color_report


def test_summary_groups_records_and_leaves_report_unchanged(tmp_path):
    path = tmp_path / "colors.csv"
    append_color_record(1, 100, 100, 102, path, scene_label="white_paper")
    append_color_record(2, 100, 100, 104, path, scene_label="white_paper")
    append_color_record(3, 100, 100, 120, path, scene_label="colored_object")
    before = path.read_bytes()
    summary = summarize_color_report(path)
    assert summary == {
        "white_paper": {"count": 2, "mean": 3.0, "min": 2.0, "max": 4.0},
        "colored_object": {"count": 1, "mean": 20.0, "min": 20.0, "max": 20.0},
    }
    assert path.read_bytes() == before


def test_summary_empty_report_and_cli(tmp_path, capsys):
    path = tmp_path / "empty.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as report:
        csv.writer(report).writerow(EXPECTED_FIELDS)
    assert summarize_color_report(path) == {}
    assert main([str(path)]) == 0
    assert "暂无记录" in capsys.readouterr().out


def test_summary_cli_displays_labels_and_statistics(tmp_path, capsys):
    path = tmp_path / "colors.csv"
    append_color_record(1, 100, 100, 110, path, scene_label="white_restored")
    assert main([str(path)]) == 0
    output = capsys.readouterr().out
    assert "恢复白纸 (white_restored) | 1 | 10.0 | 10.0 | 10.0" in output
    assert "不能用于标定或故障判定" in output


def test_summary_missing_file_returns_failure(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 1
    assert "汇总失败" in capsys.readouterr().err


def test_summary_rejects_old_report_schema(tmp_path):
    path = tmp_path / "old.csv"
    append_color_record(1, 100, 100, 110, path)
    with pytest.raises(ValueError, match="表头不匹配"):
        summarize_color_report(path)


@pytest.mark.parametrize("spread", ["abc", "nan", "inf", "-1", "256", ""])
def test_summary_rejects_bad_spread_without_partial_results(tmp_path, spread, capsys):
    path = tmp_path / "bad.csv"
    append_color_record(1, 100, 100, 110, path, scene_label="white_paper")
    with path.open("a", newline="", encoding="utf-8") as report:
        csv.writer(report).writerow(["time", 2, 100, 100, 110, spread, "white_paper"])
    assert main([str(path)]) == 1
    output = capsys.readouterr()
    assert "第 3 行" in output.err
    assert "记录数" not in output.out


@pytest.mark.parametrize("row", [
    ["time", 1, 100, 100, 110, 10, "unknown"],
    ["time", 1, 100, 100, 110, 10],
    ["time", 1, 100, 100, 110, 10, "white_paper", "extra"],
])
def test_summary_rejects_bad_labels_and_row_shapes(tmp_path, row):
    path = tmp_path / "bad.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as report:
        writer = csv.writer(report)
        writer.writerow(EXPECTED_FIELDS)
        writer.writerow(row)
    with pytest.raises(ValueError, match="第 2 行"):
        summarize_color_report(path)
