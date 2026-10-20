"""定时采集与间隔留证（T01–T11）；全部使用模拟摄像头与可控时钟，不占用真实设备。"""

import csv
import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from src import capture_task
from src.capture_task import (
    PROJECT_ROOT,
    CaptureConfig,
    CaptureRunner,
    CaptureTaskError,
)
from src.check_reports import reconcile_reports
from src.review_capture import CaptureTaskReviewer
from src.verify_frame_metrics import compare_frame_metrics
from src import verify_run_metrics


# ---------------------------------------------------------------- 测试夹具

class FakeClock:
    """独立推进的单调时钟；预期值不通过被测调度函数计算。"""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class ScriptedCamera:
    """按脚本推进时钟并返回帧或故障。

    events 元素为 (elapsed_seconds, payload)：
    - ndarray  -> (True, frame)
    - None     -> (False, None)
    - 异常对象 -> 抛出该异常
    - 元组     -> 原样返回
    """

    def __init__(self, clock: FakeClock, events) -> None:
        self.clock = clock
        self.events = list(events)
        self.index = 0
        self.read_calls = 0
        self.released = 0
        self.opened = True

    def isOpened(self) -> bool:
        return self.opened

    def getBackendName(self) -> str:
        return "DSHOW"

    def release(self) -> None:
        self.released += 1

    def read(self):
        self.read_calls += 1
        if self.index >= len(self.events):
            raise AssertionError("脚本帧已耗尽：调度读取了预期之外的帧")
        elapsed, payload = self.events[self.index]
        self.index += 1
        self.clock.now = elapsed
        if isinstance(payload, BaseException):
            raise payload
        if payload is None:
            return False, None
        if isinstance(payload, tuple):
            return payload
        return True, payload


def make_frame(seed: int, shape=(6, 8, 3)) -> np.ndarray:
    """每个 seed 给出不同的已知像素。"""
    height, width, channels = shape
    base = np.arange(height * width * channels).reshape(shape)
    return ((base + seed) % 256).astype(np.uint8)


class Harness:
    """把配置、模拟设备、可控时钟和输出目录绑在一起。"""

    def __init__(
        self, tmp_path, events, *, duration, interval,
        camera_index=0, clock=None, camera=None, output_name="task",
    ) -> None:
        self.clock = clock or FakeClock()
        self.camera = camera if camera is not None else ScriptedCamera(self.clock, events)
        self.requested_indices = []
        self.output_dir = Path(tmp_path) / output_name
        self.config = CaptureConfig(
            self.output_dir,
            camera_index=camera_index,
            duration_seconds=duration,
            interval_seconds=interval,
        )
        self.runner = CaptureRunner(
            self.config, camera_factory=self._factory, clock=self.clock
        )

    def _factory(self, index):
        self.requested_indices.append(index)
        return self.camera

    def run(self):
        return self.runner.run()


def read_report(output_dir: Path) -> dict:
    return json.loads((Path(output_dir) / "capture_task.json").read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _hash_or_none(path: Path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


PUBLIC_REPORTS = (
    PROJECT_ROOT / "data" / "reports" / "camera_quality_runs.csv",
    PROJECT_ROOT / "data" / "reports" / "camera_colors_runs.csv",
    PROJECT_ROOT / "data" / "reports" / "camera_quality.csv",
    PROJECT_ROOT / "data" / "reports" / "camera_colors.csv",
)


# ---------------------------------------------------------------- T01 参数

def test_config_defaults(tmp_path):
    config = CaptureConfig(tmp_path / "out")
    assert (config.camera_index, config.duration_seconds, config.interval_seconds) == (0, 30, 5)
    assert config.planned_sample_slots == 6


def test_config_accepts_upper_bounds(tmp_path):
    config = CaptureConfig(
        tmp_path / "out", camera_index=2**31 - 1,
        duration_seconds=3600, interval_seconds=3600,
    )
    assert config.planned_sample_slots == 1


@pytest.mark.parametrize("kwargs", [
    {"camera_index": -1},
    {"camera_index": 2**31},
    {"camera_index": True},
    {"camera_index": 1.0},
    {"duration_seconds": 0},
    {"duration_seconds": -5},
    {"duration_seconds": 3601},
    {"duration_seconds": True},
    {"duration_seconds": 1.0},
    {"duration_seconds": "5"},
    {"interval_seconds": 0},
    {"interval_seconds": -1},
    {"interval_seconds": 3601},
    {"interval_seconds": False},
])
def test_config_rejects_invalid_values(tmp_path, kwargs):
    with pytest.raises(CaptureTaskError):
        CaptureConfig(tmp_path / "out", **kwargs)
    assert not (tmp_path / "out").exists()


def test_config_requires_output_dir():
    with pytest.raises(TypeError):
        CaptureConfig()


def test_planned_slots_boundary_120(tmp_path):
    assert CaptureConfig(tmp_path / "ok", duration_seconds=120, interval_seconds=1).planned_sample_slots == 120
    assert CaptureConfig(tmp_path / "ok2", duration_seconds=3600, interval_seconds=30).planned_sample_slots == 120
    with pytest.raises(CaptureTaskError, match="120"):
        CaptureConfig(tmp_path / "bad", duration_seconds=121, interval_seconds=1)


def test_interval_greater_than_duration_allows_single_slot(tmp_path):
    config = CaptureConfig(tmp_path / "out", duration_seconds=3, interval_seconds=5)
    assert config.planned_sample_slots == 1


# ---------------------------------------------------------------- T02 启动保护

def test_config_rejects_existing_directory(tmp_path):
    existing = tmp_path / "out"
    existing.mkdir()
    with pytest.raises(CaptureTaskError, match="已存在"):
        CaptureConfig(existing)


def test_config_rejects_existing_file_and_keeps_content(tmp_path):
    existing = tmp_path / "out"
    existing.write_bytes(b"keep me")
    before = existing.read_bytes()
    with pytest.raises(CaptureTaskError, match="已存在"):
        CaptureConfig(existing)
    assert existing.read_bytes() == before


def test_existing_output_directory_content_unchanged(tmp_path):
    existing = tmp_path / "out"
    existing.mkdir()
    (existing / "keep.txt").write_bytes(b"keep")
    digest = _hash_or_none(existing / "keep.txt")
    with pytest.raises(CaptureTaskError):
        CaptureConfig(existing)
    assert _hash_or_none(existing / "keep.txt") == digest


@pytest.mark.parametrize("relative", [
    "src/phase-4.4-output",
    "tests/phase-4.4-output",
    "tools/phase-4.4-output",
    "photo/phase-4.4-output",
    "docs/phase-4.4-output",
    "data/samples/phase-4.4-output",
    "data/experiments/phase-4.4-output",
    "data/manifests/phase-4.4-output",
])
def test_config_rejects_protected_output_paths(relative):
    with pytest.raises(CaptureTaskError, match="受保护"):
        CaptureConfig(PROJECT_ROOT / relative)


def test_rejected_config_never_reaches_camera_factory(tmp_path):
    """非法配置在构造阶段就被拒绝，因此不存在打开摄像头的机会。"""
    opened = []

    def factory(index):
        opened.append(index)
        return ScriptedCamera(FakeClock(), [])

    with pytest.raises(CaptureTaskError):
        config = CaptureConfig(PROJECT_ROOT / "src" / "phase-4.4-output")
        CaptureRunner(config, camera_factory=factory)
    assert opened == []


# ---------------------------------------------------------------- T03 调度

def test_schedule_example_a(tmp_path):
    """duration=6，interval=2；有效帧在 0.2、1.0、2.1、4.1、6.1 秒返回。"""
    harness = Harness(
        tmp_path,
        [(0.2, make_frame(1)), (1.0, make_frame(2)), (2.1, make_frame(3)),
         (4.1, make_frame(4)), (6.1, make_frame(5))],
        duration=6, interval=2,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 0), (3, 1), (4, 2)]
    counts = report["counts"]
    assert counts["read_attempts"] == 5
    assert counts["valid_frames"] == 5
    assert counts["sample_attempts"] == 3
    assert counts["samples_completed"] == 3
    assert report["status"] == "completed"
    assert report["stop_reason"] == "duration_reached"


def test_schedule_example_b(tmp_path):
    """duration=6，interval=2；有效帧在 0.2、5.1、6.1 秒返回；不补区间 1。"""
    harness = Harness(
        tmp_path,
        [(0.2, make_frame(1)), (5.1, make_frame(2)), (6.1, make_frame(3))],
        duration=6, interval=2,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 0), (2, 2)]
    counts = report["counts"]
    assert counts["read_attempts"] == 3
    assert counts["valid_frames"] == 3
    assert counts["sample_attempts"] == 2
    assert counts["samples_completed"] == 2


