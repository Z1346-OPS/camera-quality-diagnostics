"""只读汇总一个批次 JSON 中各场景的指标，不生成诊断结论。"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from uuid import UUID

try:
    from .summarize_colors import SCENES
except ImportError:  # 允许从项目根目录直接运行本文件
    from summarize_colors import SCENES


FIELDS = {
    "quality": ("brightness", "dark_ratio", "bright_ratio", "sharpness", "contrast"),
    "color": ("blue_mean", "green_mean", "red_mean", "channel_spread"),
}
DISPLAY = ("brightness", "sharpness", "contrast", "channel_spread")
MAX_VALUES = {"brightness": 255, "dark_ratio": 100, "bright_ratio": 100,
              "blue_mean": 255, "green_mean": 255, "red_mean": 255,
              "channel_spread": 255}


def summarize_pairs(path: Path) -> dict:
    """校验导出格式，按场景返回样本数和描述性统计。"""
    with Path(path).open(encoding="utf-8") as report:
        data = json.load(report)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("不支持的 JSON 格式版本")
    run_id = data.get("run_id")
    try:
        if not isinstance(run_id, str) or UUID(hex=run_id).hex != run_id:
            raise ValueError
    except ValueError as error:
        raise ValueError("run_id 无效") from error
    frames = data.get("frames")
    if (not isinstance(frames, list) or not frames or
            type(data.get("record_count")) is not int or data["record_count"] != len(frames)):
        raise ValueError("记录数与帧列表不一致，或没有记录")
    groups, seen = {}, set()
    for row in frames:
        if not isinstance(row, dict):
            raise ValueError("帧记录格式错误")
        frame = row.get("frame_count")
        if type(frame) is not int or frame < 1 or frame in seen:
            raise ValueError("帧号无效或重复")
        seen.add(frame)
        color = row.get("color")
        label = color.get("scene_label") if isinstance(color, dict) else None
        if not isinstance(label, str) or label not in SCENES:
            raise ValueError(f"帧 {frame} 的场景标签无效")
        values = {}
        for section, fields in FIELDS.items():
            source = row.get(section)
            if not isinstance(source, dict) or not isinstance(source.get("recorded_at"), str) or not source["recorded_at"]:
                raise ValueError(f"帧 {frame} 的 {section} 记录不完整")
            for field in fields:
                value = source.get(field)
                try:
                    finite_number = type(value) in (int, float) and math.isfinite(value)
                except OverflowError:
                    finite_number = False
                if not finite_number:
                    raise ValueError(f"帧 {frame} 的 {field} 不是有限数字")
                if value < 0 or (field in MAX_VALUES and value > MAX_VALUES[field]):
                    raise ValueError(f"帧 {frame} 的 {field} 超出合理范围")
                values[field] = value
        groups.setdefault(label, []).append(values)
    def stats(rows, field):
        try:
            mean = statistics.fmean(row[field] for row in rows)
        except OverflowError as error:
            raise ValueError(f"{field} 数值过大，无法汇总") from error
        return {"mean": mean, "min": min(row[field] for row in rows),
                "max": max(row[field] for row in rows)}

    return {label: {"count": len(rows), "metrics": {
        field: stats(rows, field) for field in DISPLAY
    }} for label, rows in groups.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="由 export_pairs.py 生成的 JSON 路径")
    args = parser.parse_args(argv)
    try:
        groups = summarize_pairs(args.report)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"汇总失败: {error}", file=sys.stderr)
        return 1
    names = {"brightness": "亮度", "sharpness": "清晰度", "contrast": "对比度", "channel_spread": "通道差"}
    for label, group in groups.items():
        print(f"{SCENES[label]} ({label}): {group['count']} 条")
        for field, stats in group["metrics"].items():
            print(f"  {names[field]}: 均值 {stats['mean']:.1f}，范围 {stats['min']:.1f}–{stats['max']:.1f}")
    print("注意：这只是当前批次的描述性统计；少量样本不能用于设定阈值或判定故障。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
