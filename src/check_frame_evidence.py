"""只读核对指定批次的 CSV 记录是否有可解码的原始帧 PNG。"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    from .check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
except ImportError:
    from check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports


def check_frame_evidence(
    run_id: str, report_dir: Path = REPORT_DIR,
    quality_path: Path = QUALITY_PATH, color_path: Path = COLOR_PATH,
) -> dict[str, list[int]]:
    """检查配对 CSV 每一帧的 PNG；不显示画面，也不修改文件。"""
    matched, quality_only, color_only = reconcile_reports(quality_path, color_path, run_id)
    if quality_only or color_only:
        raise ValueError("质量与颜色 CSV 存在未配对记录，请先核对 CSV")
    result = {name: [] for name in ("valid", "missing", "empty", "undecodable")}
    for _, frame_count in sorted(matched):
        path = Path(report_dir) / f"camera_frame_{run_id}_{frame_count}.png"
        if not path.is_file():
            result["missing"].append(frame_count)
            continue
        contents = path.read_bytes()
        if not contents:
            result["empty"].append(frame_count)
        elif not contents.startswith(b"\x89PNG\r\n\x1a\n") or cv2.imdecode(
            np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_UNCHANGED
        ) is None:
            result["undecodable"].append(frame_count)
        else:
            result["valid"].append(frame_count)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="要核对的 32 位小写十六进制批次 ID")
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--quality", type=Path, default=QUALITY_PATH)
    parser.add_argument("--color", type=Path, default=COLOR_PATH)
    args = parser.parse_args(argv)
    try:
        result = check_frame_evidence(args.run_id, args.report_dir, args.quality, args.color)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"检查失败: {error}", file=sys.stderr)
        return 2
    print(f"批次: {args.run_id}")
    for name, label in (("valid", "可解码"), ("missing", "缺失"),
                        ("empty", "空文件"), ("undecodable", "无法解码")):
        frames = result[name]
        print(f"{label}: {len(frames)} 帧" + (f"，帧号 {frames}" if frames else ""))
    if any(result[name] for name in ("missing", "empty", "undecodable")):
        print("留证不完整；旧批次可能没有启用 --save-frames，不能仅凭此判断保存故障。")
        return 1
    print("配对 CSV 中的每帧均有可解码 PNG；这不证明画面场景或内容正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
