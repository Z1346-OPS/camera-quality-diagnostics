"""留证图片与 CSV 指标核对测试，仅使用合成图片。"""

from uuid import uuid4

import numpy as np
import pytest

from src.frame_evidence import save_frame_evidence
from src.report import append_color_record, append_quality_record
from src.verify_frame_metrics import compare_frame_metrics, main


def make_evidence(tmp_path, *, brightness=100, save_png=True):
    run_id = uuid4().hex
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    append_quality_record(7, brightness, 0, 0, 0, 0, quality, run_id=run_id)
    append_color_record(7, 100, 100, 100, color,
                        scene_label="white_paper", run_id=run_id)
    image = tmp_path / f"camera_frame_{run_id}_7.png"
    if save_png:
        save_frame_evidence(np.full((4, 5, 3), 100, dtype=np.uint8), run_id, 7, image)
    return run_id, quality, color, image


def run_check(tmp_path, run_id, quality, color):
    return main(["--run-id", run_id, "--frame", "7", "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)])


def test_matching_evidence_is_read_only(tmp_path, capsys):
    run_id, quality, color, image = make_evidence(tmp_path)
    before = [path.read_bytes() for path in (quality, color, image)]
    assert compare_frame_metrics(run_id, 7, tmp_path, quality, color) == {
        "brightness": ("100.0", "100.0"), "dark_ratio": ("0.0", "0.0"),
        "bright_ratio": ("0.0", "0.0"), "sharpness": ("0.0", "0.0"),
        "contrast": ("0.0", "0.0"),
    }
    assert run_check(tmp_path, run_id, quality, color) == 0
    assert "5 项指标均" in capsys.readouterr().out
    assert [path.read_bytes() for path in (quality, color, image)] == before


def test_changed_csv_value_is_reported_without_guessing_cause(tmp_path, capsys):
    run_id, quality, color, _ = make_evidence(tmp_path, brightness=99)
    assert run_check(tmp_path, run_id, quality, color) == 1
    output = capsys.readouterr().out
    assert "brightness: CSV=99.0 PNG重算=100.0 不同" in output
    assert "不能直接判定原因" in output


def test_missing_or_invalid_png_fails(tmp_path, capsys):
    run_id, quality, color, image = make_evidence(tmp_path, save_png=False)
    assert run_check(tmp_path, run_id, quality, color) == 2
    assert "检查失败" in capsys.readouterr().err
    image.write_bytes(b"not a png")
    assert run_check(tmp_path, run_id, quality, color) == 2
    assert "不是有效 PNG" in capsys.readouterr().err


def test_bad_frame_and_unpaired_csv_fail(tmp_path, capsys):
    run_id, quality, color, _ = make_evidence(tmp_path)
    with pytest.raises(ValueError, match="正整数"):
        compare_frame_metrics(run_id, 0, tmp_path, quality, color)
    append_quality_record(8, 100, 0, 0, 0, 0, quality, run_id=run_id)
    assert run_check(tmp_path, run_id, quality, color) == 2
    assert "未配对" in capsys.readouterr().err
