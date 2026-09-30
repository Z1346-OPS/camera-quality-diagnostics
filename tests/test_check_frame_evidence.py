"""原始帧留证核对测试：仅使用临时 CSV 与合成图片。"""

from uuid import uuid4

import cv2
import numpy as np

from src.check_frame_evidence import check_frame_evidence, main
from src.frame_evidence import save_frame_evidence
from src.report import append_color_record, append_quality_record


def make_reports(tmp_path, run_id, frame_counts=(1,)):
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    for frame_count in frame_counts:
        append_quality_record(frame_count, 100, 0, 0, 10, 10, quality, run_id=run_id)
        append_color_record(frame_count, 100, 100, 100, color,
                            scene_label="white_paper", run_id=run_id)
    return quality, color


def test_valid_and_missing_images_are_distinguished(tmp_path, capsys):
    run_id = uuid4().hex
    quality, color = make_reports(tmp_path, run_id, (1, 2))
    save_frame_evidence(np.zeros((4, 5, 3), dtype=np.uint8), run_id, 1,
                        tmp_path / f"camera_frame_{run_id}_1.png")
    result = check_frame_evidence(run_id, tmp_path, quality, color)
    assert result == {"valid": [1], "missing": [2], "empty": [], "undecodable": []}
    assert main(["--run-id", run_id, "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)]) == 1
    assert "缺失: 1 帧，帧号 [2]" in capsys.readouterr().out


def test_empty_and_broken_images_are_distinguished(tmp_path):
    run_id = uuid4().hex
    quality, color = make_reports(tmp_path, run_id, (1, 2))
    (tmp_path / f"camera_frame_{run_id}_1.png").write_bytes(b"")
    (tmp_path / f"camera_frame_{run_id}_2.png").write_bytes(b"not a png")
    assert check_frame_evidence(run_id, tmp_path, quality, color) == {
        "valid": [], "missing": [], "empty": [1], "undecodable": [2],
    }


def test_jpeg_renamed_png_is_not_accepted(tmp_path):
    run_id = uuid4().hex
    quality, color = make_reports(tmp_path, run_id)
    jpeg = cv2.imencode(".jpg", np.zeros((3, 4, 3), dtype=np.uint8))[1]
    (tmp_path / f"camera_frame_{run_id}_1.png").write_bytes(jpeg.tobytes())
    assert check_frame_evidence(run_id, tmp_path, quality, color)["undecodable"] == [1]


def test_all_images_pass_and_inputs_unchanged(tmp_path, capsys):
    run_id = uuid4().hex
    quality, color = make_reports(tmp_path, run_id)
    image = tmp_path / f"camera_frame_{run_id}_1.png"
    save_frame_evidence(np.full((3, 4, 3), 127, dtype=np.uint8), run_id, 1, image)
    before = [path.read_bytes() for path in (quality, color, image)]
    assert main(["--run-id", run_id, "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)]) == 0
    assert "可解码: 1 帧" in capsys.readouterr().out
    assert [path.read_bytes() for path in (quality, color, image)] == before


def test_unpaired_reports_and_unknown_run_fail(tmp_path, capsys):
    run_id = uuid4().hex
    quality, color = make_reports(tmp_path, run_id)
    assert main(["--run-id", uuid4().hex, "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)]) == 2
    assert "所选批次没有记录" in capsys.readouterr().err
    append_quality_record(2, 100, 0, 0, 10, 10, quality, run_id=run_id)
    assert main(["--run-id", run_id, "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)]) == 2
    assert "未配对" in capsys.readouterr().err
