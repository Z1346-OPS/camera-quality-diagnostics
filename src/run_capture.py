"""定时采集命令行入口（业务阶段 4.4）。

无预览：只按间隔采样、测量、保存并发布 `capture_task.json`。

运行方式（在项目根目录）：

    .\\.venv\\Scripts\\python.exe -X utf8 src\\run_capture.py ^
        --camera-index 0 --duration 30 --interval 5 ^
        --output-dir data\\reports\\timed-capture\\trial-001
"""

from __future__ import annotations

import argparse
import sys

import cv2

if __package__:
    from .capture_task import REPORT_NAME, CaptureConfig, CaptureRunner, CaptureTaskError
else:
    from capture_task import REPORT_NAME, CaptureConfig, CaptureRunner, CaptureTaskError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="定时采集与间隔留证（无预览）",
    )
    parser.add_argument(
        "--camera-index", type=int, default=0,
        help="摄像头编号，非负整数（默认 0）",
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="采集总时长（整数秒，1～3600，默认 30）",
    )
    parser.add_argument(
        "--interval", type=int, default=5,
        help="采样间隔（整数秒，1～3600，默认 5）",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="本次任务的新目录，必须不存在",
    )
    return parser


def _print_failure(prefix: str, error: BaseException) -> None:
    """输出主错误，并把附加错误（阶段 / 类型 / 信息）一并暴露到 stderr。"""
    print(f"{prefix}: {error}", file=sys.stderr)
    for note in getattr(error, "__notes__", ()) or ():
        print(f"附加错误: {note}", file=sys.stderr)


def main(argv=None, *, camera_factory=None, clock=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = CaptureConfig(
            output_dir=args.output_dir,
            camera_index=args.camera_index,
            duration_seconds=args.duration,
            interval_seconds=args.interval,
        )
    except CaptureTaskError as error:
        print(f"参数错误: {error}", file=sys.stderr)
        return 2

    runner = CaptureRunner(config, camera_factory=camera_factory, clock=clock)
    try:
        report = runner.run()
    except KeyboardInterrupt as error:
        _print_failure("已收到中断，采集结束", error)
        return 130
    except CaptureTaskError as error:
        _print_failure("采集失败", error)
        return 2
    except (OSError, ValueError, cv2.error) as error:
        _print_failure("采集失败", error)
        return 2

    counts = report["counts"]
    print(
        f"采集完成：状态 {report['status']}，"
        f"完整样本 {counts['samples_completed']}/{counts['sample_attempts']}，"
        f"读取 {counts['read_attempts']} 次，有效帧 {counts['valid_frames']}。"
    )
    print(f"任务报告: {config.output_dir / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
