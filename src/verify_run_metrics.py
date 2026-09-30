"""只读复核一个批次内所有已保存帧的 PNG 与质量 CSV 指标。"""

import argparse
import csv
import sys
from pathlib import Path

import cv2

try:
    from .check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
    from .verify_frame_metrics import compare_frame_metrics
except ImportError:
    from check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
    from verify_frame_metrics import compare_frame_metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="要复核的运行批次")
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--quality", type=Path, default=QUALITY_PATH)
    parser.add_argument("--color", type=Path, default=COLOR_PATH)
    args = parser.parse_args(argv)
    try:
        matched, quality_only, color_only = reconcile_reports(
            args.quality, args.color, args.run_id
        )
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"批次检查失败: {error}", file=sys.stderr)
        return 2
    if quality_only or color_only:
        print("批次检查失败: 质量与颜色 CSV 有未配对记录", file=sys.stderr)
        return 2

    counts = {"一致": 0, "数值不同": 0, "无法复核": 0}
    for _, frame_count in sorted(matched):
        try:
            compared = compare_frame_metrics(
                args.run_id, frame_count, args.report_dir, args.quality, args.color
            )
        except (OSError, UnicodeError, ValueError, csv.Error, cv2.error) as error:
            counts["无法复核"] += 1
            print(f"帧 {frame_count}: 无法复核（{error}）")
            continue
        different = [name for name, (saved, recalculated) in compared.items()
                     if saved != recalculated]
        if different:
            counts["数值不同"] += 1
            print(f"帧 {frame_count}: 数值不同（{', '.join(different)}）")
        else:
            counts["一致"] += 1
            print(f"帧 {frame_count}: 5 项一致")
    print(f"批次 {args.run_id}: 共 {len(matched)} 帧；"
          f"一致 {counts['一致']}；数值不同 {counts['数值不同']}；"
          f"无法复核 {counts['无法复核']}")
    if counts["数值不同"] or counts["无法复核"]:
        print("批次复核未全部通过；不能仅凭本结果判断相机故障或场景标签。")
        return 1
    print("本批次保存帧均与当前指标算法一致；不证明标签或拍摄条件正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
