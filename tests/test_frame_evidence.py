"""原始帧 PNG 留证不使用真实摄像头。"""

import cv2
import numpy as np
import pytest
from uuid import uuid4

from src.frame_evidence import save_frame_evidence


def test_png_round_trip_preserves_original_pixels(tmp_path):
    frame = np.zeros((8, 10, 3), dtype=np.uint8)
    frame[2, 3] = (12, 34, 56)
    path = tmp_path / "evidence.png"
    assert save_frame_evidence(frame, uuid4().hex, 7, path) == path
    assert np.array_equal(cv2.imread(str(path)), frame)


def test_existing_png_is_not_overwritten(tmp_path):
    path = tmp_path / "evidence.png"
    run_id = uuid4().hex
    first = np.full((4, 4, 3), 10, dtype=np.uint8)
    save_frame_evidence(first, run_id, 1, path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_frame_evidence(np.full_like(first, 20), run_id, 1, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("run_id, frame_count", [
    ("../outside", 1),
    (uuid4().hex, 0),
    (uuid4().hex, True),
])
def test_invalid_name_components_do_not_create_png(tmp_path, run_id, frame_count):
    path = tmp_path / "evidence.png"
    with pytest.raises(ValueError):
        save_frame_evidence(np.zeros((4, 4, 3), dtype=np.uint8), run_id, frame_count, path)
    assert not path.exists()


def test_encoder_failure_does_not_create_png(tmp_path, monkeypatch):
    path = tmp_path / "evidence.png"
    monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    with pytest.raises(ValueError, match="编码失败"):
        save_frame_evidence(np.zeros((4, 4, 3), dtype=np.uint8), uuid4().hex, 1, path)
    assert not path.exists()
