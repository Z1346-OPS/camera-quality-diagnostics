"""批次 JSON 导出测试。"""

import json
from uuid import uuid4

import pytest

from src.export_pairs import export_run
from src.report import append_color_record, append_quality_record


def _pair(quality, color, run_id, frame):
    append_quality_record(frame, 100, 1, 2, 30, 40, quality, run_id=run_id)
    append_color_record(frame, 99, 100, 101, color,
                        scene_label="white_paper", run_id=run_id)


def test_export_selected_run_without_touching_sources(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    selected, historical = uuid4().hex, uuid4().hex
    _pair(quality, color, selected, 7)
    _pair(quality, color, selected, 2)
    append_color_record(3, 2, 3, 4, color,
                        scene_label="unspecified", run_id=historical)
    before = quality.read_bytes(), color.read_bytes()

    assert export_run(selected, quality, color, target) == target
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["run_id"] == selected
    assert result["record_count"] == 2
    assert [row["frame_count"] for row in result["frames"]] == [2, 7]
    assert result["frames"][0]["quality"]["brightness"] == 100.0
    assert result["frames"][0]["color"]["scene_label"] == "white_paper"
    assert result["frames"][0]["color"]["channel_spread"] == 2.0
    assert (quality.read_bytes(), color.read_bytes()) == before


def test_export_rejects_unpaired_selected_run_and_missing_run(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id, 1)
    append_quality_record(2, 100, 0, 0, 1, 1, quality, run_id=run_id)
    with pytest.raises(ValueError, match="未配对"):
        export_run(run_id, quality, color, target)
    assert not target.exists()
    with pytest.raises(ValueError, match="没有配对"):
        export_run(uuid4().hex, quality, color, target)
    assert not target.exists()


def test_export_never_overwrites_existing_json(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id, 1)
    target.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_run(run_id, quality, color, target)
    assert target.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("bad_value", ["not-a-number", "nan", "inf"])
def test_export_rejects_invalid_metric(tmp_path, bad_value):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id, 1)
    data = quality.read_text(encoding="utf-8-sig").replace("100.0", bad_value)
    quality.write_text(data, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="brightness"):
        export_run(run_id, quality, color, target)
    assert not target.exists()


def test_export_rejects_invalid_run_id_before_reading_files(tmp_path):
    with pytest.raises(ValueError, match="run_id"):
        export_run("../outside", tmp_path / "missing.csv", tmp_path / "missing2.csv")
