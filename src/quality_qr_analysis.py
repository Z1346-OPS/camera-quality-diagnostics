"""把同一张图、同一区域的 Phase 4.1 质量测量与既有 QR 报告关联起来。

本模块是**外围组合层**：不重写解码、不重写测量、不改既有报告字段。
它把既有 `analyze_label` 的完整输出作为子对象 `qr_report` **原样保留**，
把 `analyze_quality` 的测量放在旁边，并用**读取一致性**、**区域对应**与
**profile 归并**把两者关联成一条可追溯的结构化记录。

能力边界（**不得夸大**）：本模块采用外围组合，会**读取两次**
（一次供质量测量，一次由 `analyze_label` 内部读取）。它提供的是**规定检查范围内**
的一致性证据——即 `read_consistency.checked_fields` 列出的字段在两次读取中相同。
它**不声称**单次读取，**不声称**文件在整个过程中始终未变化，
也**不声称**检查范围之外的差异不存在。

本模块**不写文件**、不联网、不打开相机、不调用 CLI、不新增第三方依赖。
"""

from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as _package_version
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

import cv2
import numpy as np
from PIL import __version__ as pillow_version

if __package__:
    from . import analyze_image as images
    from . import analyze_label as label_module
    from .quality_analysis import QualityAnalysisError, analyze_quality
else:
    import analyze_image as images
    import analyze_label as label_module
    from quality_analysis import QualityAnalysisError, analyze_quality


SCHEMA_VERSION = 1
REPORT_TYPE = "quality_qr_association"
IMPLEMENTATION_VERSION = "quality-qr-association-1"

# 质量测量始终在标准化后的**原图区域**上完成，不是解码器内部降采样后的图。
BASIS = "original_normalized_image_region"

# 读取一致性实际比对的字段，顺序固定（契约 1、2）。
CHECKED_FIELDS = [
    "sha256", "format", "mode", "width", "height",
    "exif_orientation", "analysis_width", "analysis_height",
]

# provenance.source_sha256 至少覆盖的源码文件。
SOURCE_FILES = (
    "quality_qr_analysis.py", "quality_analysis.py", "analyze_label.py",
    "label_analysis.py", "analyze_image.py", "analysis_config.py", "metrics.py",
)


