"""CSV 质量报告测试。"""

import csv

from src.report import append_quality_record


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
    assert rows[0]["recorded_at"]


def test_append_quality_record_reuses_header(tmp_path):
    report_path = tmp_path / "camera_quality.csv"

    append_quality_record(1, 100, 2, 3, 200, 20, report_path)
    append_quality_record(2, 110, 4, 5, 210, 30, report_path)

    with report_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        lines = csv_file.readlines()

    assert len(lines) == 3
    assert lines[0].startswith("recorded_at,frame_count,brightness")