def test_schedule_example_c(tmp_path):
    """duration=3，interval=5；有效帧在 0.2、1.0、3.1 秒返回；只保存第 1 帧。"""
    harness = Harness(
        tmp_path,
        [(0.2, make_frame(1)), (1.0, make_frame(2)), (3.1, make_frame(3))],
        duration=3, interval=5,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 0)]
    counts = report["counts"]
    assert counts["read_attempts"] == 3
    assert counts["valid_frames"] == 3
    assert counts["sample_attempts"] == 1
    assert counts["samples_completed"] == 1


def test_schedule_example_d(tmp_path):
    """duration=3，首个有效帧在 3.1 秒返回；no_samples 失败。"""
    harness = Harness(tmp_path, [(3.1, make_frame(1))], duration=3, interval=5)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "no_samples"
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "no_samples"
    assert report["counts"]["valid_frames"] == 1
    assert report["counts"]["sample_attempts"] == 0
    assert report["samples"] == []


def test_first_frame_in_later_slot_does_not_backfill(tmp_path):
    """首次有效帧已经进入后续区间：只采该区间，不补 0、1。"""
    harness = Harness(
        tmp_path, [(4.5, make_frame(1)), (6.5, make_frame(2))],
        duration=6, interval=2,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 2)]
    assert report["counts"]["sample_attempts"] == 1


def test_frame_exactly_on_interval_boundary(tmp_path):
    """恰好位于区间边界：floor(2.0 / 2) = 1。"""
    harness = Harness(
        tmp_path, [(2.0, make_frame(1)), (6.0, make_frame(2))],
        duration=6, interval=2,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 1)]
    assert report["counts"]["sample_attempts"] == 1


def test_frame_exactly_at_deadline_is_counted_but_not_saved(tmp_path):
    """恰好位于截止边界：计入有效帧，但不保存。"""
    harness = Harness(tmp_path, [(3.0, make_frame(1))], duration=3, interval=1)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "no_samples"
    report = read_report(harness.output_dir)
    assert report["counts"]["valid_frames"] == 1
    assert report["counts"]["sample_attempts"] == 0
    assert report["samples"] == []


def test_duplicate_frames_in_same_slot_produce_one_sample(tmp_path):
    harness = Harness(
        tmp_path,
        [(0.1, make_frame(1)), (0.5, make_frame(2)), (1.5, make_frame(3)), (2.5, make_frame(4))],
        duration=2, interval=1,
    )
    report = harness.run()
    assert [(s["frame_count"], s["slot_index"]) for s in report["samples"]] == [(1, 0), (3, 1)]
    assert report["counts"]["sample_attempts"] == 2


def test_sample_completes_when_saving_crosses_deadline(tmp_path, monkeypatch):
    """样本在截止前取得，保存跨过截止时间时允许完成该样本，之后停止采集。"""
    clock = FakeClock()
    harness = Harness(
        tmp_path, [(0.2, make_frame(1)), (2.5, make_frame(2))],
        duration=3, interval=2, clock=clock,
    )
    real_quality = capture_task.append_quality_record

    def slow_quality(*args, **kwargs):
        clock.now = 5.0  # 保存耗时跨过截止时间
        return real_quality(*args, **kwargs)

    monkeypatch.setattr(capture_task, "append_quality_record", slow_quality)
    report = harness.run()
    assert report["status"] == "completed"
    assert report["counts"]["read_attempts"] == 1
    assert report["counts"]["samples_completed"] == 1
    assert [s["slot_index"] for s in report["samples"]] == [0]


def test_capture_elapsed_is_measured_not_requested(tmp_path):
    """记录实际时长，不把请求时长冒充实测时长。"""
    harness = Harness(
        tmp_path, [(0.2, make_frame(1)), (1.9, make_frame(2)), (2.4, make_frame(3))],
        duration=2, interval=1,
    )
    report = harness.run()
    assert report["timings"]["capture_elapsed_seconds"] == 2.4
    assert report["timings"]["started_at_utc"] is not None
    assert report["timings"]["ended_at_utc"] is not None


# ---------------------------------------------------------------- T04 数据

def test_saved_png_matches_selected_frame_and_input_unchanged(tmp_path):
    first, second, third = make_frame(1), make_frame(2), make_frame(3)
    keep = {1: first.copy(), 2: second.copy(), 3: third.copy()}
    assert not np.array_equal(first, second)
    harness = Harness(
        tmp_path, [(0.5, first), (2.5, second), (4.5, third)],
        duration=4, interval=2,
    )
    report = harness.run()
    assert np.array_equal(first, keep[1])
    assert np.array_equal(second, keep[2])
    assert np.array_equal(third, keep[3])
    assert [s["frame_count"] for s in report["samples"]] == [1, 2]
    for sample in report["samples"]:
        path = harness.output_dir / sample["image_file"]
        saved = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        assert np.array_equal(saved, keep[sample["frame_count"]])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sample["image_sha256"]


def test_no_preview_or_key_functions_are_called(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("定时采集不得调用预览、叠字或按键接口")

    for name in ("imshow", "putText", "waitKey", "namedWindow", "getWindowProperty", "destroyAllWindows"):
        monkeypatch.setattr(cv2, name, forbidden)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))],
        duration=2, interval=2,
    )
    assert harness.run()["status"] == "completed"


# ---------------------------------------------------------------- T05 指标

