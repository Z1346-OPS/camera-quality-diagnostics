"""三场景采集标签顺序检查，不使用真实摄像头。"""

import json
from uuid import uuid4

import pytest

from src.validate_capture import main, validate_capture


def _report(path, labels, order=None):
    frames = []
    for number, label in enumerate(labels, start=1):
        frames.append({
            "frame_count": number,
            "quality": {"recorded_at": "2026-09-29T10:00:00+08:00",
                        "brightness": 100, "dark_ratio": 0, "bright_ratio": 0,
                        "sharpness": 5, "contrast": 10},
            "color": {"recorded_at": "2026-09-29T10:00:00+08:00",
                      "blue_mean": 100, "green_mean": 100, "red_mean": 100,
                      "channel_spread": 0, "scene_label": label},
        })
    if order is not None:
        frames = [frames[index] for index in order]
    run_id = uuid4().hex
    path.write_text(json.dumps({"schema_version": 1, "run_id": run_id,
                                "record_count": len(frames), "frames": frames}), encoding="utf-8")
    return run_id


def test_valid_order_uses_frame_number_and_does_not_modify_report(tmp_path, capsys):
    path = tmp_path / "pairs.json"
    run_id = _report(path, ["white_paper", "colored_object", "white_restored"], [2, 0, 1])
    before = path.read_bytes()
    assert validate_capture(path) == (run_id, ("white_paper", "colored_object", "white_restored"))
    assert main([str(path)]) == 0
    assert "不能确认画面内容" in capsys.readouterr().out
    assert path.read_bytes() == before


@pytest.mark.parametrize("labels", [
    ["white_paper", "white_paper", "colored_object", "white_restored"],
    ["white_paper", "white_restored", "colored_object"],
    ["white_paper", "colored_object"],
    ["unspecified", "colored_object", "white_restored"],
])
def test_wrong_sequence_is_rejected(tmp_path, labels, capsys):
    path = tmp_path / "pairs.json"
    _report(path, labels)
    before = path.read_bytes()
    assert main([str(path)]) == 1
    assert "标签顺序不符" in capsys.readouterr().err
    assert path.read_bytes() == before


def test_invalid_report_is_rejected_by_existing_format_check(tmp_path, capsys):
    path = tmp_path / "pairs.json"
    _report(path, ["white_paper", "colored_object", "white_restored"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["record_count"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(path)]) == 1
    assert "记录数" in capsys.readouterr().err
