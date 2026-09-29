"""只读汇总多个批次的白纸前后差值；不生成判定阈值。"""

import argparse
import json
import sys
from pathlib import Path

try:
    from .compare_white import compare_white
    from .summarize_pairs import DISPLAY
except ImportError:  # 允许从项目根目录直接运行本文件
    from compare_white import compare_white
    from summarize_pairs import DISPLAY


NAMES = {"brightness": "亮度", "sharpness": "清晰度",
         "contrast": "对比度", "channel_spread": "通道差"}


def summarize_white_runs(paths: list[Path]) -> dict:
    """每个 run_id 只计一次，跨批次范围以批次差值为单位。"""
    if not paths:
        raise ValueError("至少提供一个批次 JSON")
    runs = {}
    for path in paths:
        path = Path(path)
        comparison = compare_white(path)
        with path.open(encoding="utf-8") as report:
            run_id = json.load(report)["run_id"]
        if run_id in runs:
            raise ValueError(f"重复的 run_id: {run_id}")
        runs[run_id] = comparison
    ranges = None
    if len(runs) >= 2:
        ranges = {
            field: {
                "min": min(run["metrics"][field]["difference"] for run in runs.values()),
                "max": max(run["metrics"][field]["difference"] for run in runs.values()),
            }
            for field in DISPLAY
        }
    return {"run_count": len(runs), "runs": runs, "ranges": ranges}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="逐个列出要比较的批次 JSON")
    args = parser.parse_args(argv)
    try:
        result = summarize_white_runs(args.reports)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"跨批次汇总失败: {error}", file=sys.stderr)
        return 1
    for run_id, run in result["runs"].items():
        print(f"run_id={run_id}：首次白纸 {run['before_count']} 条，恢复白纸 {run['after_count']} 条")
        for field in DISPLAY:
            print(f"  {NAMES[field]}差值: {run['metrics'][field]['difference']:+.1f}")
    if result["ranges"] is None:
        print("目前只有 1 个完整批次，尚不能给出跨批次范围。")
    else:
        print(f"跨 {result['run_count']} 个批次的差值范围（每批次计一次）：")
        for field, values in result["ranges"].items():
            print(f"  {NAMES[field]}: {values['min']:+.1f} 到 {values['max']:+.1f}")
    print("注意：范围仅描述已输入批次；拍摄条件需可比，不能直接用作合格阈值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