def test_uniform_frame_gives_known_mean_and_zero_variance(tmp_path):
    uniform = np.full((10, 12, 3), 100, dtype=np.uint8)
    harness = Harness(
        tmp_path, [(0.5, uniform), (2.5, uniform)], duration=2, interval=2,
    )
    report = harness.run()
    sample = report["samples"][0]
    quality = read_csv_rows(harness.output_dir / "camera_quality_runs.csv")[0]
    assert quality["frame_count"] == str(sample["frame_count"])
    assert quality["brightness"] == "100.0"
    assert quality["dark_ratio"] == "0.0"
    assert quality["bright_ratio"] == "0.0"
    assert quality["sharpness"] == "0.0"
    assert quality["contrast"] == "0.0"
    color = read_csv_rows(harness.output_dir / "camera_colors_runs.csv")[0]
    assert (color["blue_mean"], color["green_mean"], color["red_mean"]) == ("100.0", "100.0", "100.0")
    assert color["channel_spread"] == "0.0"
    assert color["scene_label"] == "unspecified"


def test_successful_task_passes_existing_five_metric_verification(tmp_path):
    harness = Harness(
        tmp_path,
        [(0.5, make_frame(1)), (1.5, make_frame(2)), (2.5, make_frame(3)), (3.5, make_frame(4))],
        duration=3, interval=1,
    )
    report = harness.run()
    quality = harness.output_dir / "camera_quality_runs.csv"
    color = harness.output_dir / "camera_colors_runs.csv"
    matched, quality_only, color_only = reconcile_reports(quality, color, report["run_id"])
    assert quality_only == set() and color_only == set()
    assert len(matched) == len(report["samples"]) == 3
    for sample in report["samples"]:
        compared = compare_frame_metrics(
            report["run_id"], sample["frame_count"], harness.output_dir, quality, color
        )
        assert all(saved == recalculated for saved, recalculated in compared.values())


def test_metrics_match_metric_module_on_saved_png(tmp_path):
    """以既有独立指标函数为算法基准，逐样本核对。"""
    harness = Harness(
        tmp_path, [(0.5, make_frame(11)), (2.5, make_frame(12))], duration=2, interval=2,
    )
    report = harness.run()
    quality = {row["frame_count"]: row for row in read_csv_rows(harness.output_dir / "camera_quality_runs.csv")}
    for sample in report["samples"]:
        saved = cv2.imread(str(harness.output_dir / sample["image_file"]), cv2.IMREAD_UNCHANGED)
        gray = cv2.cvtColor(saved, cv2.COLOR_BGR2GRAY)
        row = quality[str(sample["frame_count"])]
        assert row["brightness"] == f"{capture_task.calculate_mean_brightness(gray):.1f}"
        assert row["contrast"] == f"{capture_task.calculate_contrast(gray):.1f}"
        assert row["sharpness"] == f"{capture_task.calculate_sharpness(gray):.1f}"
        dark, bright = capture_task.calculate_exposure_ratios(
            gray, capture_task.DARK_THRESHOLD, capture_task.BRIGHT_THRESHOLD
        )
        assert row["dark_ratio"] == f"{dark:.1f}"
        assert row["bright_ratio"] == f"{bright:.1f}"


# ---------------------------------------------------------------- T06 读取故障

def test_open_failure_writes_report_without_timings(tmp_path):
    camera = ScriptedCamera(FakeClock(), [])
    camera.opened = False
    harness = Harness(tmp_path, [], duration=5, interval=1, camera=camera)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "open_failed"
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "open_failed"
    assert report["timings"] == {
        "started_at_utc": None, "ended_at_utc": None, "capture_elapsed_seconds": None,
    }
    assert report["camera"]["first_frame_size"] is None
    assert report["counts"]["read_attempts"] == 0
    assert camera.released == 1


def test_camera_factory_returning_none_is_open_failure(tmp_path):
    harness = Harness(tmp_path, [], duration=5, interval=1)
    harness.runner._camera_factory = lambda index: None
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "open_failed"
    assert read_report(harness.output_dir)["stop_reason"] == "open_failed"


@pytest.mark.parametrize("payload, reason", [
    (None, "read_failed"),
    (np.zeros((0, 5, 3), dtype=np.uint8), "invalid_frame"),
    (np.zeros((0, 0, 3), dtype=np.uint8), "invalid_frame"),
    (np.zeros((4, 5), dtype=np.uint8), "invalid_frame"),
    (np.zeros((4, 5, 4), dtype=np.uint8), "invalid_frame"),
    (np.zeros((4, 5, 3), dtype=np.float32), "invalid_frame"),
    (np.zeros((4, 5, 3), dtype=np.uint16), "invalid_frame"),
])
def test_first_read_failure(tmp_path, payload, reason):
    harness = Harness(tmp_path, [(0.5, payload)], duration=5, interval=1)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == reason
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == reason
    assert report["counts"]["read_attempts"] == 1
    assert report["counts"]["valid_frames"] == 0
    assert report["counts"]["sample_attempts"] == 0


def test_mid_capture_read_failure_keeps_saved_sample(tmp_path):
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (1.5, None)], duration=5, interval=1,
    )
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "read_failed"
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["counts"]["read_attempts"] == 2
    assert report["counts"]["valid_frames"] == 1
    assert report["counts"]["sample_attempts"] == 1
    assert report["counts"]["samples_completed"] == 1
    assert (harness.output_dir / report["samples"][0]["image_file"]).exists()


def test_read_failure_returned_after_deadline_is_not_masked(tmp_path):
    """读取失败优先作为错误，不能因为已经超时而伪装成正常到时结束。"""
    harness = Harness(
        tmp_path, [(4.9, make_frame(1)), (5.5, None)], duration=5, interval=1,
    )
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "read_failed"
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "read_failed"
    assert report["counts"]["valid_frames"] == 1
    assert report["counts"]["samples_completed"] == 1


# ---------------------------------------------------------------- T07 保存故障

