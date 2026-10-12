"""Command-line local evaluation; results are exclusively created, never replaced."""

import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .label_evaluation import EvaluationError, evaluate_manifest
else:
    from label_evaluation import EvaluationError, evaluate_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="按冻结样本清单评测 QR 基线与降采样搜索；原图只读")
    parser.add_argument("manifest", type=Path, help="UTF-8 JSON 清单；图片/答案路径相对清单目录")
    parser.add_argument("--split", choices=("development", "test"))
    parser.add_argument("--output", type=Path, help="新建 JSON 报告，不覆盖历史结果")
    args = parser.parse_args(argv)
    try:
        if args.output is not None and args.output.exists():
            raise FileExistsError("结果文件已存在，请换新文件名")
        report = evaluate_manifest(args.manifest, args.split)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
    except (EvaluationError, OSError, MemoryError) as error:
        code = getattr(error, "code", "output_exists" if isinstance(error, FileExistsError) else
                       "resource_exhausted" if isinstance(error, MemoryError) else "evaluation_io_failed")
        print(f"评测失败 [{code}]: {error}", file=sys.stderr)
        return 2
    print(rendered)
    return 2 if report["status"] == "completed_with_errors" else 0


if __name__ == "__main__":
    sys.exit(main())
