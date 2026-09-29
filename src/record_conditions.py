"""为已保存且配对的摄像头批次记录人工拍摄条件。"""

import argparse
import csv
from datetime import datetime
import json
import sys
from pathlib import Path

try:
    from .check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports
except ImportError:  # 允许从项目根目录直接运行本文件
    from check_reports import COLOR_PATH, QUALITY_PATH, REPORT_DIR, reconcile_reports


def record_conditions(
    run_id: str, note: str,
    quality_path: Path = QUALITY_PATH, color_path: Path = COLOR_PATH,
    output_path: Path | None = None,
) -> Path:
    """校验批次后新建备注 JSON，不覆盖报告或已有备注。"""
    if not isinstance(note, str) or not note.strip():
        raise ValueError("条件备注不能为空")
    _matched, quality_only, color_only = reconcile_reports(
        quality_path, color_path, run_id=run_id
    )
    if quality_only or color_only:
        raise ValueError("所选批次存在未配对记录，未保存条件备注")
    target = Path(output_path) if output_path is not None else (
        REPORT_DIR / f"camera_conditions_{run_id}.json"
    )
    payload = {
        "schema_version": 1, "run_id": run_id,
        "source": "operator_note",
        "note_recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "conditions_note": note.strip(),
    }
    with target.open("x", encoding="utf-8") as result:
        json.dump(payload, result, ensure_ascii=False, indent=2)
        result.write("\n")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="已保存的 32 位小写十六进制批次 ID")
    parser.add_argument("--note", required=True, help="操作者记录的实际条件；未知就写未知")
    args = parser.parse_args(argv)
    try:
        target = record_conditions(args.run_id, args.note)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"条件记录失败: {error}", file=sys.stderr)
        return 1
    print(f"已保存条件备注: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
