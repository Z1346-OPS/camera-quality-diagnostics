"""定时采集与间隔留证（业务阶段 4.4）。

无预览的定时采集：按固定间隔从单个摄像头取帧，只对选中帧测量、保存并留证，
最后发布一份 `capture_task.json` 任务报告。

首版只做运行保护：不重试、不切换后端、不自动重连、不做质量评分或故障判定，
也不保证严格到时退出（同步读取、测量与保存都可能阻塞）。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

if __package__:
    from .analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from .frame_evidence import save_frame_evidence
    from .metrics import (
        calculate_bgr_means,
        calculate_contrast,
        calculate_exposure_ratios,
        calculate_mean_brightness,
        calculate_sharpness,
    )
    from .report import append_color_record, append_quality_record
else:
    from analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from frame_evidence import save_frame_evidence
    from metrics import (
        calculate_bgr_means,
        calculate_contrast,
        calculate_exposure_ratios,
        calculate_mean_brightness,
        calculate_sharpness,
    )
    from report import append_color_record, append_quality_record


IMPLEMENTATION_VERSION = "timed-capture-1"

# 首版运行保护策略，不是相机或质量阈值。
MAX_CAMERA_INDEX = 2**31 - 1
MAX_DURATION_SECONDS = 3600
MAX_INTERVAL_SECONDS = 3600
MAX_PLANNED_SAMPLE_SLOTS = 120

QUALITY_CSV_NAME = "camera_quality_runs.csv"
COLOR_CSV_NAME = "camera_colors_runs.csv"
REPORT_NAME = "capture_task.json"
REPORT_TEMP_NAME = "capture_task.json.tmp"

SCENE_LABEL = "unspecified"

# 报告 provenance 需要摘要的源文件（相对项目根的 src/ 目录）。
SOURCE_FILES = (
    "capture_task.py",
    "run_capture.py",
    "metrics.py",
    "analysis_config.py",
    "report.py",
    "frame_evidence.py",
)

# 不得作为任务输出目录的位置：原图、合成样本、既有实验、冻结证据、源码目录。
PROTECTED_RELATIVE_ROOTS = (
    "photo",
    "data/samples",
    "data/experiments",
    "data/manifests",
    "docs",
    "src",
    "tests",
    "tools",
    ".git",
    ".github",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CaptureTaskError(Exception):
    """逻辑失败。

    底层异常（`OSError`、`cv2.error`、`MemoryError` 等）保留原类型，不包装成此类。
    """

    def __init__(self, message: str, *, stop_reason: str, stage: str | None = None) -> None:
        super().__init__(message)
        self.stop_reason = stop_reason
        self.stage = stage


def _require_int(name: str, value, minimum: int, maximum: int) -> None:
    """布尔值不算整数。"""
    if type(value) is not int:
        raise CaptureTaskError(
            f"{name} 必须是整数，实际为 {type(value).__name__}",
            stop_reason="execution_error",
            stage="config",
        )
    if not minimum <= value <= maximum:
        raise CaptureTaskError(
            f"{name} 必须在 {minimum}～{maximum} 之间，实际为 {value}",
            stop_reason="execution_error",
            stage="config",
        )


def _is_protected_output(path: Path) -> bool:
    resolved = path.resolve()
    for relative in PROTECTED_RELATIVE_ROOTS:
        root = (PROJECT_ROOT / relative).resolve()
        if resolved == root or root in resolved.parents:
            return True
    return False


@dataclass(frozen=True)
class CaptureConfig:
    """一次定时采集任务的配置；构造即校验。"""

    output_dir: Path
    camera_index: int = 0
    duration_seconds: int = 30
    interval_seconds: int = 5

    def __post_init__(self) -> None:
        _require_int("camera-index", self.camera_index, 0, MAX_CAMERA_INDEX)
        _require_int("duration", self.duration_seconds, 1, MAX_DURATION_SECONDS)
        _require_int("interval", self.interval_seconds, 1, MAX_INTERVAL_SECONDS)

        planned = (
            self.duration_seconds + self.interval_seconds - 1
        ) // self.interval_seconds
        if planned > MAX_PLANNED_SAMPLE_SLOTS:
            raise CaptureTaskError(
                f"理论采样点数 {planned} 超过上限 {MAX_PLANNED_SAMPLE_SLOTS}",
                stop_reason="execution_error",
                stage="config",
            )

        if not isinstance(self.output_dir, (str, os.PathLike)):
            raise CaptureTaskError(
                "output-dir 必须是路径",
                stop_reason="execution_error",
                stage="config",
            )
        path = Path(self.output_dir)
        if _is_protected_output(path):
            raise CaptureTaskError(
                f"输出目录位于受保护路径，拒绝使用: {path}",
                stop_reason="execution_error",
                stage="config",
            )
        if path.exists():
            raise CaptureTaskError(
                f"输出目录已存在，拒绝使用: {path}",
                stop_reason="execution_error",
                stage="config",
            )
        object.__setattr__(self, "output_dir", path)

    @property
    def planned_sample_slots(self) -> int:
        return (
            self.duration_seconds + self.interval_seconds - 1
        ) // self.interval_seconds


class _GrabRetrieveCamera:
    """默认摄像头读取边界的薄适配：显式传播 ``grab()``/``retrieve()`` 的真实标志。

    背景（已核对 OpenCV 5.0.0 官方源码，见 `docs/stage-37-read-failure-guard.md`）：
    ``cv2.VideoCapture.read()`` 丢弃 ``retrieve()`` 的布尔返回值，只按输出数组是否
    为空判定成功；DirectShow 的 ``retrieveFrame()`` 在取像素**之前**先
    ``frame.create()`` 预分配非空数组，因此取帧超时失败时仍可能返回非空数组。
    这会让「上游未取到帧」被上层误计为成功采集。

    本适配器只在 ``grab()`` 与 ``retrieve()`` **都**成功时把原始帧原样交给上层；
    任一失败即返回 ``(False, None)``，交由 ``CaptureRunner`` 既有的 ``read_failed``
    流程处理。它不重试、不补采、不删帧、不改像素、不判定画面质量。

    只委托 ``CaptureRunner`` 实际用到的接口：``isOpened`` / ``getBackendName`` /
    ``release`` / ``read``。
    """

    def __init__(self, capture) -> None:
        self._capture = capture

    def isOpened(self) -> bool:
        return self._capture.isOpened()

    def getBackendName(self):
        return self._capture.getBackendName()

    def release(self) -> None:
        self._capture.release()

    def read(self):
        """返回 ``(ok, frame)``，与 ``cv2.VideoCapture.read()`` 形状一致。

        grab 失败即返回失败且**不**继续 retrieve；retrieve 以其真实布尔标志为准，
        失败时即使底层给出非空数组也不作为成功帧上交。
        """
        if not self._capture.grab():
            return False, None
        retrieved, frame = self._capture.retrieve()
        if not retrieved:
            return False, None
        return True, frame


def _requested_backend() -> str:
    """Linux 使用 V4L2；其他平台保持原 DirectShow 行为（未新增支持声明）。"""
    return "CAP_V4L2" if platform.system() == "Linux" else "CAP_DSHOW"


def _default_camera_factory(camera_index: int):
    """Windows DirectShow / Linux V4L2；只打开配置的编号，不做探测读帧。

    返回薄适配对象：其 ``read()`` 显式检查 ``grab()``/``retrieve()`` 的真实成功标志，
    避免底层取帧失败但输出数组非空时被误计为成功采集。
    """
    capture = cv2.VideoCapture(camera_index, getattr(cv2, _requested_backend()))
    return _GrabRetrieveCamera(capture)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _runtime_versions() -> dict:
    return {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
    }


def _collect_source_sha256() -> dict:
    """在打开设备前收集来源摘要；收集失败明确报错。"""
    src_dir = PROJECT_ROOT / "src"
    digests = {}
    for name in SOURCE_FILES:
        try:
            digests[name] = hashlib.sha256((src_dir / name).read_bytes()).hexdigest()
        except OSError as error:
            raise CaptureTaskError(
                f"无法读取来源文件 {name}: {error}",
                stop_reason="execution_error",
                stage="provenance",
            ) from error
    return digests


def _is_valid_frame(frame) -> bool:
    return (
        isinstance(frame, np.ndarray)
        and frame.dtype == np.uint8
        and frame.ndim == 3
        and frame.shape[2] == 3
        and frame.shape[0] > 0
        and frame.shape[1] > 0
    )


def _read_backend_name(camera) -> str | None:
    try:
        name = camera.getBackendName()
    except (AttributeError, cv2.error):
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    return name


def _release_camera(camera) -> tuple[list, BaseException | None]:
    """尝试释放摄像头。

    返回 (cleanup_errors 条目, 首个释放异常对象)。
    异常对象必须保留：没有更早的执行错误时，API 要重新抛出原始释放异常，
    不能把底层异常（如 MemoryError）转换成逻辑失败。
    """
    entries = []
    first_error = None
    try:
        camera.release()
    except BaseException as error:  # noqa: BLE001 - 释放失败要如实记录，不能吞掉
        entries.append({"type": type(error).__name__, "message": str(error)})
        first_error = error
    return entries, first_error


def _error_entry(stage, error) -> dict:
    return {
        "stage": stage,
        "type": type(error).__name__,
        "message": str(error),
    }


def _secondary_note(kind: str, stage: str, error) -> str:
    """附加错误文本：包含阶段、异常类型与信息，供 CLI 明确输出。"""
    return f"{kind} 阶段={stage} 类型={type(error).__name__} 信息={error}"


def _add_note(error, note: str) -> None:
    try:
        error.add_note(note)
    except AttributeError:  # pragma: no cover - 3.11+ 一定有 add_note
        pass


def _new_report(config: CaptureConfig, run_id: str) -> dict:
    return {
        "schema_version": 1,
        "report_type": "camera_timed_capture",
        "run_id": run_id,
        "status": "failed",
        "stop_reason": "execution_error",
        "config": {
            "camera_index": config.camera_index,
            "duration_seconds": config.duration_seconds,
            "interval_seconds": config.interval_seconds,
        },
        "camera": {
            "requested_backend": _requested_backend(),
            "actual_backend": None,
            "first_frame_size": None,
        },
        "timings": {
            "started_at_utc": None,
            "ended_at_utc": None,
            "capture_elapsed_seconds": None,
        },
        "counts": {
            "planned_sample_slots": config.planned_sample_slots,
            "read_attempts": 0,
            "valid_frames": 0,
            "sample_attempts": 0,
            "samples_completed": 0,
        },
        "metric_config": {
            "dark_threshold": DARK_THRESHOLD,
            "bright_threshold": BRIGHT_THRESHOLD,
        },
        "samples": [],
        "primary_error": None,
        "cleanup_errors": [],
        "provenance": {
            "implementation_version": IMPLEMENTATION_VERSION,
            "runtime": _runtime_versions(),
            "source_sha256": {},
        },
    }


def _new_sample(frame_count, slot_index, interval, read_elapsed, frame, run_id) -> dict:
    return {
        "frame_count": frame_count,
        "slot_index": slot_index,
        "scheduled_elapsed_seconds": slot_index * interval,
        "read_elapsed_seconds": read_elapsed,
        "width": int(frame.shape[1]),
        "height": int(frame.shape[0]),
        "quality_status": "not_attempted",
        "color_status": "not_attempted",
        "image_status": "not_attempted",
        "image_file": f"camera_frame_{run_id}_{frame_count}.png",
        "image_sha256": None,
    }


def _measure_frame(frame) -> dict:
    """只对选中帧测量；复用既有指标函数，不改算法或默认值。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark_ratio, bright_ratio = calculate_exposure_ratios(
        gray, DARK_THRESHOLD, BRIGHT_THRESHOLD
    )
    blue_mean, green_mean, red_mean = calculate_bgr_means(frame)
    return {
        "brightness": calculate_mean_brightness(gray),
        "dark_ratio": dark_ratio,
        "bright_ratio": bright_ratio,
        "sharpness": calculate_sharpness(gray),
        "contrast": calculate_contrast(gray),
        "blue_mean": blue_mean,
        "green_mean": green_mean,
        "red_mean": red_mean,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _publish_report(report: dict, target: Path) -> Path:
    """完整关闭同目录临时文件后，以独占硬链接发布；不替换已有目标。

    硬链接让目标在发布时直接指向完整文件，且目标同时被别人创建时也拒绝覆盖。
    文件系统不支持硬链接时明确失败，保留临时证据，不降级到覆盖式发布。
    """
    target = Path(target)
    if target.exists():
        raise CaptureTaskError(
            f"报告目标已存在，拒绝覆盖: {target}",
            stop_reason="execution_error",
            stage="report",
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temp = target.parent / REPORT_TEMP_NAME
    with temp.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    try:
        os.link(temp, target)
    except FileExistsError as error:
        raise CaptureTaskError(
            f"报告目标已存在，拒绝覆盖: {target}",
            stop_reason="execution_error",
            stage="report",
        ) from error
    try:
        temp.unlink()
    except BaseException as error:
        _add_note(error, f"完整报告已发布: {target}；临时链接未移除: {temp}")
        raise
    return target


class CaptureRunner:
    """管理一次定时采集任务的设备生命周期、采样与结果。

    单个执行器只执行一次任务；重复调用 `run()` 明确拒绝。
    """

    def __init__(
        self,
        config: CaptureConfig,
        *,
        camera_factory=None,
        clock=None,
    ) -> None:
        if not isinstance(config, CaptureConfig):
            raise TypeError("config 必须是 CaptureConfig")
        self.config = config
        self.run_id = uuid4().hex
        self._camera_factory = camera_factory or _default_camera_factory
        self._clock = clock or time.monotonic
        self._used = False
        self._failure = None

    # ---------- 内部工具 ----------

    def _fail(self, error, stage: str, stop_reason: str):
        self._failure = {"stage": stage, "stop_reason": stop_reason, "exception": error}
        return error

    def _stage_for(self, error) -> str:
        failure = self._failure
        if failure is not None and failure["exception"] is error:
            return failure["stage"]
        if isinstance(error, CaptureTaskError) and error.stage is not None:
            return error.stage
        return "capture"

    def _reason_for(self, error) -> str:
        if isinstance(error, KeyboardInterrupt):
            return "interrupted"
        if isinstance(error, CaptureTaskError):
            return error.stop_reason
        failure = self._failure
        if failure is not None and failure["exception"] is error:
            return failure["stop_reason"]
        return "execution_error"

    # ---------- 主流程 ----------

    def run(self) -> dict:
        if self._used:
            raise CaptureTaskError(
                "同一个执行器只能执行一次任务",
                stop_reason="execution_error",
                stage="execution",
            )
        self._used = True
        self._failure = None

        config = self.config
        report = _new_report(config, self.run_id)

        # 来源摘要在打开设备前收集；失败即报错，不带缺失来源继续采集。
        report["provenance"]["source_sha256"] = _collect_source_sha256()

        output_dir = Path(config.output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise CaptureTaskError(
                f"输出目录已存在，拒绝使用: {output_dir}",
                stop_reason="execution_error",
                stage="output",
            ) from error

        original_exception = None
        camera = None
        t0 = None
        release_exception = None
        try:
            try:
                camera = self._camera_factory(config.camera_index)
            except BaseException as error:
                raise self._fail(error, "open", "open_failed")

            opened = False
            if camera is not None:
                try:
                    opened = bool(camera.isOpened())
                except BaseException as error:
                    raise self._fail(error, "open", "open_failed")
            if not opened:
                raise CaptureTaskError(
                    "无法打开摄像头",
                    stop_reason="open_failed",
                    stage="open",
                )

            t0 = self._clock()
            report["timings"]["started_at_utc"] = _utc_now_iso()
            report["camera"]["actual_backend"] = _read_backend_name(camera)

            reason = self._capture_loop(camera, t0, report)
            if reason == "duration_reached" and report["counts"]["samples_completed"] == 0:
                raise CaptureTaskError(
                    "到时结束但没有取得完整样本",
                    stop_reason="no_samples",
                    stage="capture",
                )
            report["stop_reason"] = reason
        except BaseException as error:
            original_exception = error
            report["stop_reason"] = self._reason_for(error)
            report["primary_error"] = _error_entry(self._stage_for(error), error)
        finally:
            if t0 is not None:
                report["timings"]["ended_at_utc"] = _utc_now_iso()
                report["timings"]["capture_elapsed_seconds"] = self._clock() - t0
            if camera is not None:
                entries, release_exception = _release_camera(camera)
                report["cleanup_errors"].extend(entries)

        # 首个错误优先：执行错误 → 释放错误 → 正常完成。
        primary_exception = (
            original_exception if original_exception is not None else release_exception
        )
        if primary_exception is None:
            status = "completed" if report["stop_reason"] == "duration_reached" else "failed"
        elif isinstance(primary_exception, KeyboardInterrupt):
            status = "interrupted"
            report["stop_reason"] = "interrupted"
        else:
            status = "failed"
            if original_exception is None:
                report["stop_reason"] = "release_failed"
        report["status"] = status

        # 尽力发布最终报告；发布阶段的异常（含 KeyboardInterrupt）都不得替换首个错误。
        publish_error = None
        try:
            _publish_report(report, output_dir / REPORT_NAME)
        except BaseException as error:  # noqa: BLE001 - 见下：发布错误只作为附加信息
            publish_error = error

        if primary_exception is not None:
            if publish_error is not None:
                _add_note(primary_exception, _secondary_note("报告发布失败", "report", publish_error))
            if release_exception is not None and release_exception is not primary_exception:
                _add_note(primary_exception, _secondary_note("释放设备失败", "release", release_exception))
            raise primary_exception
        if publish_error is not None:
            raise publish_error
        if status != "completed":
            raise CaptureTaskError(
                f"任务未正常完成: {report['stop_reason']}",
                stop_reason=report["stop_reason"],
                stage="capture",
            )
        return report

    def _capture_loop(self, camera, t0, report) -> str:
        config = self.config
        counts = report["counts"]
        samples = report["samples"]
        sampled_slots = set()
        first_size_recorded = False

        while True:
            # 3. read() 前检查截止时间，已到则不再读取。
            if self._clock() - t0 >= config.duration_seconds:
                return "duration_reached"

            # 抛出异常的 read 也算一次尝试：留证要如实记录「试过并失败」。
            counts["read_attempts"] += 1
            try:
                ok, frame = camera.read()
            except BaseException as error:
                raise self._fail(error, "read", "read_failed")
            elapsed = self._clock() - t0

            # 5. 读取失败或无效图像优先作为错误，不因已经超时而掩盖失败。
            if not ok:
                raise CaptureTaskError(
                    "读取画面失败",
                    stop_reason="read_failed",
                    stage="read",
                )
            if not _is_valid_frame(frame):
                raise CaptureTaskError(
                    "无效图像：需要非空 uint8 的 H×W×3 数组",
                    stop_reason="invalid_frame",
                    stage="read",
                )

            counts["valid_frames"] += 1
            if not first_size_recorded:
                report["camera"]["first_frame_size"] = [
                    int(frame.shape[1]),
                    int(frame.shape[0]),
                ]
                first_size_recorded = True

            # 8. 截止后返回的有效帧计入有效帧数，但不保存。
            if elapsed >= config.duration_seconds:
                continue

            # 9–11. 区间归属；同一区间最多一个样本，不补采跨过的旧区间。
            slot_index = int(elapsed // config.interval_seconds)
            if slot_index in sampled_slots:
                continue
            sampled_slots.add(slot_index)

            sample = _new_sample(
                counts["valid_frames"],
                slot_index,
                config.interval_seconds,
                elapsed,
                frame,
                self.run_id,
            )
            samples.append(sample)
            counts["sample_attempts"] += 1

            # 12. 处理与保存即使跨过截止时间也允许完成该样本。
            self._process_sample(frame, sample)
            counts["samples_completed"] += 1

    def _process_sample(self, frame, sample: dict) -> None:
        """先计算指标 → 质量 CSV → 颜色 CSV → PNG → PNG 摘要；任一步失败即停止。"""
        output_dir = Path(self.config.output_dir)

        try:
            metrics = _measure_frame(frame)
        except BaseException as error:
            raise self._fail(error, "measurement", "measurement_failed")

        try:
            append_quality_record(
                sample["frame_count"],
                metrics["brightness"],
                metrics["dark_ratio"],
                metrics["bright_ratio"],
                metrics["sharpness"],
                metrics["contrast"],
                output_dir / QUALITY_CSV_NAME,
                run_id=self.run_id,
            )
        except BaseException as error:
            sample["quality_status"] = "failed"
            raise self._fail(error, "save", "save_failed")
        sample["quality_status"] = "written"

        try:
            append_color_record(
                sample["frame_count"],
                metrics["blue_mean"],
                metrics["green_mean"],
                metrics["red_mean"],
                output_dir / COLOR_CSV_NAME,
                scene_label=SCENE_LABEL,
                run_id=self.run_id,
            )
        except BaseException as error:
            sample["color_status"] = "failed"
            raise self._fail(error, "save", "save_failed")
        sample["color_status"] = "written"

        try:
            save_frame_evidence(
                frame,
                self.run_id,
                sample["frame_count"],
                output_dir / sample["image_file"],
            )
        except BaseException as error:
            sample["image_status"] = "failed"
            raise self._fail(error, "save", "save_failed")
        sample["image_status"] = "written"

        try:
            sample["image_sha256"] = _sha256_file(output_dir / sample["image_file"])
        except BaseException as error:
            raise self._fail(error, "save", "save_failed")
