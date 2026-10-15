"""只读复核一个定时采集任务目录：组合既有 CSV 配对与指标重算接口。

本入口只做组合，不新增统计、评分、故障判定、恢复或版本强制闸门：
它读取任务目录中的 `capture_task.json`、两份 CSV 与留证 PNG，
核对任务声明、CSV 关联键、图片摘要与「按当前算法重算」的五项指标，
再输出一份结构化 JSON。不修改输入目录中的任何文件。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import sys
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np

try:
    from .analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from .check_reports import reconcile_reports
    from .verify_frame_metrics import compare_frame_metrics
except ImportError:
    from analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from check_reports import reconcile_reports
    from verify_frame_metrics import compare_frame_metrics


TASK_REPORT_NAME = "capture_task.json"
QUALITY_CSV_NAME = "camera_quality_runs.csv"
COLOR_CSV_NAME = "camera_colors_runs.csv"

TASK_REPORT_TYPE = "camera_timed_capture"
REPORT_TYPE = "capture_task_review"
SCHEMA_VERSION = 1
COMPARISON_BASIS = "current_algorithm_one_decimal"

COMPLETED_STATUS = "completed"

SAVE_STATE_FIELDS = ("quality_status", "color_status", "image_status")
WRITTEN_STATE = "written"

# 只核对这两项指标来源摘要；不核对其他采集源码，也不要求相同 Git 提交。
CONTEXT_SOURCE_FILES = ("metrics.py", "analysis_config.py")

# 稳定问题码。
TASK_SAMPLE_COUNT_MISMATCH = "task_sample_count_mismatch"
TASK_SAMPLE_STATE_MISMATCH = "task_sample_state_mismatch"
CSV_KEYS_MISMATCH = "csv_keys_mismatch"
IMAGE_HASH_MISMATCH = "image_hash_mismatch"
METRIC_MISMATCH = "metric_mismatch"
FRAME_UNVERIFIABLE = "frame_unverifiable"
TASK_NOT_COMPLETED = "task_not_completed"
MEASUREMENT_CONTEXT_UNAVAILABLE = "measurement_context_unavailable"
MEASUREMENT_CONTEXT_DIFFERS = "measurement_context_differs"

EXIT_CODES = {"consistent": 0, "inconsistent": 1, "not_reviewed": 2}

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _issue(code: str, frame_count: int | None, detail: str) -> dict:
    return {"code": code, "frame_count": frame_count, "detail": detail}


def _reject_constant(value: str):
    """拒绝 JSON 中的 NaN/Infinity 等非有限常量。"""
    raise ValueError(f"不允许非有限 JSON 常量: {value}")


def _require_run_id(run_id, path: Path) -> str:
    try:
        if not isinstance(run_id, str) or UUID(hex=run_id).hex != run_id:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"{path}: run_id 必须是 32 位小写十六进制 UUID") from error
    return run_id


def _load_task(path: Path) -> dict:
    """读取并校验任务 JSON 的顶层结构；缺文件、坏 JSON、非对象都是输入错误。"""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except ValueError as error:  # JSONDecodeError 是 ValueError 的子类
        raise ValueError(f"{path}: JSON 无法解析或含非有限常量: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层必须是 JSON 对象")
    return data


def _resolve_within(base: Path, candidate: Path) -> Path:
    """解析路径并确认仍在任务目录内；链接逃逸属于输入错误。"""
    resolved_base = base.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise ValueError(f"路径逃出任务目录: {candidate}")
    return resolved


def _reconcile_reports(quality_path: Path, color_path: Path):
    """组合层调用既有核对；坏 CSV 的 csv.Error 在此转为 ValueError 并保留原因。

    只在本层转换，不改既有 `check_reports.py`；`MemoryError` 与其他未预期异常照常传播。
    """
    try:
        return reconcile_reports(quality_path, color_path)
    except csv.Error as error:
        raise ValueError(
            f"CSV 无法解析（{quality_path.name} 或 {color_path.name}）: {error}"
        ) from error


class CaptureTaskReviewer:
    """复核一个定时采集任务目录。

    构造只保存目录，不打开摄像头、不创建目录、不写文件。
    `review()` 每次都是只读检查，重复调用不累加状态。
    """

    def __init__(self, task_dir) -> None:
        self.task_dir = Path(task_dir)

    def review(self) -> dict:
        task_dir = self.task_dir.resolve()
        report_path = _resolve_within(task_dir, task_dir / TASK_REPORT_NAME)
        quality_path = _resolve_within(task_dir, task_dir / QUALITY_CSV_NAME)
        color_path = _resolve_within(task_dir, task_dir / COLOR_CSV_NAME)

        task = _load_task(report_path)

        version = task.get("schema_version")
        if type(version) is not int or version != SCHEMA_VERSION:
            raise ValueError(f"{report_path}: schema_version 必须是整数 {SCHEMA_VERSION}")
        if task.get("report_type") != TASK_REPORT_TYPE:
            raise ValueError(f"{report_path}: report_type 必须是 {TASK_REPORT_TYPE}")
        run_id = _require_run_id(task.get("run_id"), report_path)

        status = task.get("status")
        if not isinstance(status, str):
            raise ValueError(f"{report_path}: status 必须是字符串")

        if status != COMPLETED_STATUS:
            return self._not_reviewed(run_id, status)

        samples = self._read_samples(task, report_path, run_id, task_dir)
        frame_counts = [sample["frame_count"] for sample in samples]

        issues = []
        task_counts = task.get("counts")
        declared_count = task_counts.get("samples_completed") if isinstance(task_counts, dict) else None
        if type(declared_count) is not int or declared_count < 0:
            raise ValueError(f"{report_path}: counts.samples_completed 必须是非负整数")
        if declared_count != len(samples):
            issues.append(_issue(
                TASK_SAMPLE_COUNT_MISMATCH, None,
                f"任务声明 samples_completed={declared_count}，实际样本数={len(samples)}",
            ))

        unwritten = [sample["frame_count"] for sample in samples if not sample["state_ok"]]
        if unwritten:
            issues.append(_issue(
                TASK_SAMPLE_STATE_MISMATCH, None,
                f"这些帧的保存状态不是 {WRITTEN_STATE}: {unwritten}",
            ))

        warnings = self._context_warnings(task, report_path)

        matched, quality_only, color_only = _reconcile_reports(quality_path, color_path)
        present = matched | quality_only | color_only
        declared_keys = {(run_id, frame_count) for frame_count in frame_counts}
        if quality_only or color_only or present != declared_keys:
            detail = (
                f"任务声明 {len(declared_keys)} 个键，CSV 实际出现 {len(present)} 个键；"
                f"仅质量 {len(quality_only)}，仅颜色 {len(color_only)}"
            )
            issues.append(_issue(CSV_KEYS_MISMATCH, None, detail))
            return self._result(
                run_id, status, "inconsistent", issues, warnings, frames=[],
                reported_samples=declared_count, csv_pairs=len(matched), verified_frames=0,
            )

        frames = []
        verified_frames = 0
        for sample in sorted(samples, key=lambda item: item["frame_count"]):
            frame, frame_issues, verified = self._review_frame(
                sample, run_id, task_dir, quality_path, color_path
            )
            frames.append(frame)
            issues.extend(frame_issues)
            verified_frames += 1 if verified else 0

        verification_status = "consistent" if not issues else "inconsistent"
        return self._result(
            run_id, status, verification_status, issues, warnings, frames=frames,
            reported_samples=declared_count, csv_pairs=len(matched),
            verified_frames=verified_frames,
        )

    # ---------- 内部步骤 ----------

    def _read_samples(self, task: dict, report_path: Path, run_id: str, task_dir: Path) -> list[dict]:
        """校验 samples 的必需字段，并预先确认图片路径安全（先于任何读取）。"""
        samples = task.get("samples")
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"{report_path}: completed 任务的 samples 必须是非空数组")

        parsed = []
        seen = set()
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError(f"{report_path}: samples 的每一项必须是对象")

            frame_count = sample.get("frame_count")
            if type(frame_count) is not int or frame_count < 1:
                raise ValueError(f"{report_path}: 样本帧号必须是正整数")
            if frame_count in seen:
                raise ValueError(f"{report_path}: 重复的样本帧号 {frame_count}")
            seen.add(frame_count)

            expected_name = f"camera_frame_{run_id}_{frame_count}.png"
            if sample.get("image_file") != expected_name:
                raise ValueError(f"{report_path}: 帧 {frame_count} 的 image_file 必须是 {expected_name}")

            image_sha256 = sample.get("image_sha256")
            if not isinstance(image_sha256, str) or not _SHA256_PATTERN.fullmatch(image_sha256):
                raise ValueError(f"{report_path}: 帧 {frame_count} 的 image_sha256 必须是 64 位小写十六进制")

            for field in SAVE_STATE_FIELDS:
                if not isinstance(sample.get(field), str):
                    raise ValueError(f"{report_path}: 帧 {frame_count} 缺少字符串字段 {field}")

            image_path = _resolve_within(task_dir, task_dir / expected_name)
            parsed.append({
                "frame_count": frame_count,
                "image_file": expected_name,
                "image_sha256": image_sha256,
                "image_path": image_path,
                "state_ok": all(sample[field] == WRITTEN_STATE for field in SAVE_STATE_FIELDS),
            })
        return parsed

    def _review_frame(self, sample, run_id, task_dir, quality_path, color_path):
        """复核单帧：文件摘要与指标分别核对；无法读取/重算只记录，不中断其他帧。"""
        frame_count = sample["frame_count"]
        hash_issue = None
        metric_issue = None
        unverifiable = None
        image_sha256_match = None
        metrics = None

        try:
            digest = hashlib.sha256(sample["image_path"].read_bytes()).hexdigest()
        except OSError as error:
            unverifiable = f"无法读取留证图片: {error}"
        else:
            image_sha256_match = digest == sample["image_sha256"]
            if not image_sha256_match:
                hash_issue = f"文件摘要 {digest} 与任务记录 {sample['image_sha256']} 不同"

        try:
            compared = compare_frame_metrics(
                run_id, frame_count, task_dir, quality_path, color_path
            )
        except (OSError, ValueError, cv2.error) as error:
            unverifiable = (
                f"{unverifiable}；无法重算指标: {error}" if unverifiable
                else f"无法重算指标: {error}"
            )
        else:
            metrics = {name: [saved, recalculated] for name, (saved, recalculated) in compared.items()}
            different = [name for name, (saved, recalculated) in compared.items() if saved != recalculated]
            if different:
                metric_issue = f"指标不同: {', '.join(different)}"

        frame_issues = []
        if unverifiable is not None:
            frame_issues.append(_issue(FRAME_UNVERIFIABLE, frame_count, unverifiable))
        if hash_issue is not None:
            frame_issues.append(_issue(IMAGE_HASH_MISMATCH, frame_count, hash_issue))
        if metric_issue is not None:
            frame_issues.append(_issue(METRIC_MISMATCH, frame_count, metric_issue))

        frame = {
            "frame_count": frame_count,
            "image_sha256_match": image_sha256_match,
            "metrics": metrics,
        }
        verified = image_sha256_match is True and metrics is not None and metric_issue is None
        return frame, frame_issues, verified

    def _context_warnings(self, task: dict, report_path: Path) -> list[dict]:
        """比较任务记录与当前口径；缺失或不同只提示，不阻断文件与指标检查。"""
        missing = []
        differs = []

        metric_config = task.get("metric_config")
        if not isinstance(metric_config, dict):
            missing.append("metric_config")
        else:
            for key, current in (("dark_threshold", DARK_THRESHOLD), ("bright_threshold", BRIGHT_THRESHOLD)):
                if key not in metric_config:
                    missing.append(f"metric_config.{key}")
                elif metric_config[key] != current:
                    differs.append(f"metric_config.{key}: 任务={metric_config[key]} 当前={current}")

        provenance = task.get("provenance")
        runtime = provenance.get("runtime") if isinstance(provenance, dict) else None
        if not isinstance(runtime, dict):
            missing.append("provenance.runtime")
        else:
            current_runtime = {
                "python": platform.python_version(),
                "opencv": cv2.__version__,
                "numpy": np.__version__,
            }
            for key, current in current_runtime.items():
                if key not in runtime:
                    missing.append(f"runtime.{key}")
                elif runtime[key] != current:
                    differs.append(f"runtime.{key}: 任务={runtime[key]} 当前={current}")

        digests = provenance.get("source_sha256") if isinstance(provenance, dict) else None
        if not isinstance(digests, dict):
            missing.append("provenance.source_sha256")
        else:
            for name in CONTEXT_SOURCE_FILES:
                if name not in digests:
                    missing.append(f"source_sha256.{name}")
                    continue
                current = hashlib.sha256((SRC_DIR / name).read_bytes()).hexdigest()
                if digests[name] != current:
                    differs.append(f"source_sha256.{name}: 任务={digests[name]} 当前={current}")

        warnings = []
        if missing:
            warnings.append(_issue(
                MEASUREMENT_CONTEXT_UNAVAILABLE, None, "任务缺少口径字段: " + "，".join(missing)
            ))
        if differs:
            warnings.append(_issue(
                MEASUREMENT_CONTEXT_DIFFERS, None,
                "任务记录与当前口径不同（仅为比较口径提示，不代表图片或相机故障）: " + "，".join(differs),
            ))
        return warnings

    def _not_reviewed(self, run_id: str, status: str) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_type": REPORT_TYPE,
            "run_id": run_id,
            "task_status": status,
            "verification_status": "not_reviewed",
            "comparison_basis": COMPARISON_BASIS,
            "counts": None,
            "frames": [],
            "issues": [_issue(TASK_NOT_COMPLETED, None, f"任务状态为 {status}，不复核部分记录")],
            "warnings": [],
        }

    def _result(self, run_id, status, verification_status, issues, warnings,
                frames, reported_samples, csv_pairs, verified_frames) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_type": REPORT_TYPE,
            "run_id": run_id,
            "task_status": status,
            "verification_status": verification_status,
            "comparison_basis": COMPARISON_BASIS,
            "counts": {
                "reported_samples": reported_samples,
                "csv_pairs": csv_pairs,
                "verified_frames": verified_frames,
            },
            "frames": frames,
            "issues": issues,
            "warnings": warnings,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path, help="定时采集任务目录")
    args = parser.parse_args(argv)
    try:
        result = CaptureTaskReviewer(args.task_dir).review()
    except (OSError, UnicodeError, ValueError, csv.Error, cv2.error) as error:
        print(f"复核失败: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_CODES[result["verification_status"]]


if __name__ == "__main__":
    sys.exit(main())
