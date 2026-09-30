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

        def getBackendName(self):
            return "DSHOW"

    camera = FakeCamera()
    keys = iter(map(ord, "s1s2s3s0sq"))
    saved_labels = []
    saved_run_ids = []
    quality_frames = []
    quality_run_ids = []
    metadata_calls = []
    image_calls = []
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
    monkeypatch.setattr(camera_test, "save_session_metadata", lambda *args: metadata_calls.append(args))
    monkeypatch.setattr(camera_test, "save_frame_evidence", lambda *args: image_calls.append(args))
    assert camera_test.main() == 0
    assert saved_labels == [
        "unspecified", "white_paper", "colored_object", "white_restored", "unspecified"
    ]
    assert quality_frames == [1, 3, 5, 7, 9]
    assert quality_run_ids == saved_run_ids
    assert len(set(saved_run_ids)) == 1
    assert len(saved_run_ids[0]) == 32
    assert metadata_calls == [(saved_run_ids[0], 0, "DSHOW", 640, 480)]
    assert image_calls == []  # 默认关闭，绝不自动保存真实画面
    assert camera.released
    assert closed == [True]


def test_metadata_write_failure_is_reported_without_losing_csv_saves(monkeypatch, capsys):
    class FakeCamera:
        def read(self):
            return True, np.full((480, 640, 3), 100, dtype=np.uint8)

        def getBackendName(self):
            return "DSHOW"

        def release(self):
            pass

    keys = iter(map(ord, "ssq"))
    saved = []
    monkeypatch.setattr(camera_test, "open_camera", FakeCamera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(camera_test, "append_quality_record", lambda *args, **kwargs: saved.append("quality"))
    monkeypatch.setattr(camera_test, "append_color_record", lambda *args, **kwargs: saved.append("color"))

    def fail_metadata(*args):
        raise PermissionError("无法写入会话信息")

    monkeypatch.setattr(camera_test, "save_session_metadata", fail_metadata)
    assert camera_test.main() == 0
    assert saved == ["quality", "color", "quality", "color"]
    assert "会话信息保存失败（CSV 已保存）" in capsys.readouterr().out


def test_blank_backend_is_saved_as_unknown(monkeypatch):
    class FakeCamera:
        def read(self):
            return True, np.full((480, 640, 3), 100, dtype=np.uint8)

        def getBackendName(self):
            return ""

        def release(self):
            pass

    keys = iter(map(ord, "sq"))
    metadata_calls = []
    monkeypatch.setattr(camera_test, "open_camera", FakeCamera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(camera_test, "append_quality_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(camera_test, "append_color_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(camera_test, "save_session_metadata", lambda *args: metadata_calls.append(args))
    assert camera_test.main() == 0
    assert len(metadata_calls) == 1
    assert metadata_calls[0][2] is None


def test_opt_in_saves_unannotated_frame_from_same_save_key(monkeypatch):
    class FakeCamera:
        def read(self):
            return True, np.full((480, 640, 3), 100, dtype=np.uint8)

        def getBackendName(self):
            return "DSHOW"

        def release(self):
            pass

    keys = iter(map(ord, "sq"))
    shown, saved = [], []
    monkeypatch.setattr(camera_test, "open_camera", FakeCamera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda _name, frame: shown.append(frame.copy()))
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(camera_test, "append_quality_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(camera_test, "append_color_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(camera_test, "save_session_metadata", lambda *args: None)
    monkeypatch.setattr(camera_test, "save_frame_evidence",
                        lambda frame, run_id, count: saved.append((frame.copy(), run_id, count)))
    assert camera_test.main(save_frames=True) == 0
    assert len(saved) == 1
    assert saved[0][2] == 1
    assert np.all(saved[0][0] == 100)
    assert np.any(shown[0] != 100)  # 预览有文字，但留证帧没有


def test_opt_in_image_failure_reports_error_and_keeps_csv_saves(monkeypatch, capsys):
    class FakeCamera:
        def read(self):
            return True, np.full((480, 640, 3), 100, dtype=np.uint8)

        def getBackendName(self):
            return "DSHOW"

        def release(self):
            pass

    keys = iter(map(ord, "sq"))
    saved = []
    monkeypatch.setattr(camera_test, "open_camera", FakeCamera)
    monkeypatch.setattr(camera_test.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(camera_test.cv2, "waitKey", lambda delay: next(keys))
    monkeypatch.setattr(camera_test.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(camera_test.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(camera_test, "append_quality_record", lambda *args, **kwargs: saved.append("quality"))
    monkeypatch.setattr(camera_test, "append_color_record", lambda *args, **kwargs: saved.append("color"))
    monkeypatch.setattr(camera_test, "save_session_metadata", lambda *args: None)

    def fail_image(*args):
        raise PermissionError("无法写入 PNG")

    monkeypatch.setattr(camera_test, "save_frame_evidence", fail_image)
    assert camera_test.main(save_frames=True) == 0
    assert saved == ["quality", "color"]
    assert "原始帧保存失败（CSV 已保存）" in capsys.readouterr().out
