"""只读比较同一批次中首次与恢复白纸场景的指标均值。"""

import argparse
import sys
from pathlib import Path

try:
    from .summarize_pairs import DISPLAY, summarize_pairs
except ImportError:  # 允许从项目根目录直接运行本文件
    from summarize_pairs import DISPLAY, summarize_pairs


def compare_white(path: Path) -> dict:
    """返回恢复白纸减首次白纸的均值差，不判断变化原因。"""
    groups = summarize_pairs(path)
    if "white_paper" not in groups or "white_restored" not in groups:
        raise ValueError("需要同时有 white_paper 和 white_restored 记录")
    before, after = groups["white_paper"], groups["white_restored"]
    return {
        "before_count": before["count"], "after_count": after["count"],
        "metrics": {
            field: {"before": before["metrics"][field]["mean"],
                    "after": after["metrics"][field]["mean"],
                    "difference": after["metrics"][field]["mean"] - before["metrics"][field]["mean"]}
            for field in DISPLAY
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="同一批次的配对 JSON 路径")
    args = parser.parse_args(argv)
    try:
        result = compare_white(args.report)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"比较失败: {error}", file=sys.stderr)
        return 1
    print(f"首次白纸 {result['before_count']} 条；恢复白纸 {result['after_count']} 条")
    names = {"brightness": "亮度", "sharpness": "清晰度",
             "contrast": "对比度", "channel_spread": "通道差"}
    for field, values in result["metrics"].items():
        print(f"{names[field]}: {values['before']:.1f} → {values['after']:.1f} "
              f"(恢复减首次 {values['difference']:+.1f})")
    print("注意：场景标签由人手动选择；差值只描述本批次样本，不代表故障或恢复效果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
