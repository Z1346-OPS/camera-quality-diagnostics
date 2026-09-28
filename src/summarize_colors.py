"""只读汇总带场景标签的颜色报告，不判断偏色故障。"""

import argparse
import csv
import math
import sys
from pathlib import Path
from uuid import UUID


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
RUN_FIELDS = EXPECTED_FIELDS + ["run_id"]


def summarize_color_report(report_path: Path = DEFAULT_COLOR_REPORT) -> dict:
    """按场景统计已保存的通道差；遇到坏数据时失败，不返回部分结果。"""
    groups = {}
    with Path(report_path).open(newline="", encoding="utf-8-sig") as report:
        reader = csv.DictReader(report, strict=True)
        if reader.fieldnames not in (EXPECTED_FIELDS, RUN_FIELDS):
            raise ValueError("表头不匹配，请使用带标签或带批次的颜色报告")
        has_run_id = reader.fieldnames == RUN_FIELDS
        for row in reader:
            label = row["scene_label"]
            if None in row or any(value is None or value == "" for value in row.values()):
                raise ValueError(f"第 {reader.line_num} 行字段数量错误或字段为空")
            if label not in SCENES:
                raise ValueError(f"第 {reader.line_num} 行场景标签无效")
            run_id = row["run_id"] if has_run_id else None
            if has_run_id:
                try:
                    if UUID(hex=run_id).hex != run_id:
                        raise ValueError
                except ValueError as error:
                    raise ValueError(f"第 {reader.line_num} 行 run_id 格式无效") from error
            try:
                spread = float(row["channel_spread"])
            except ValueError as error:
                raise ValueError(f"第 {reader.line_num} 行通道差不是数字") from error
            if not math.isfinite(spread) or not 0 <= spread <= 255:
                raise ValueError(f"第 {reader.line_num} 行通道差必须是 0 到 255 的有限数值")
            key = (run_id, label) if has_run_id else label
            group = groups.setdefault(key, {"count": 0, "sum": 0.0, "min": spread, "max": spread})
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
    print("范围：文件内全部记录；带 run_id 的报告按批次和场景分组。")
    if not summary:
        print("暂无记录，请先运行摄像头程序并按 s 保存。")
        return 0
    has_run_id = isinstance(next(iter(summary)), tuple)
    print(("run_id | " if has_run_id else "") + "场景 | 记录数 | 通道差均值 | 最小值 | 最大值")
    for key, group in summary.items():
        run_id, label = key if has_run_id else (None, key)
        prefix = f"{run_id} | " if has_run_id else ""
        print(f"{prefix}{SCENES[label]} ({label}) | {group['count']} | "
              f"{group['mean']:.1f} | {group['min']:.1f} | {group['max']:.1f}")
    print("注意：统计基于已保存的一位小数通道差；少量记录不能用于标定或故障判定。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
