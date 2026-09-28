"""不占用真实摄像头的按键流程回归测试。"""

import numpy as np
from src import camera_test


def test_scene_keys_save_current_label_and_release_camera(monkeypatch):
    class FakeCamera:
        released = False

        def read(self):
            return True, np.full((480, 640, 3), 100, dtype=np.uint8)

        def release(self):
            self.released = True

    camera = FakeCamera()
    keys = iter(map(ord, "s1s2s3s0sq"))
    saved_labels = []
    saved_run_ids = []
    quality_frames = []
    quality_run_ids = []
    closed = []
    monkeypatch.setattr(camera_test, "open_camera", lambda: camera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: closed.append(True))
    def save_quality(frame, *args, run_id):
        quality_frames.append(frame)
        quality_run_ids.append(run_id)
    monkeypatch.setattr(camera_test, "append_quality_record", save_quality)
    def save_color(*args, scene_label, run_id):
        saved_labels.append(scene_label)
        saved_run_ids.append(run_id)
    monkeypatch.setattr(camera_test, "append_color_record", save_color)
    assert camera_test.main() == 0
    assert saved_labels == [
        "unspecified", "white_paper", "colored_object", "white_restored", "unspecified"
    ]
    assert quality_frames == [1, 3, 5, 7, 9]
    assert quality_run_ids == saved_run_ids
    assert len(set(saved_run_ids)) == 1
    assert len(saved_run_ids[0]) == 32
    assert camera.released
    assert closed == [True]
