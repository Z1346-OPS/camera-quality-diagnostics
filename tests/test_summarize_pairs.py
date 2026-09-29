"""配对 JSON 描述性汇总测试。"""

import copy
import json
from uuid import uuid4

import pytest

from src.summarize_pairs import main, summarize_pairs


def _frame(number, label, brightness, sharpness):
    return {
        "frame_count": number,
        "quality": {"recorded_at": "2026-09-29T10:00:00+08:00",
                    "brightness": brightness, "dark_ratio": 0, "bright_ratio": 0,
                    "sharpness": sharpness, "contrast": 10},
        "color": {"recorded_at": "2026-09-29T10:00:00+08:00",
                  "blue_mean": 100, "green_mean": 101, "red_mean": 102,
                  "channel_spread": 2, "scene_label": label},
    }


def _report(tmp_path):
    path = tmp_path / "pairs.json"
    data = {"schema_version": 1, "run_id": uuid4().hex, "record_count": 3,
            "frames": [_frame(1, "white_paper", 100, 5),
                       _frame(2, "colored_object", 80, 50),
                       _frame(3, "white_paper", 120, 7)]}
    return path, data


def _save(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_summarize_groups_by_scene_without_changing_json(tmp_path, capsys):
    path, data = _report(tmp_path)
    _save(path, data)
    before = path.read_bytes()
    groups = summarize_pairs(path)
    assert groups["white_paper"]["count"] == 2
    assert groups["white_paper"]["metrics"]["brightness"] == {
        "mean": 110, "min": 100, "max": 120,
    }
    assert groups["white_paper"]["metrics"]["sharpness"]["mean"] == 6
    assert groups["colored_object"]["count"] == 1
    assert main([str(path)]) == 0
    assert "少量样本不能用于设定阈值" in capsys.readouterr().out
    assert path.read_bytes() == before


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(schema_version=2), "版本"),
    (lambda d: d.update(run_id="../bad"), "run_id"),
    (lambda d: d.update(record_count=2), "记录数"),
    (lambda d: d["frames"].clear(), "记录数"),
    (lambda d: d["frames"][1].update(frame_count=1), "帧号"),
    (lambda d: d["frames"][0]["color"].update(scene_label="unknown"), "场景"),
    (lambda d: d["frames"][0]["color"].update(scene_label=[]), "场景"),
    (lambda d: d["frames"][0]["quality"].update(brightness="100"), "brightness"),
    (lambda d: d["frames"][0]["quality"].update(brightness=300), "brightness"),
    (lambda d: d["frames"][0]["quality"].update(dark_ratio=-1), "dark_ratio"),
    (lambda d: d["frames"][0]["color"].update(blue_mean=float("nan")), "blue_mean"),
    (lambda d: d["frames"][0]["color"].update(blue_mean=10 ** 400), "blue_mean"),
    (lambda d: d["frames"][0]["quality"].pop("recorded_at"), "不完整"),
])
def test_summarize_rejects_bad_data(tmp_path, change, message):
    path, data = _report(tmp_path)
    data = copy.deepcopy(data)
    change(data)
    _save(path, data)
    with pytest.raises(ValueError, match=message):
        summarize_pairs(path)


def test_summarize_reports_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json")]) == 1
    assert "汇总失败" in capsys.readouterr().err


def test_summarize_rejects_overflowing_mean(tmp_path):
    path, data = _report(tmp_path)
    data["frames"][0]["quality"]["sharpness"] = 1e308
    data["frames"][2]["quality"]["sharpness"] = 1e308
    _save(path, data)
    with pytest.raises(ValueError, match="sharpness 数值过大"):
        summarize_pairs(path)
