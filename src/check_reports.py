"""只读核对质量与颜色报告的批次和帧号。"""

import argparse
import csv
import sys
from pathlib import Path
from uuid import UUID


REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
QUALITY_PATH = REPORT_DIR / "camera_quality_runs.csv"
COLOR_PATH = REPORT_DIR / "camera_colors_runs.csv"
QUALITY_FIELDS = [
    "recorded_at", "frame_count", "brightness", "dark_ratio",
    "bright_ratio", "sharpness", "contrast", "run_id",
]
COLOR_FIELDS = [
    "recorded_at", "frame_count", "blue_mean", "green_mean", "red_mean",
    "channel_spread", "scene_label", "run_id",
]


def read_report_keys(path: Path, expected_fields: list[str]) -> set[tuple[str, int]]:
    """读取并校验关联键；重复键或坏行会报错。"""
    keys = set()
    with Path(path).open(newline="", encoding="utf-8-sig") as report:
        reader = csv.DictReader(report, strict=True)
        if reader.fieldnames != expected_fields:
            raise ValueError(f"{path}: 表头不匹配")
        for row in reader:
            if None in row or any(value is None or value == "" for value in row.values()):
                raise ValueError(f"{path}: 第 {reader.line_num} 行字段数量错误或字段为空")
            run_id = row["run_id"]
            try:
                if UUID(hex=run_id).hex != run_id:
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"{path}: 第 {reader.line_num} 行 run_id 格式无效") from error
            try:
                frame_count = int(row["frame_count"])
                if frame_count < 1 or str(frame_count) != row["frame_count"]:
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"{path}: 第 {reader.line_num} 行帧号无效") from error
            key = (run_id, frame_count)
            if key in keys:
                raise ValueError(f"{path}: 第 {reader.line_num} 行重复的 run_id 与帧号")
            keys.add(key)
    return keys


def reconcile_reports(
    quality_path: Path = QUALITY_PATH, color_path: Path = COLOR_PATH
) -> tuple[set, set, set]:
    """返回匹配、仅质量、仅颜色的键集合，不修改报告。"""
    quality_keys = read_report_keys(quality_path, QUALITY_FIELDS)
    color_keys = read_report_keys(color_path, COLOR_FIELDS)
    return (
        quality_keys & color_keys,
        quality_keys - color_keys,
        color_keys - quality_keys,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quality", nargs="?", type=Path, default=QUALITY_PATH)
    parser.add_argument("color", nargs="?", type=Path, default=COLOR_PATH)
    args = parser.parse_args(argv)
    try:
        matched, quality_only, color_only = reconcile_reports(args.quality, args.color)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"检查失败: {error}", file=sys.stderr)
        return 2
    print(f"匹配: {len(matched)} 条；仅质量: {len(quality_only)} 条；仅颜色: {len(color_only)} 条")
    for name, keys in (("仅质量", quality_only), ("仅颜色", color_only)):
        for run_id, frame_count in sorted(keys):
            print(f"{name}: run_id={run_id} frame_count={frame_count}")
    if quality_only or color_only:
        print("存在未配对记录；可能是历史格式启用时间不同或部分保存，单凭此结果不能判断原因。")
        return 1
    print("两份报告的 run_id 与帧号均一一对应。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
