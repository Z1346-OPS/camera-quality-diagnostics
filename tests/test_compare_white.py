"""同批次白纸标签的描述性差值测试。"""

from uuid import uuid4

import pytest

from src.compare_white import compare_white, main
from src.export_pairs import export_run
from src.report import append_color_record, append_quality_record


def _save_pair(quality, color, run_id, frame, label, brightness, sharpness,
               contrast, channels):
    append_quality_record(frame, brightness, 0, 0, sharpness, contrast,
                          quality, run_id=run_id)
    append_color_record(frame, *channels, color,
                        scene_label=label, run_id=run_id)


def test_compare_white_uses_scene_means_and_keeps_json_unchanged(tmp_path, capsys):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    _save_pair(quality, color, run_id, 1, "white_paper", 100, 5, 10, (100, 100, 100))
    _save_pair(quality, color, run_id, 2, "white_paper", 120, 7, 12, (100, 100, 100))
    _save_pair(quality, color, run_id, 3, "colored_object", 200, 80, 40, (40, 50, 60))
    _save_pair(quality, color, run_id, 4, "white_restored", 130, 8, 9, (99, 100, 101))
    export_run(run_id, quality, color, target)
    before_bytes = target.read_bytes()

    result = compare_white(target)
    assert (result["before_count"], result["after_count"]) == (2, 1)
    assert result["metrics"]["brightness"]["difference"] == 20
    assert result["metrics"]["sharpness"]["difference"] == 2
    assert result["metrics"]["contrast"]["difference"] == -2
    assert result["metrics"]["channel_spread"]["difference"] == 2
    assert main([str(target)]) == 0
    assert "恢复减首次 +20.0" in capsys.readouterr().out
    assert target.read_bytes() == before_bytes


def test_compare_white_requires_both_labels(tmp_path, capsys):
    quality, color, target = (tmp_path / name for name in (
        "quality.csv", "color.csv", "pairs.json"
    ))
    run_id = uuid4().hex
    _save_pair(quality, color, run_id, 1, "white_paper", 100, 5, 10, (100, 100, 100))
    export_run(run_id, quality, color, target)
    with pytest.raises(ValueError, match="white_restored"):
        compare_white(target)
    assert main([str(target)]) == 1
    assert "比较失败" in capsys.readouterr().err


def test_compare_white_rejects_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json")]) == 1
    assert "比较失败" in capsys.readouterr().err