def test_quality_save_failure_stops_later_steps(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("质量 CSV 写入失败")

    monkeypatch.setattr(capture_task, "append_quality_record", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "save_failed"
    sample = report["samples"][0]
    assert (sample["quality_status"], sample["color_status"], sample["image_status"]) == (
        "failed", "not_attempted", "not_attempted",
    )
    assert sample["image_sha256"] is None
    assert report["counts"]["sample_attempts"] == 1
    assert report["counts"]["samples_completed"] == 0
    assert not (harness.output_dir / "camera_colors_runs.csv").exists()
    assert not (harness.output_dir / sample["image_file"]).exists()


def test_color_save_failure_keeps_quality_csv(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("颜色 CSV 写入失败")

    monkeypatch.setattr(capture_task, "append_color_record", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()
    report = read_report(harness.output_dir)
    sample = report["samples"][0]
    assert (sample["quality_status"], sample["color_status"], sample["image_status"]) == (
        "written", "failed", "not_attempted",
    )
    assert (harness.output_dir / "camera_quality_runs.csv").exists()
    assert not (harness.output_dir / "camera_colors_runs.csv").exists()
    assert not (harness.output_dir / sample["image_file"]).exists()
    assert report["counts"]["samples_completed"] == 0


def test_png_encode_failure_keeps_csvs(tmp_path, monkeypatch):
    monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(ValueError):
        harness.run()
    report = read_report(harness.output_dir)
    sample = report["samples"][0]
    assert (sample["quality_status"], sample["color_status"], sample["image_status"]) == (
        "written", "written", "failed",
    )
    assert (harness.output_dir / "camera_quality_runs.csv").exists()
    assert (harness.output_dir / "camera_colors_runs.csv").exists()
    assert report["counts"]["samples_completed"] == 0


def test_png_write_failure_marks_image_failed(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("PNG 写入失败")

    monkeypatch.setattr(capture_task, "save_frame_evidence", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()
    report = read_report(harness.output_dir)
    sample = report["samples"][0]
    assert (sample["quality_status"], sample["color_status"], sample["image_status"]) == (
        "written", "written", "failed",
    )
    assert report["counts"]["samples_completed"] == 0


def test_png_digest_failure_is_not_counted_complete(tmp_path, monkeypatch):
    def boom(path):
        raise OSError("摘要读取失败")

    monkeypatch.setattr(capture_task, "_sha256_file", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()
    report = read_report(harness.output_dir)
    sample = report["samples"][0]
    assert sample["image_status"] == "written"
    assert sample["image_sha256"] is None
    assert report["stop_reason"] == "save_failed"
    assert report["counts"]["samples_completed"] == 0


# ---------------------------------------------------------------- T08 部分失败与旧复核

def test_partial_failure_and_legacy_tools_reject_incomplete_batch(tmp_path, monkeypatch):
    real_color = capture_task.append_color_record
    calls = {"count": 0}

    def flaky_color(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] >= 2:
            raise OSError("第二帧颜色 CSV 写入失败")
        return real_color(*args, **kwargs)

    monkeypatch.setattr(capture_task, "append_color_record", flaky_color)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=3, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()

    output_dir = harness.output_dir
    quality = output_dir / "camera_quality_runs.csv"
    color = output_dir / "camera_colors_runs.csv"
    run_id = harness.runner.run_id
    quality_before = quality.read_bytes()

    matched, quality_only, color_only = reconcile_reports(quality, color)
    assert matched == {(run_id, 1)}
    assert quality_only == {(run_id, 2)}
    assert color_only == set()

    # 既有复核工具拒绝不完整批次（未修改、未放宽）
    exit_code = verify_run_metrics.main([
        "--run-id", run_id, "--report-dir", str(output_dir),
        "--quality", str(quality), "--color", str(color),
    ])
    assert exit_code == 2

    # 在临时副本中提取完整配对记录后复核，不改变实际任务产物
    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    _copy_filtered_csv(quality, copy_dir / "camera_quality_runs.csv", lambda row: row[1] == "1")
    _copy_filtered_csv(color, copy_dir / "camera_colors_runs.csv", lambda row: row[1] == "1")
    compared = compare_frame_metrics(
        run_id, 1, output_dir,
        copy_dir / "camera_quality_runs.csv", copy_dir / "camera_colors_runs.csv",
    )
    assert all(saved == recalculated for saved, recalculated in compared.values())
    assert quality.read_bytes() == quality_before


def _copy_filtered_csv(source: Path, target: Path, keep) -> None:
    with Path(source).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    with Path(target).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(rows[0])
        for row in rows[1:]:
            if keep(row):
                writer.writerow(row)


# ---------------------------------------------------------------- T09 中断与异常

def test_keyboard_interrupt_mid_capture(tmp_path):
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (1.5, KeyboardInterrupt())],
        duration=5, interval=1,
    )
    with pytest.raises(KeyboardInterrupt):
        harness.run()
    report = read_report(harness.output_dir)
    assert report["status"] == "interrupted"
    assert report["stop_reason"] == "interrupted"
    assert report["primary_error"]["type"] == "KeyboardInterrupt"
    assert report["counts"]["read_attempts"] == 2
    assert report["counts"]["samples_completed"] == 1
    assert harness.camera.released == 1


def test_keyboard_interrupt_during_save_is_interrupted(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(capture_task, "append_quality_record", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(KeyboardInterrupt):
        harness.run()
    report = read_report(harness.output_dir)
    assert report["status"] == "interrupted"
    assert report["stop_reason"] == "interrupted"
    assert report["primary_error"]["type"] == "KeyboardInterrupt"
    assert harness.camera.released == 1


def test_unexpected_exception_propagates_unchanged(tmp_path, monkeypatch):
    def boom(frame):
        raise MemoryError("模拟内存不足")

    monkeypatch.setattr(capture_task, "_measure_frame", boom)
    harness = Harness(tmp_path, [(0.5, make_frame(1))], duration=2, interval=1)
    with pytest.raises(MemoryError):
        harness.run()
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "measurement_failed"
    assert report["primary_error"] == {
        "stage": "measurement", "type": "MemoryError", "message": "模拟内存不足",
    }
    assert report["counts"]["sample_attempts"] == 1
    assert report["counts"]["samples_completed"] == 0
    assert harness.camera.released == 1


def test_cv2_error_from_camera_is_preserved(tmp_path):
    harness = Harness(tmp_path, [(0.5, cv2.error("设备异常"))], duration=2, interval=1)
    with pytest.raises(cv2.error):
        harness.run()
    report = read_report(harness.output_dir)
    assert report["primary_error"]["type"] == "error"
    assert report["stop_reason"] == "read_failed"
    # 抛异常的 read 也要计入尝试次数（曾出现只统计「返回成功」的缺陷）
    assert report["counts"]["read_attempts"] == 1
    assert report["counts"]["valid_frames"] == 0
    assert harness.camera.released == 1


def test_sampling_stops_after_exception(tmp_path):
    harness = Harness(
        tmp_path,
        [(0.5, make_frame(1)), (1.5, None), (2.5, make_frame(3))],
        duration=5, interval=1,
    )
    with pytest.raises(CaptureTaskError):
        harness.run()
    assert harness.camera.read_calls == 2  # 第二帧失败后不再读取第三帧


# ---------------------------------------------------------------- T10 清理与报告

class BadReleaseCamera(ScriptedCamera):
    def __init__(self, clock, events, release_error):
        super().__init__(clock, events)
        self.release_error = release_error

    def release(self):
        self.released += 1
        raise self.release_error


def _raising(error):
    def _boom(*args, **kwargs):
        raise error
    return _boom


def _run_and_capture(harness):
    observed = None
    try:
        harness.run()
    except BaseException as error:  # noqa: BLE001 - 测试要拿到原始异常对象
        observed = error
    return observed


@pytest.mark.parametrize("release_error", [
    MemoryError("释放时内存不足"),
    OSError("释放失败"),
    cv2.error("释放时设备异常"),
])
def test_release_failure_alone_preserves_original_exception(tmp_path, release_error):
    """仅释放失败时重新抛出原始释放异常，不转换成 CaptureTaskError。"""
    clock = FakeClock()
    camera = BadReleaseCamera(clock, [(0.5, make_frame(1)), (2.5, make_frame(2))], release_error)
    harness = Harness(tmp_path, [], duration=2, interval=1, clock=clock, camera=camera)
    observed = _run_and_capture(harness)
    assert observed is release_error
    assert type(observed) is type(release_error)
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "release_failed"
    assert report["primary_error"] is None
    assert len(report["cleanup_errors"]) == 1
    assert report["cleanup_errors"][0]["type"] == type(release_error).__name__
    assert report["counts"]["samples_completed"] == 1
    assert camera.released == 1


def test_release_keyboard_interrupt_is_not_a_logical_failure(tmp_path):
    """释放时的 KeyboardInterrupt 仍按中断处理，不变成普通逻辑失败。"""
    clock = FakeClock()
    error = KeyboardInterrupt("释放时中断")
    camera = BadReleaseCamera(clock, [(0.5, make_frame(1)), (2.5, make_frame(2))], error)
    harness = Harness(tmp_path, [], duration=2, interval=1, clock=clock, camera=camera)
    observed = _run_and_capture(harness)
    assert observed is error
    report = read_report(harness.output_dir)
    assert report["status"] == "interrupted"
    assert report["stop_reason"] == "interrupted"
    assert report["counts"]["samples_completed"] == 1
    assert camera.released == 1


def test_release_failure_does_not_replace_original_error(tmp_path):
    clock = FakeClock()
    release_error = OSError("释放失败")
    camera = BadReleaseCamera(clock, [(0.5, None)], release_error)
    harness = Harness(tmp_path, [], duration=5, interval=1, clock=clock, camera=camera)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "read_failed"
    report = read_report(harness.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "read_failed"
    assert report["primary_error"]["type"] == "CaptureTaskError"
    assert len(report["cleanup_errors"]) == 1
    # 释放错误作为附加错误可见，但不替换原异常
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("释放设备失败" in note and "阶段=release" in note for note in notes)
    assert camera.released == 1


def test_publication_interrupt_does_not_replace_earlier_error(tmp_path, monkeypatch):
    """发布阶段的中断不得替换先前的执行错误。"""
    clock = FakeClock()
    primary = OSError("原始读取错误")
    camera = ScriptedCamera(clock, [(0.5, primary)])
    harness = Harness(tmp_path, [], duration=5, interval=1, clock=clock, camera=camera)
    published = {}

    def capture_then_raise(report, target):
        published.update(report)
        raise KeyboardInterrupt("发布中断")

    monkeypatch.setattr(capture_task, "_publish_report", capture_then_raise)
    observed = _run_and_capture(harness)
    assert observed is primary
    # 报告未发布，但被交给发布函数的内容仍反映原始执行错误
    assert published["status"] == "failed"
    assert published["stop_reason"] == "read_failed"
    assert not (harness.output_dir / "capture_task.json").exists()
    notes = getattr(observed, "__notes__", [])
    assert any("阶段=report" in note and "KeyboardInterrupt" in note for note in notes)
    assert camera.released == 1


@pytest.mark.parametrize("publish_error", [
    OSError("发布失败"),
    KeyboardInterrupt("发布中断"),
])
def test_publication_error_alone_propagates(tmp_path, monkeypatch, publish_error):
    """没有先前执行错误时，发布错误正常传播，不被吞掉。"""
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, make_frame(1)), (2.5, make_frame(2))])
    harness = Harness(tmp_path, [], duration=2, interval=1, clock=clock, camera=camera)
    monkeypatch.setattr(capture_task, "_publish_report", _raising(publish_error))
    observed = _run_and_capture(harness)
    assert observed is publish_error
    assert camera.released == 1


def test_publish_refuses_existing_target(tmp_path):
    target = tmp_path / "capture_task.json"
    target.write_bytes(b"existing")
    with pytest.raises(CaptureTaskError):
        capture_task._publish_report({"schema_version": 1}, target)
    assert target.read_bytes() == b"existing"


def test_publish_refuses_target_created_after_initial_check(tmp_path, monkeypatch):
    target = tmp_path / "capture_task.json"
    real_dumps = capture_task.json.dumps

    def concurrent_writer(*args, **kwargs):
        payload = real_dumps(*args, **kwargs)
        target.write_bytes(b"concurrent report")
        return payload

    monkeypatch.setattr(capture_task.json, "dumps", concurrent_writer)
    with pytest.raises(CaptureTaskError, match="拒绝覆盖") as caught:
        capture_task._publish_report({"schema_version": 1}, target)
    assert caught.value.stage == "report"
    assert target.read_bytes() == b"concurrent report"
    # 完整临时文件留作错误证据，不删除竞争者创建的报告。
    assert json.loads((tmp_path / capture_task.REPORT_TEMP_NAME).read_text(encoding="utf-8")) == {
        "schema_version": 1,
    }


def test_publish_complete_report_removes_temp_file(tmp_path):
    target = tmp_path / "capture_task.json"
    payload = {"schema_version": 1, "message": "完整报告"}
    assert capture_task._publish_report(payload, target) == target
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert not (tmp_path / capture_task.REPORT_TEMP_NAME).exists()


def test_publish_link_error_preserves_temp_without_fallback(tmp_path, monkeypatch):
    target = tmp_path / "capture_task.json"
    error = OSError("文件系统不支持硬链接")
    monkeypatch.setattr(capture_task.os, "link", _raising(error))
    with pytest.raises(OSError) as caught:
        capture_task._publish_report({"schema_version": 1}, target)
    assert caught.value is error
    assert not target.exists()
    assert (tmp_path / capture_task.REPORT_TEMP_NAME).is_file()


def test_publish_unlink_error_exposes_published_report(tmp_path, monkeypatch):
    target = tmp_path / "capture_task.json"
    error = OSError("临时链接删除失败")
    monkeypatch.setattr(capture_task.Path, "unlink", _raising(error))
    with pytest.raises(OSError) as caught:
        capture_task._publish_report({"schema_version": 1}, target)
    assert caught.value is error
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema_version": 1}
    assert (tmp_path / capture_task.REPORT_TEMP_NAME).is_file()
    assert any("已发布" in note for note in getattr(caught.value, "__notes__", []))


def test_publish_link_error_keeps_capture_error_primary(tmp_path, monkeypatch):
    error = OSError("文件系统拒绝发布")
    monkeypatch.setattr(capture_task.os, "link", _raising(error))
    harness = Harness(tmp_path, [(0.5, None)], duration=5, interval=1)
    with pytest.raises(CaptureTaskError) as caught:
        harness.run()
    assert caught.value.stop_reason == "read_failed"
    assert any("报告发布失败" in note and "文件系统拒绝发布" in note
               for note in getattr(caught.value, "__notes__", []))
    assert harness.camera.released == 1
    assert not (harness.output_dir / "capture_task.json").exists()


def test_temp_write_failure_leaves_no_partial_report(tmp_path):
    target = tmp_path / "capture_task.json"
    (tmp_path / capture_task.REPORT_TEMP_NAME).mkdir()  # 占用临时文件名
    with pytest.raises(OSError):
        capture_task._publish_report({"schema_version": 1}, target)
    assert not target.exists()
    assert (tmp_path / capture_task.REPORT_TEMP_NAME).exists()  # 残留临时产物


def test_publish_failure_does_not_override_execution_error(tmp_path, monkeypatch):
    def boom(report, target):
        raise OSError("报告发布失败")

    monkeypatch.setattr(capture_task, "_publish_report", boom)
    harness = Harness(tmp_path, [(0.5, None)], duration=5, interval=1)
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.run()
    assert excinfo.value.stop_reason == "read_failed"
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("报告发布" in note for note in notes)
    assert not (harness.output_dir / "capture_task.json").exists()


def test_publish_failure_on_successful_capture_raises(tmp_path, monkeypatch):
    def boom(report, target):
        raise OSError("报告发布失败")

    monkeypatch.setattr(capture_task, "_publish_report", boom)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    with pytest.raises(OSError):
        harness.run()


def test_json_serialization_rejects_non_finite(tmp_path):
    target = tmp_path / "capture_task.json"
    with pytest.raises(ValueError):
        capture_task._publish_report({"bad": float("nan")}, target)
    assert not target.exists()


# ---------------------------------------------------------------- T11 格式与计数

SAMPLE_FIELDS = {
    "frame_count", "slot_index", "scheduled_elapsed_seconds", "read_elapsed_seconds",
    "width", "height", "quality_status", "color_status", "image_status",
    "image_file", "image_sha256",
}
TOP_FIELDS = {
    "schema_version", "report_type", "run_id", "status", "stop_reason", "config",
    "camera", "timings", "counts", "metric_config", "samples", "primary_error",
    "cleanup_errors", "provenance",
}


def test_report_is_strict_json_with_fixed_fields_and_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_task.platform, "system", lambda: "Windows")
    harness = Harness(
        tmp_path,
        [(0.5, make_frame(1)), (1.5, make_frame(2)), (2.5, make_frame(3)), (3.1, make_frame(4))],
        duration=3, interval=1,
    )
    report = harness.run()
    text = (harness.output_dir / "capture_task.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    loaded = json.loads(text)
    assert loaded == report

    assert set(loaded) == TOP_FIELDS
    assert loaded["schema_version"] == 1
    assert loaded["report_type"] == "camera_timed_capture"
    assert loaded["status"] == "completed"
    assert loaded["stop_reason"] == "duration_reached"
    assert re.fullmatch(r"[0-9a-f]{32}", loaded["run_id"])
    assert loaded["config"] == {"camera_index": 0, "duration_seconds": 3, "interval_seconds": 1}
    assert loaded["camera"] == {
        "requested_backend": "CAP_DSHOW", "actual_backend": "DSHOW", "first_frame_size": [8, 6],
    }
    assert loaded["metric_config"] == {"dark_threshold": 30, "bright_threshold": 225}
    assert loaded["primary_error"] is None
    assert loaded["cleanup_errors"] == []
    assert loaded["provenance"]["implementation_version"] == "timed-capture-1"
    assert set(loaded["provenance"]["runtime"]) == {"python", "opencv", "numpy"}
    assert set(loaded["provenance"]["source_sha256"]) == {
        "capture_task.py", "run_capture.py", "metrics.py",
        "analysis_config.py", "report.py", "frame_evidence.py",
    }

    for sample in loaded["samples"]:
        assert set(sample) == SAMPLE_FIELDS
        assert sample["image_file"] == f"camera_frame_{loaded['run_id']}_{sample['frame_count']}.png"
        assert sample["scheduled_elapsed_seconds"] == sample["slot_index"] * 1
        assert sample["width"] == 8 and sample["height"] == 6
        assert sample["quality_status"] == sample["color_status"] == sample["image_status"] == "written"
        assert re.fullmatch(r"[0-9a-f]{64}", sample["image_sha256"])

    counts = loaded["counts"]
    assert counts["planned_sample_slots"] == 3
    assert counts["read_attempts"] == 4
    assert counts["valid_frames"] == 4
    assert counts["sample_attempts"] == 3
    assert counts["samples_completed"] == 3
    assert counts["read_attempts"] >= counts["valid_frames"] >= counts["sample_attempts"] >= counts["samples_completed"]
    assert counts["sample_attempts"] == len(loaded["samples"])
    assert counts["sample_attempts"] <= counts["planned_sample_slots"]
    assert counts["samples_completed"] == sum(
        1 for sample in loaded["samples"]
        if sample["quality_status"] == "written"
        and sample["color_status"] == "written"
        and sample["image_status"] == "written"
        and sample["image_sha256"]
    )


def test_task_directory_contains_only_expected_files(tmp_path):
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (1.5, make_frame(2)), (2.5, make_frame(3))],
        duration=2, interval=1,
    )
    report = harness.run()
    names = sorted(path.name for path in harness.output_dir.iterdir())
    expected = sorted(
        ["capture_task.json", "camera_quality_runs.csv", "camera_colors_runs.csv"]
        + [f"camera_frame_{report['run_id']}_{sample['frame_count']}.png" for sample in report["samples"]]
    )
    assert names == expected
    assert not any(name.startswith("camera_session_") for name in names)


def test_device_metadata_null_when_unknown(tmp_path):
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, make_frame(1)), (2.5, make_frame(2))])

    def raise_backend():
        raise cv2.error("后端不可用")

    camera.getBackendName = raise_backend
    harness = Harness(tmp_path, [], duration=2, interval=1, clock=clock, camera=camera)
    report = harness.run()
    assert report["camera"]["actual_backend"] is None
    assert report["camera"]["first_frame_size"] == [8, 6]


