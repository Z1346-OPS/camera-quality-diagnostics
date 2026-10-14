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


def test_report_is_strict_json_with_fixed_fields_and_counts(tmp_path):
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
