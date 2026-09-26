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
    quality_frames = []
    closed = []
    monkeypatch.setattr(camera_test, "open_camera", lambda: camera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: closed.append(True))
    monkeypatch.setattr(camera_test, "append_quality_record",
                        lambda frame, *args: quality_frames.append(frame))
    monkeypatch.setattr(camera_test, "append_color_record",
                        lambda *args, scene_label: saved_labels.append(scene_label))
    assert camera_test.main() == 0
    assert saved_labels == [
        "unspecified", "white_paper", "colored_object", "white_restored", "unspecified"
    ]
    assert quality_frames == [1, 3, 5, 7, 9]
    assert camera.released
    assert closed == [True]
