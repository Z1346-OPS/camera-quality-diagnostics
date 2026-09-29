"""只读检查配对报告是否符合三场景采集顺序。"""

import argparse
import json
import sys
from pathlib import Path

try:
    from .summarize_pairs import summarize_pairs
except ImportError:  # 允许从项目根目录直接运行本文件
    from summarize_pairs import summarize_pairs


EXPECTED = ("white_paper", "colored_object", "white_restored")


def validate_capture(path: Path) -> tuple[str, tuple[str, ...]]:
    """检查报告格式与按帧号排列的标签；不验证镜头前的真实物体。"""
    summarize_pairs(path)  # 复用已有的格式、帧号和指标校验
    with Path(path).open(encoding="utf-8") as report:
        data = json.load(report)
    frames = sorted(data["frames"], key=lambda row: row["frame_count"])
    labels = tuple(row["color"]["scene_label"] for row in frames)
    if labels != EXPECTED:
        raise ValueError(f"标签顺序不符：期望 {EXPECTED}，实际 {labels}")
    return data["run_id"], labels


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="由 export_pairs.py 生成的批次 JSON")
    args = parser.parse_args(argv)
    try:
        run_id, labels = validate_capture(args.report)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"采集流程检查失败: {error}", file=sys.stderr)
        return 1
    print(f"批次 {run_id}：标签顺序符合三场景流程（{', '.join(labels)}）。")
    print("注意：只能核对记录的标签，不能确认画面内容或拍摄条件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