class QualityQrAssociationError(ValueError):
    """关联层自身的错误；首版只有读取一致性失败一种。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _source_sha256():
    root = Path(__file__).resolve().parents[1]
    sources = {}
    for name in SOURCE_FILES:
        try:
            sources[name] = sha256((root / "src" / name).read_bytes()).hexdigest()
        except OSError:
            sources[name] = None
    return sources


def _runtime_versions():
    try:
        zxing_version = _package_version("zxing-cpp")
    except PackageNotFoundError:
        zxing_version = None
    return {
        "python": sys.version.split()[0], "opencv": cv2.__version__,
        "numpy": np.__version__, "pillow": pillow_version, "zxing_cpp": zxing_version,
    }


def _read_fields(source, preprocessing):
    """从一次读取的 `source` / `preprocessing` 里取出参与比对的 8 个字段。"""
    return {
        "sha256": source["sha256"], "format": source["format"], "mode": source["mode"],
        "width": source["width"], "height": source["height"],
        "exif_orientation": preprocessing["exif_orientation"],
        "analysis_width": preprocessing["analysis_width"],
        "analysis_height": preprocessing["analysis_height"],
    }


def _measure(bgr, roi_argument):
    """调用一次 `analyze_quality`；只有 `QualityAnalysisError` 转成 `quality_error`。

    `MemoryError`、`cv2.error` 与其他未预期异常一律继续抛出，不得解释为图像质量问题。
    """
    started = perf_counter()
    quality, quality_error = None, None
    try:
        quality = analyze_quality(bgr, roi_argument)
    except QualityAnalysisError as error:
        quality_error = {"code": error.code, "message": str(error),
                         "exception_type": type(error).__name__}
    return quality, quality_error, perf_counter() - started


def analyze_quality_and_qr(path, roi=None, expected_file=None, truth_source=None, *,
                           try_downscale=False):
    """对同一张图、同一个区域同时取得 QR 结果与质量测量，并输出可追溯的关联记录。

    `path` / `roi` / `expected_file` / `truth_source` / `try_downscale` 的语义与既有
    `analyze_label` 完全一致；输入或校验失败**抛异常、不返回报告**。
    """
    started = perf_counter()
    if type(try_downscale) is not bool:
        raise label_module.LabelAnalysisError("invalid_decoder_config", "try_downscale 必须是布尔值")

    # 关联层自己读一次（供质量测量），随后由 analyze_label 内部再读一次。
    bgr, metadata = images.load_normalized_image(path)
    qr_report = label_module.analyze_label(
        path, roi, expected_file, truth_source, try_downscale=try_downscale
    )

    # --- 读取一致性（契约 1、2）：逐字段比对，任一不一致即拒绝关联 -------------
    quality_read = _read_fields(metadata["source"], metadata["preprocessing"])
    qr_read = _read_fields(qr_report["source"], qr_report["preprocessing"])
    for name in CHECKED_FIELDS:
        if quality_read[name] != qr_read[name]:
            raise QualityQrAssociationError(
                "source_changed_between_reads",
                f"两次读取的 {name} 不一致：质量读取 {quality_read[name]!r}，"
                f"QR 读取 {qr_read[name]!r}",
            )
    read_consistency = {
        "qr_read_sha256": qr_read["sha256"],
        "quality_read_sha256": quality_read["sha256"],
        "consistent": True,
        "checked_fields": list(CHECKED_FIELDS),
    }

    # --- 测量记录（契约 3、4、7）：整图与 ROI 分别测量，每区域恰一条 -----------
    _, full_region = label_module.select_region(bgr)
    planned = [("full_image", None, dict(full_region))]
    if roi is not None:
        _, roi_region = label_module.select_region(bgr, roi)
        planned.append(("roi", roi, dict(roi_region)))

    measurements = []
    for measurement_id, roi_argument, region in planned:
        quality, quality_error, duration = _measure(bgr, roi_argument)
        measurements.append({
            "measurement_id": measurement_id, "region": region, "basis": BASIS,
            "quality": quality, "quality_error": quality_error,
            "duration_seconds": duration,
        })

    # --- 关联表（契约 3）：每个 (region, profile) 恰一条，引用测量记录 ----------
    associations = []
    for attempt_index, attempt in enumerate(qr_report["attempts"]):
        attempt_region = attempt["region"]
        associations.append({
            "measurement_id": attempt_region["kind"],
            "region": {"kind": attempt_region["kind"], "x": attempt_region["x"],
                       "y": attempt_region["y"], "width": attempt_region["width"],
                       "height": attempt_region["height"]},
            "profile": attempt["profile"], "attempt_index": attempt_index,
            "decode_status": attempt["decode"]["status"],
            "truth_status": attempt["truth_check"]["status"],
        })

    # --- 三类耗时（契约 9）：分别定义，互不替代 --------------------------------
    decode_seconds = sum(attempt["decode"]["duration_seconds"]
                         for attempt in qr_report["attempts"])
    quality_seconds = sum(measurement["duration_seconds"] for measurement in measurements)

    # --- 状态与错误（契约 5、6、8）--------------------------------------------
    measurement_failed = any(m["quality_error"] is not None for m in measurements)
    status = ("completed" if not measurement_failed and qr_report["status"] == "completed"
              else "completed_with_errors")

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "association_id": uuid4().hex,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "timings": {"decode_seconds": decode_seconds,
                    "quality_seconds": quality_seconds},
        "provenance": {"implementation_version": IMPLEMENTATION_VERSION,
                       "source_sha256": _source_sha256(),
                       "quality_module_version": None,
                       "runtime": _runtime_versions()},
        "read_consistency": read_consistency,
        "requested_roi": list(roi) if roi is not None else None,
        "measurements": measurements,
        "associations": associations,
        "qr_report": qr_report,
        # 首版没有可证伪的关联层限制事实，恒为空列表（契约 5、6.11）。
        "warnings": [],
    }
    # 包含来源摘要、版本读取及报告组装；计时结束后立即返回。
    report["timings"]["total_seconds"] = perf_counter() - started
    return report
