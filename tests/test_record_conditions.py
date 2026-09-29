"""按批次保存人工条件备注，不修改原始报告。"""

import csv
import json
from uuid import uuid4

import pytest

from src import record_conditions as conditions_module
from src.record_conditions import record_conditions
from src.report import append_color_record, append_quality_record


def _pair(quality, color, run_id):
    append_quality_record(1, 100, 0, 0, 5, 10, quality, run_id=run_id)
    append_color_record(1, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)


def test_record_conditions_links_note_and_preserves_csv(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "conditions.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id)
    before = quality.read_bytes(), color.read_bytes()
    assert record_conditions(run_id, "光照基本没变；纸距未测", quality, color, target) == target
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["run_id"] == run_id
    assert result["source"] == "operator_note"
    assert result["conditions_note"] == "光照基本没变；纸距未测"
    assert result["note_recorded_at"]
    assert (quality.read_bytes(), color.read_bytes()) == before


def test_record_conditions_rejects_unpaired_or_missing_run(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "conditions.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id)
    append_quality_record(2, 100, 0, 0, 5, 10, quality, run_id=run_id)
    with pytest.raises(ValueError, match="未配对"):
        record_conditions(run_id, "已记录条件", quality, color, target)
    assert not target.exists()
    with pytest.raises(ValueError, match="没有记录"):
        record_conditions(uuid4().hex, "已记录条件", quality, color, target)
    assert not target.exists()


def test_record_conditions_rejects_invalid_id_or_empty_note(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "conditions.json"
    ))
    with pytest.raises(ValueError, match="备注不能为空"):
        record_conditions(uuid4().hex, "   ", quality, color, target)
    with pytest.raises(ValueError, match="run_id"):
        record_conditions("../bad", "已记录条件", quality, color, target)
    assert not target.exists()


def test_record_conditions_never_overwrites_existing_file(tmp_path):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "conditions.json"
    ))
    run_id = uuid4().hex
    _pair(quality, color, run_id)
    target.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        record_conditions(run_id, "新备注", quality, color, target)
    assert target.read_text(encoding="utf-8") == "keep"


def test_cli_reports_csv_parse_errors(monkeypatch, capsys):
    def fail(*args):
        raise csv.Error("坏 CSV")

    monkeypatch.setattr(conditions_module, "record_conditions", fail)
    assert conditions_module.main([uuid4().hex, "--note", "条件未知"]) == 1
    assert "条件记录失败: 坏 CSV" in capsys.readouterr().err