def test_no_valid_frame_keeps_first_frame_size_null(tmp_path):
    harness = Harness(tmp_path, [(0.5, None)], duration=5, interval=1)
    with pytest.raises(CaptureTaskError):
        harness.run()
    assert read_report(harness.output_dir)["camera"]["first_frame_size"] is None


def test_per_sample_size_is_recorded_independently(tmp_path):
    harness = Harness(
        tmp_path,
        [(0.5, make_frame(1, (6, 8, 3))), (1.5, make_frame(2, (10, 12, 3))), (3.1, make_frame(3))],
        duration=3, interval=1,
    )
    report = harness.run()
    assert [(s["height"], s["width"]) for s in report["samples"]] == [(6, 8), (10, 12)]
    assert report["camera"]["first_frame_size"] == [8, 6]


def test_runner_rejects_repeated_run(tmp_path):
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    harness.run()
    with pytest.raises(CaptureTaskError) as excinfo:
        harness.runner.run()
    assert "只能执行一次" in str(excinfo.value)


def test_saves_always_use_explicit_task_paths(tmp_path, monkeypatch):
    seen = []
    real_quality = capture_task.append_quality_record
    real_color = capture_task.append_color_record
    real_evidence = capture_task.save_frame_evidence

    def spy_quality(frame_count, brightness, dark_ratio, bright_ratio,
                    sharpness, contrast, report_path=None, *, run_id=None):
        seen.append(("quality", Path(report_path)))
        return real_quality(frame_count, brightness, dark_ratio, bright_ratio,
                            sharpness, contrast, report_path, run_id=run_id)

    def spy_color(frame_count, blue, green, red, report_path=None, *, scene_label=None, run_id=None):
        seen.append(("color", Path(report_path)))
        return real_color(frame_count, blue, green, red, report_path,
                          scene_label=scene_label, run_id=run_id)

    def spy_evidence(frame, run_id, frame_count, output_path=None):
        seen.append(("image", Path(output_path)))
        return real_evidence(frame, run_id, frame_count, output_path)

    monkeypatch.setattr(capture_task, "append_quality_record", spy_quality)
    monkeypatch.setattr(capture_task, "append_color_record", spy_color)
    monkeypatch.setattr(capture_task, "save_frame_evidence", spy_evidence)
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    harness.run()
    assert ("quality", harness.output_dir / "camera_quality_runs.csv") in seen
    assert ("color", harness.output_dir / "camera_colors_runs.csv") in seen
    assert ("image", harness.output_dir / f"camera_frame_{harness.runner.run_id}_1.png") in seen


