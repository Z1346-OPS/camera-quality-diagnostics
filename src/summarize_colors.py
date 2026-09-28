"""只读汇总带场景标签的颜色报告，不判断偏色故障。"""

import argparse
import csv
import math
import sys
from pathlib import Path


DEFAULT_COLOR_REPORT = (
    Path(__file__).resolve().parents[1] / "data" / "reports" / "camera_colors_labeled.csv"
)
SCENES = {
    "unspecified": "未指定",
    "white_paper": "白纸",
    "colored_object": "彩色物体",
    "white_restored": "恢复白纸",
}
EXPECTED_FIELDS = [
    "recorded_at", "frame_count", "blue_mean", "green_mean",
    "red_mean", "channel_spread", "scene_label",
]


def summarize_color_report(report_path: Path = DEFAULT_COLOR_REPORT) -> dict:
    """按场景统计已保存的通道差；遇到坏数据时失败，不返回部分结果。"""
    groups = {}
    with Path(report_path).open(newline="", encoding="utf-8-sig") as report:
        reader = csv.DictReader(report, strict=True)
        if reader.fieldnames != EXPECTED_FIELDS:
            raise ValueError("表头不匹配，请使用 camera_colors_labeled.csv 带标签报告")
        for row in reader:
            label = row["scene_label"]
            if None in row or any(value is None or value == "" for value in row.values()):
                raise ValueError(f"第 {reader.line_num} 行字段数量错误或字段为空")
            if label not in SCENES:
                raise ValueError(f"第 {reader.line_num} 行场景标签无效")
            try:
                spread = float(row["channel_spread"])
            except ValueError as error:
                raise ValueError(f"第 {reader.line_num} 行通道差不是数字") from error
            if not math.isfinite(spread) or not 0 <= spread <= 255:
                raise ValueError(f"第 {reader.line_num} 行通道差必须是 0 到 255 的有限数值")
            group = groups.setdefault(label, {"count": 0, "sum": 0.0, "min": spread, "max": spread})
            group["count"] += 1
            group["sum"] += spread
            group["min"] = min(group["min"], spread)
            group["max"] = max(group["max"], spread)
    return {
        label: {"count": group["count"], "mean": group["sum"] / group["count"],
                "min": group["min"], "max": group["max"]}
        for label, group in groups.items()
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=DEFAULT_COLOR_REPORT)
    args = parser.parse_args(argv)
    try:
        summary = summarize_color_report(args.report)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"汇总失败: {error}", file=sys.stderr)
        return 1
    print(f"读取报告: {args.report.resolve()}")
    print("范围：文件内全部记录，可能包含多次运行。")
    if not summary:
        print("暂无记录，请先运行摄像头程序并按 s 保存。")
        return 0
    print("场景 | 记录数 | 通道差均值 | 最小值 | 最大值")
    for label, name in SCENES.items():
        if label in summary:
            group = summary[label]
            print(f"{name} ({label}) | {group['count']} | {group['mean']:.1f} | "
                  f"{group['min']:.1f} | {group['max']:.1f}")
    print("注意：统计基于已保存的一位小数通道差；少量记录不能用于标定或故障判定。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
