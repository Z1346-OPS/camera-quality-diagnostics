"""CSV 质量报告测试。"""

import csv
import re
import pytest

from src.report import append_camera_event, append_color_record, append_quality_record


def test_labeled_colors_preserve_labels_and_one_header(tmp_path):
    path = tmp_path / "labeled.csv"
    labels = ["unspecified", "white_paper", "colored_object", "white_restored"]
    for frame_count, label in enumerate(labels, 1):
        append_color_record(frame_count, 100, 110, 120, path, scene_label=label)
    with path.open(newline="", encoding="utf-8-sig") as report:
        rows = list(csv.DictReader(report))
    assert [row["scene_label"] for row in rows] == labels
    assert all(row["channel_spread"] == "20.0" for row in rows)


def test_labeled_colors_reject_old_schema_without_changing_file(tmp_path):
    path = tmp_path / "colors.csv"
    append_color_record(1, 100, 110, 120, path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="表头不匹配"):
        append_color_record(2, 100, 110, 120, path, scene_label="white_paper")
    assert path.read_bytes() == before


def test_color_report_rejects_unknown_scene(tmp_path):
    path = tmp_path / "colors.csv"
    with pytest.raises(ValueError, match="场景标签"):
        append_color_record(1, 100, 110, 120, path, scene_label="=1+1")
    assert not path.exists()


def test_color_report_appends_records_with_one_header(tmp_path):
    path = tmp_path / "reports" / "colors.csv"
    assert append_color_record(10, 94.0, 104.2, 124.2, path) == path
    append_color_record(20, 142.7, 142.4, 143.1, path)
    with path.open(newline="", encoding="utf-8-sig") as report:
        reader = csv.DictReader(report)
        rows = list(reader)
        assert reader.fieldnames == [
            "recorded_at", "frame_count", "blue_mean", "green_mean",
            "red_mean", "channel_spread",
        ]
    assert len(rows) == 2
    assert rows[0]["blue_mean"] == "94.0"
    assert rows[0]["green_mean"] == "104.2"
    assert rows[0]["red_mean"] == "124.2"
    assert rows[0]["channel_spread"] == "30.2"
    assert rows[1]["channel_spread"] == "0.7"
    assert rows[1]["frame_count"] == "20"
    assert re.search(r"\.\d{3}[+-]\d{2}:\d{2}$", rows[1]["recorded_at"])


def test_append_camera_event_creates_event_report(tmp_path):
    report_path = tmp_path / "reports" / "camera_events.csv"

    result = append_camera_event(
        42,
        "read_failed",
        "读取画面失败",
        report_path,
    )

    assert result == report_path
    with report_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 1
    assert rows[0]["frame_count"] == "42"
    assert rows[0]["event"] == "read_failed"
    assert rows[0]["message"] == "读取画面失败"
    assert re.search(r"\.\d{3}[+-]\d{2}:\d{2}$", rows[0]["recorded_at"])


def test_append_camera_event_reuses_header(tmp_path):
    report_path = tmp_path / "camera_events.csv"

    append_camera_event(10, "read_failed", "第一次失败", report_path)
    append_camera_event(20, "read_failed", "第二次失败", report_path)

    with report_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        lines = csv_file.readlines()

    assert len(lines) == 3
    assert lines[0].startswith("recorded_at,frame_count,event,message")


def test_append_quality_record_creates_directory_and_csv(tmp_path):
    report_path = tmp_path / "reports" / "camera_quality.csv"

    result = append_quality_record(12, 125.64, 1.23, 4.56, 230.04, 33.35, report_path)

    assert result == report_path
    with report_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 1
    assert rows[0]["frame_count"] == "12"
    assert rows[0]["brightness"] == "125.6"
    assert rows[0]["dark_ratio"] == "1.2"
    assert rows[0]["bright_ratio"] == "4.6"
    assert rows[0]["sharpness"] == "230.0"
    assert rows[0]["contrast"] == "33.4"
    assert re.search(r"\.\d{3}[+-]\d{2}:\d{2}$", rows[0]["recorded_at"])


def test_append_quality_record_reuses_header(tmp_path):
    report_path = tmp_path / "camera_quality.csv"

    append_quality_record(1, 100, 2, 3, 200, 20, report_path)
    append_quality_record(2, 110, 4, 5, 210, 30, report_path)

    with report_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        lines = csv_file.readlines()

    assert len(lines) == 3
    assert lines[0].startswith("recorded_at,frame_count,brightness")