def test_public_reports_are_not_touched(tmp_path):
    before = {path: _hash_or_none(path) for path in PUBLIC_REPORTS}
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))], duration=2, interval=1,
    )
    harness.run()
    assert {path: _hash_or_none(path) for path in PUBLIC_REPORTS} == before


def test_requested_camera_index_is_used(tmp_path):
    harness = Harness(
        tmp_path, [(0.5, make_frame(1)), (2.5, make_frame(2))],
        duration=2, interval=1, camera_index=3,
    )
    report = harness.run()
    assert harness.requested_indices == [3]
    assert report["config"]["camera_index"] == 3


# ------------------------------------------------ T13 默认工厂读取边界

class FakeVideoCapture:
    """假底层 ``cv2.VideoCapture``：忠实模拟 DirectShow 的旧 ``read()`` 行为。

    ``grab()`` / ``retrieve()`` 是真实标志；``read()`` 故意模仿 OpenCV 5.0.0
    ``cap.cpp`` 的缺陷——忽略 ``retrieve()`` 的布尔返回值，只按输出数组是否
    非空判定成功。默认工厂的适配器**不得**使用这个 ``read()``。

    ``clock`` / ``step``：每次 ``grab()`` 推进可控时钟，用于驱动采样循环。
    """

    def __init__(self, *, clock=None, step=0.0, opened=True, backend="DSHOW",
                 grab_result=True, retrieve_result=True, frame=None,
                 grab_error=None, retrieve_error=None, release_error=None) -> None:
        self.clock = clock
        self.step = step
        self.opened = opened
        self.backend = backend
        self.grab_result = grab_result
        self.retrieve_result = retrieve_result
        self.frame = frame
        self.grab_error = grab_error
        self.retrieve_error = retrieve_error
        self.release_error = release_error
        self.grab_calls = 0
        self.retrieve_calls = 0
        self.read_calls = 0
        self.released = 0

    def _tick(self) -> None:
        if self.clock is not None:
            self.clock.now += self.step

    def isOpened(self) -> bool:
        return self.opened

    def getBackendName(self) -> str:
        return self.backend

    def release(self) -> None:
        self.released += 1
        if self.release_error is not None:
            raise self.release_error

    def grab(self) -> bool:
        self.grab_calls += 1
        self._tick()
        if self.grab_error is not None:
            raise self.grab_error
        return self.grab_result

    def retrieve(self):
        self.retrieve_calls += 1
        if self.retrieve_error is not None:
            raise self.retrieve_error
        return self.retrieve_result, self.frame

    def read(self):
        """旧行为：不使用 ``retrieve()`` 的布尔值，只按数组是否为空判定成功。"""
        self.read_calls += 1
        if not self.grab():
            return False, None
        _ok, frame = self.retrieve()
        return frame is not None and getattr(frame, "size", 0) > 0, frame


