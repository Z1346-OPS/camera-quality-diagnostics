"""将单帧图像质量指标追加保存为 CSV 报告。"""

import csv
from datetime import datetime
from pathlib import Path


DEFAULT_REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "reports" / "camera_quality.csv"
)


def append_quality_record(
    frame_count: int,
    brightness: float,
    dark_ratio: float,
    bright_ratio: float,
    sharpness: float,
    contrast: float,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> Path:
    """把当前帧的质量指标追加到 CSV，并返回报告路径。"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not report_path.exists() or report_path.stat().st_size == 0

    row = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "frame_count": frame_count,
        "brightness": f"{brightness:.1f}",
        "dark_ratio": f"{dark_ratio:.1f}",
        "bright_ratio": f"{bright_ratio:.1f}",
        "sharpness": f"{sharpness:.1f}",
        "contrast": f"{contrast:.1f}",
    }

    with report_path.open("a", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=row.keys())
        if needs_header:
            writer.writeheader()
        writer.writerow(row)

    return report_path
