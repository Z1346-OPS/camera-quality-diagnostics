"""批次复核仅使用合成 PNG 和临时 CSV。"""

from uuid import uuid4

import numpy as np

from src.frame_evidence import save_frame_evidence
from src.report import append_color_record, append_quality_record
from src.verify_run_metrics import main


def make_batch(tmp_path, records):
    run_id = uuid4().hex
    quality = tmp_path / "quality.csv"
    color = tmp_path / "color.csv"
    images = []
    for frame_count, csv_brightness, has_png in records:
        append_quality_record(frame_count, csv_brightness, 0, 0, 0, 0,
                              quality, run_id=run_id)
        append_color_record(frame_count, 100, 100, 100, color,
                            scene_label="white_paper", run_id=run_id)
        if has_png:
            image = tmp_path / f"camera_frame_{run_id}_{frame_count}.png"
            save_frame_evidence(np.full((4, 5, 3), 100, dtype=np.uint8),
                                run_id, frame_count, image)
            images.append(image)
    return run_id, quality, color, images


def check_batch(tmp_path, run_id, quality, color):
    return main(["--run-id", run_id, "--report-dir", str(tmp_path),
                 "--quality", str(quality), "--color", str(color)])


def test_batch_all_match_without_modifying_files(tmp_path, capsys):
    run_id, quality, color, images = make_batch(tmp_path, [(1, 100, True), (2, 100, True)])
    files = [quality, color, *images]
    before = [path.read_bytes() for path in files]
    assert check_batch(tmp_path, run_id, quality, color) == 0
    output = capsys.readouterr().out
    assert "共 2 帧；一致 2；数值不同 0；无法复核 0" in output
    assert [path.read_bytes() for path in files] == before


def test_batch_continues_after_mismatch_and_missing_png(tmp_path, capsys):
    run_id, quality, color, _ = make_batch(
        tmp_path, [(1, 100, True), (2, 99, True), (3, 100, False)]
    )
    assert check_batch(tmp_path, run_id, quality, color) == 1
    output = capsys.readouterr().out
    assert "帧 1: 5 项一致" in output
    assert "帧 2: 数值不同（brightness）" in output
    assert "帧 3: 无法复核" in output
    assert "共 3 帧；一致 1；数值不同 1；无法复核 1" in output


def test_unpaired_csv_and_unknown_run_are_input_errors(tmp_path, capsys):
    run_id, quality, color, _ = make_batch(tmp_path, [(1, 100, True)])
    assert check_batch(tmp_path, uuid4().hex, quality, color) == 2
    assert "所选批次没有记录" in capsys.readouterr().err
    append_quality_record(2, 100, 0, 0, 0, 0, quality, run_id=run_id)
    assert check_batch(tmp_path, run_id, quality, color) == 2
    assert "未配对" in capsys.readouterr().err