def _run_with_default_factory(tmp_path, backend, *, duration, interval, clock,
                              monkeypatch, camera_index=0):
    """经**真实**默认工厂（``_default_camera_factory``）驱动假底层设备。

    不注入 ``camera_factory``：直接替换 ``capture_task.cv2.VideoCapture``，
    以确保被测的是默认工厂实际创建的适配对象，而不是被直接注入的假 camera。
    """
    seen_indices = []

    def fake_constructor(index, *args, **kwargs):
        seen_indices.append(index)
        return backend

    monkeypatch.setattr(capture_task.cv2, "VideoCapture", fake_constructor)
    config = CaptureConfig(
        Path(tmp_path) / "task", camera_index=camera_index,
        duration_seconds=duration, interval_seconds=interval,
    )
    runner = CaptureRunner(config, clock=clock)
    return config, runner, seen_indices


def test_grab_retrieve_adapter_rejects_nonempty_array_on_retrieve_failure():
    """retrieve 返回 False 但数组非空 → 适配器必须返回读取失败。"""
    backend = FakeVideoCapture(grab_result=True, retrieve_result=False, frame=make_frame(1))
    adapter = capture_task._GrabRetrieveCamera(backend)
    ok, frame = adapter.read()
    assert ok is False
    assert frame is None
    assert backend.grab_calls == 1
    assert backend.retrieve_calls == 1
    assert backend.read_calls == 0


def test_grab_retrieve_adapter_grab_failure_skips_retrieve():
    """grab 失败 → 直接返回读取失败，绝不继续 retrieve。"""
    backend = FakeVideoCapture(grab_result=False, frame=make_frame(1))
    adapter = capture_task._GrabRetrieveCamera(backend)
    ok, frame = adapter.read()
    assert ok is False
    assert frame is None
    assert backend.grab_calls == 1
    assert backend.retrieve_calls == 0


def test_grab_retrieve_adapter_passes_frame_through_unchanged():
    frame = make_frame(5)
    backend = FakeVideoCapture(frame=frame)
    adapter = capture_task._GrabRetrieveCamera(backend)
    ok, returned = adapter.read()
    assert ok is True
    assert returned is frame


def test_grab_retrieve_adapter_delegates_lifecycle():
    backend = FakeVideoCapture(backend="DSHOW", opened=True)
    adapter = capture_task._GrabRetrieveCamera(backend)
    assert adapter.isOpened() is True
    assert adapter.getBackendName() == "DSHOW"
    adapter.release()
    assert backend.released == 1


