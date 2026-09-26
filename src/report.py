"""将单帧图像质量指标追加保存为 CSV 报告。"""

import csv
from datetime import datetime
from pathlib import Path


def append_color_record(
    frame_count: int,
    blue_mean: float,
    green_mean: float,
    red_mean: float,
    report_path: Path | None = None,
    *,
    scene_label: str | None = None,
) -> Path:
    """追加颜色通道均值，通道差由未舍入的均值计算。"""
    if scene_label is not None and scene_label not in (
        "unspecified", "white_paper", "colored_object", "white_restored"
    ):
        raise ValueError("不支持的场景标签")
    if report_path is None:
        filename = "camera_colors.csv" if scene_label is None else "camera_colors_labeled.csv"
        report_path = Path(__file__).resolve().parents[1] / "data" / "reports" / filename
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not report_path.exists() or report_path.stat().st_size == 0
    row = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "frame_count": frame_count,
        "blue_mean": f"{blue_mean:.1f}",
        "green_mean": f"{green_mean:.1f}",
        "red_mean": f"{red_mean:.1f}",
        "channel_spread": f"{max(blue_mean, green_mean, red_mean) - min(blue_mean, green_mean, red_mean):.1f}",
    }
    if scene_label is not None:
        row["scene_label"] = scene_label
    if not needs_header:
        with report_path.open(newline="", encoding="utf-8-sig") as csv_file:
            if next(csv.reader(csv_file), None) != list(row):
                raise ValueError("颜色报告表头不匹配，请使用另一份报告文件")
    with report_path.open("a", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=row.keys())
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    return report_path


DEFAULT_REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "reports" / "camera_quality.csv"
)
DEFAULT_EVENT_REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "reports" / "camera_events.csv"
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


def append_camera_event(
    frame_count: int,
    event: str,
    message: str,
    report_path: Path = DEFAULT_EVENT_REPORT_PATH,
) -> Path:
    """把摄像头事件追加到独立 CSV，并返回报告路径。"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not report_path.exists() or report_path.stat().st_size == 0

    row = {
        "recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "frame_count": frame_count,
        "event": event,
        "message": message,
    }

    with report_path.open("a", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=row.keys())
        if needs_header:
            writer.writeheader()
        writer.writerow(row)

    return report_path
