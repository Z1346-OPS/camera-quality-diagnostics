"""用留证 PNG 重新计算单帧质量指标并与 CSV 核对。"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    from .camera_test import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from .check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
    from .metrics import (
        calculate_contrast, calculate_exposure_ratios,
        calculate_mean_brightness, calculate_sharpness,
    )
except ImportError:
    from camera_test import BRIGHT_THRESHOLD, DARK_THRESHOLD
    from check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
    from metrics import (
        calculate_contrast, calculate_exposure_ratios,
        calculate_mean_brightness, calculate_sharpness,
    )


def compare_frame_metrics(
    run_id: str, frame_count: int, report_dir: Path = REPORT_DIR,
    quality_path: Path = QUALITY_PATH, color_path: Path = COLOR_PATH,
) -> dict[str, tuple[str, str]]:
    """返回各指标的 (CSV 值, PNG 重算值)，两者均按一位小数表示。"""
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError("帧号必须是正整数")
    matched, quality_only, color_only = reconcile_reports(quality_path, color_path, run_id)
    if quality_only or color_only:
        raise ValueError("质量与颜色 CSV 存在未配对记录")
    if (run_id, frame_count) not in matched:
        raise ValueError("所选批次没有该帧的配对 CSV 记录")
    with Path(quality_path).open(newline="", encoding="utf-8-sig") as source:
        row = next(
            item for item in csv.DictReader(source)
            if item["run_id"] == run_id and int(item["frame_count"]) == frame_count
        )
    image_path = Path(report_dir) / f"camera_frame_{run_id}_{frame_count}.png"
    contents = image_path.read_bytes()
    if not contents.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("留证图片不是有效 PNG")
    frame = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if frame is None or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("留证图片无法解码为 8 位 BGR 三通道图")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark_ratio, bright_ratio = calculate_exposure_ratios(
        gray, DARK_THRESHOLD, BRIGHT_THRESHOLD
    )
    calculated = {
        "brightness": calculate_mean_brightness(gray),
        "dark_ratio": dark_ratio,
        "bright_ratio": bright_ratio,
        "sharpness": calculate_sharpness(gray),
        "contrast": calculate_contrast(gray),
    }
    return {name: (row[name], f"{value:.1f}") for name, value in calculated.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--frame", required=True, type=int)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--quality", type=Path, default=QUALITY_PATH)
    parser.add_argument("--color", type=Path, default=COLOR_PATH)
    args = parser.parse_args(argv)
    try:
        compared = compare_frame_metrics(
            args.run_id, args.frame, args.report_dir, args.quality, args.color
        )
    except (OSError, UnicodeError, ValueError, csv.Error, cv2.error) as error:
        print(f"检查失败: {error}", file=sys.stderr)
        return 2
    different = False
    for name, (saved, recalculated) in compared.items():
        same = saved == recalculated
        different |= not same
        print(f"{name}: CSV={saved} PNG重算={recalculated} {'一致' if same else '不同'}")
    if different:
        print("指标不一致；请核对图片、CSV、算法版本及阈值，不能直接判定原因。")
        return 1
    print("5 项指标均与当前算法的一位小数结果一致；不证明场景标签正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