def test_default_factory_retrieve_failure_is_read_failed(tmp_path, monkeypatch):
    """默认工厂路径：grab 成功、retrieve 失败、数组非空 → failed/read_failed。

    这是本轮的**核心回归**：未修改的旧代码会把这个非空数组当作成功帧，
    任务 completed 且保存样本，因此本用例在修复前必然失败。
    """
    clock = FakeClock()
    backend = FakeVideoCapture(
        clock=clock, step=0.5,
        grab_result=True, retrieve_result=False,
        frame=make_frame(1),          # 非空数组：旧 read() 会据此报成功
    )
    config, runner, seen_indices = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    with pytest.raises(CaptureTaskError) as excinfo:
        runner.run()
    assert excinfo.value.stop_reason == "read_failed"

    report = read_report(config.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "read_failed"
    assert report["primary_error"]["stage"] == "read"
    assert report["camera"]["actual_backend"] == "DSHOW"
    assert report["counts"]["read_attempts"] == 1
    assert report["counts"]["valid_frames"] == 0
    assert report["counts"]["sample_attempts"] == 0
    assert report["counts"]["samples_completed"] == 0
    assert report["samples"] == []
    assert seen_indices == [0]
    # 适配器使用了 grab/retrieve，没有走底层那个会误报成功的 read()
    assert backend.grab_calls == 1
    assert backend.retrieve_calls == 1
    assert backend.read_calls == 0
    assert backend.released == 1


def test_default_factory_grab_failure_uses_existing_read_failure_path(tmp_path, monkeypatch):
    """默认工厂路径：grab 失败 → 既有读取失败路径，不调用 retrieve，设备释放。"""
    clock = FakeClock()
    backend = FakeVideoCapture(
        clock=clock, step=0.5, grab_result=False, frame=make_frame(1),
    )
    config, runner, _ = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    with pytest.raises(CaptureTaskError) as excinfo:
        runner.run()
    assert excinfo.value.stop_reason == "read_failed"

    report = read_report(config.output_dir)
    assert report["status"] == "failed"
    assert report["counts"]["read_attempts"] == 1
    assert report["counts"]["valid_frames"] == 0
    assert report["counts"]["samples_completed"] == 0
    assert backend.retrieve_calls == 0
    assert backend.released == 1


def test_default_factory_accepts_successfully_read_black_frame(tmp_path, monkeypatch):
    """grab/retrieve 都成功、画面确实全黑 → 按现有规则正常完成，不判为执行异常。"""
    clock = FakeClock()
    black = np.zeros((6, 8, 3), dtype=np.uint8)
    backend = FakeVideoCapture(clock=clock, step=0.5, frame=black)
    config, runner, _ = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    report = runner.run()
    assert report["status"] == "completed"
    assert report["stop_reason"] == "duration_reached"
    assert report["counts"]["samples_completed"] == 2
    # 全黑帧被正常保存：不改像素、不新增暗图过滤或亮度阈值
    for sample in report["samples"]:
        saved = cv2.imread(str(config.output_dir / sample["image_file"]))
        assert saved is not None
        assert np.array_equal(saved, black)


def test_default_factory_normal_frame_pixels_and_review_unchanged(tmp_path, monkeypatch):
    """默认工厂路径：正常图像像素不变，采样 / PNG / CSV / 离线复核均一致。"""
    clock = FakeClock()
    frame = make_frame(7)
    backend = FakeVideoCapture(clock=clock, step=0.5, frame=frame)
    config, runner, _ = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    report = runner.run()
    assert report["status"] == "completed"
    assert report["counts"]["samples_completed"] == 2
    assert backend.read_calls == 0

    for sample in report["samples"]:
        assert sample["quality_status"] == "written"
        assert sample["color_status"] == "written"
        assert sample["image_status"] == "written"
        saved = cv2.imread(str(config.output_dir / sample["image_file"]))
        assert np.array_equal(saved, frame)

    quality_rows = read_csv_rows(config.output_dir / "camera_quality_runs.csv")
    color_rows = read_csv_rows(config.output_dir / "camera_colors_runs.csv")
    assert len(quality_rows) == len(color_rows) == 2

    review = CaptureTaskReviewer(config.output_dir).review()
    assert review["verification_status"] == "consistent"
    assert review["counts"]["verified_frames"] == 2


@pytest.mark.parametrize("error_attr, error", [
    ("grab_error", RuntimeError("grab 崩了")),
    ("retrieve_error", cv2.error("retrieve 崩了")),
])
def test_default_factory_backend_exception_is_preserved(tmp_path, monkeypatch,
                                                        error_attr, error):
    """底层调用抛异常 → 原样传播（不吞、不包装），设备仍被释放。"""
    clock = FakeClock()
    backend = FakeVideoCapture(clock=clock, step=0.5, frame=make_frame(1),
                               **{error_attr: error})
    config, runner, _ = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    observed = None
    try:
        runner.run()
    except BaseException as caught:  # noqa: BLE001 - 要拿到原始异常对象比对同一性
        observed = caught
    assert observed is error

    report = read_report(config.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "read_failed"
    assert report["primary_error"]["type"] == type(error).__name__
    assert backend.released == 1


def test_default_factory_release_error_is_reported_through_adapter(tmp_path, monkeypatch):
    """适配器正确委托 release：仅释放失败时 stop_reason=release_failed，首错优先不变。"""
    clock = FakeClock()
    release_error = OSError("适配器释放失败")
    backend = FakeVideoCapture(clock=clock, step=0.5, frame=make_frame(1),
                               release_error=release_error)
    config, runner, _ = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock, monkeypatch=monkeypatch,
    )

    observed = None
    try:
        runner.run()
    except BaseException as caught:  # noqa: BLE001
        observed = caught
    assert observed is release_error

    report = read_report(config.output_dir)
    assert report["status"] == "failed"
    assert report["stop_reason"] == "release_failed"
    assert report["primary_error"] is None
    assert report["cleanup_errors"][0]["type"] == "OSError"
    assert report["counts"]["samples_completed"] == 2
    assert backend.released == 1


def test_default_factory_delegates_camera_index(tmp_path, monkeypatch):
    """适配不改变摄像头编号的传递。"""
    clock = FakeClock()
    backend = FakeVideoCapture(clock=clock, step=0.5, frame=make_frame(1))
    config, runner, seen_indices = _run_with_default_factory(
        tmp_path, backend, duration=2, interval=1, clock=clock,
        monkeypatch=monkeypatch, camera_index=3,
    )
    report = runner.run()
    assert seen_indices == [3]
    assert report["config"]["camera_index"] == 3


@pytest.mark.parametrize("system, api, name, actual", [
    ("Windows", cv2.CAP_DSHOW, "CAP_DSHOW", "DSHOW"),
    ("Linux", cv2.CAP_V4L2, "CAP_V4L2", "V4L2"),
])
@pytest.mark.parametrize("outcome", ["normal", "grab_failed", "retrieve_failed", "open_failed"])
def test_platform_default_factory_and_report(tmp_path, monkeypatch, system, api,
                                           name, actual, outcome):
    """真实默认工厂的后端选择、报告、失败传播及释放；不访问硬件。"""
    monkeypatch.setattr(capture_task.platform, "system", lambda: system)
    clock = FakeClock()
    frame = make_frame(7)
    backend = FakeVideoCapture(
        clock=clock, step=0.5, backend=actual, frame=frame,
        opened=outcome != "open_failed",
        grab_result=outcome != "grab_failed",
        retrieve_result=outcome != "retrieve_failed",
    )
    calls = []

    def constructor(index, requested_api):
        calls.append((index, requested_api))
        return backend

    monkeypatch.setattr(capture_task.cv2, "VideoCapture", constructor)
    config = CaptureConfig(tmp_path / "task", camera_index=3,
                           duration_seconds=2, interval_seconds=1)
    runner = CaptureRunner(config, clock=clock)
    if outcome == "normal":
        report = runner.run()
        assert report["status"] == "completed"
        assert report["counts"]["samples_completed"] == 2
        for sample in report["samples"]:
            assert np.array_equal(cv2.imread(str(config.output_dir / sample["image_file"])), frame)
        review = CaptureTaskReviewer(config.output_dir).review()
        assert review["verification_status"] == "consistent"
        assert review["counts"]["verified_frames"] == 2
    else:
        with pytest.raises(CaptureTaskError) as caught:
            runner.run()
        reason = "open_failed" if outcome == "open_failed" else "read_failed"
        assert caught.value.stop_reason == reason
        report = read_report(config.output_dir)
        assert report["status"] == "failed"
        assert report["stop_reason"] == reason
        assert report["counts"]["samples_completed"] == 0
        assert report["samples"] == []
        assert backend.retrieve_calls == (1 if outcome == "retrieve_failed" else 0)
    assert calls == [(3, api)]  # 不枚举设备、不尝试其他后端
    assert report["camera"]["requested_backend"] == name
    assert report["camera"]["actual_backend"] == (None if outcome == "open_failed" else actual)
    assert backend.read_calls == 0
    assert backend.released == 1
