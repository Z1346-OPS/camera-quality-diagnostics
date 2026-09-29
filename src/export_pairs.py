"""把同一运行批次内配对的质量与颜色记录导出为 JSON。"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from uuid import UUID

try:
    from .check_reports import COLOR_PATH, QUALITY_PATH, reconcile_reports
except ImportError:  # 允许从项目根目录直接运行本文件
    from check_reports import COLOR_PATH, QUALITY_PATH, reconcile_reports


def _selected_rows(path: Path, run_id: str, numeric_fields: tuple[str, ...]) -> dict[int, dict]:
    """关联键已由 reconcile_reports 校验；此处转换选中批次的指标。"""
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as report:
        for row in csv.DictReader(report, strict=True):
            if row["run_id"] != run_id:
                continue
            frame_count = int(row["frame_count"])
            values = {"recorded_at": row["recorded_at"]}
            for field in numeric_fields:
                try:
                    number = float(row[field])
                except ValueError as error:
                    raise ValueError(f"{path}: 帧 {frame_count} 的 {field} 不是数字") from error
                if not math.isfinite(number):
                    raise ValueError(f"{path}: 帧 {frame_count} 的 {field} 不是有限数字")
                values[field] = number
            if "scene_label" in row:
                values["scene_label"] = row["scene_label"]
            rows[frame_count] = values
    return rows


def export_run(
    run_id: str, quality_path: Path = QUALITY_PATH, color_path: Path = COLOR_PATH,
    output_path: Path | None = None,
) -> Path:
    """先校验并构造完整 JSON，再创建新文件；绝不覆盖已有结果。"""
    try:
        if not isinstance(run_id, str) or UUID(hex=run_id).hex != run_id:
            raise ValueError
    except ValueError as error:
        raise ValueError("run_id 必须是 32 位小写十六进制 UUID") from error
    matched, quality_only, color_only = reconcile_reports(quality_path, color_path)
    selected = sorted(frame for batch, frame in matched if batch == run_id)
    if any(batch == run_id for batch, _ in quality_only | color_only):
        raise ValueError("所选批次存在未配对记录，未生成 JSON")
    if not selected:
        raise ValueError("所选批次没有配对记录，未生成 JSON")
    quality = _selected_rows(Path(quality_path), run_id, (
        "brightness", "dark_ratio", "bright_ratio", "sharpness", "contrast",
    ))
    color = _selected_rows(Path(color_path), run_id, (
        "blue_mean", "green_mean", "red_mean", "channel_spread",
    ))
    payload = {
        "schema_version": 1, "run_id": run_id, "record_count": len(selected),
        "frames": [
            {"frame_count": frame, "quality": quality[frame], "color": color[frame]}
            for frame in selected
        ],
    }
    target = Path(output_path) if output_path is not None else (
        QUALITY_PATH.parent / f"camera_pair_{run_id}.json"
    )
    with target.open("x", encoding="utf-8") as result:
        json.dump(payload, result, ensure_ascii=False, indent=2, allow_nan=False)
        result.write("\n")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="要导出的 32 位小写十六进制批次 ID")
    args = parser.parse_args(argv)
    try:
        result = export_run(args.run_id)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"导出失败: {error}", file=sys.stderr)
        return 1
    print(f"已导出: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
