"""定时采集命令行入口（T12）；流程测试全部注入模拟设备，不依赖真实摄像头。"""

import json

import numpy as np
import pytest

from src import capture_task, run_capture


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class ScriptedCamera:
    def __init__(self, clock, events) -> None:
        self.clock = clock
        self.events = list(events)
        self.index = 0
        self.released = 0

    def isOpened(self) -> bool:
        return True

    def getBackendName(self) -> str:
        return "DSHOW"

    def release(self) -> None:
        self.released += 1

    def read(self):
        elapsed, payload = self.events[self.index]
        self.index += 1
        self.clock.now = elapsed
        if isinstance(payload, BaseException):
            raise payload
        if payload is None:
            return False, None
        return True, payload


def make_frame(seed: int, shape=(6, 8, 3)) -> np.ndarray:
    height, width, channels = shape
    base = np.arange(height * width * channels).reshape(shape)
    return ((base + seed) % 256).astype(np.uint8)


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_capture.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--output-dir" in out and "--duration" in out and "--interval" in out


@pytest.mark.parametrize("argv", [
    [],                                                       # 缺少必填 output-dir
    ["--output-dir", "x", "--duration", "abc"],
    ["--output-dir", "x", "--duration", "1.5"],
    ["--output-dir", "x", "--interval", "two"],
    ["--output-dir", "x", "--camera-index", "1.0"],
    ["--unknown-flag"],
])
def test_cli_argparse_errors_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_capture.main(argv)
    assert excinfo.value.code == 2
    assert capsys.readouterr().err  # argparse 给出明确提示


@pytest.mark.parametrize("extra", [
    ["--duration", "0"],
    ["--duration", "3601"],
    ["--interval", "0"],
    ["--interval", "3601"],
    ["--camera-index", "-1"],
    ["--camera-index", str(2**31)],
    ["--duration", "121", "--interval", "1"],
])
def test_cli_range_validation_returns_2(tmp_path, capsys, extra):
    code = run_capture.main(["--output-dir", str(tmp_path / "out"), *extra])
    assert code == 2
    assert "参数错误" in capsys.readouterr().err


def test_cli_rejects_existing_output_dir_before_opening_camera(tmp_path, capsys):
    existing = tmp_path / "out"
    existing.mkdir()
    opened = []
    code = run_capture.main(
        ["--output-dir", str(existing)],
        camera_factory=lambda index: opened.append(index),
    )
    assert code == 2
    assert opened == []
    assert "参数错误" in capsys.readouterr().err


def test_cli_success_returns_0(tmp_path, capsys):
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, make_frame(1)), (1.5, make_frame(2)), (2.5, make_frame(3))])
    output_dir = tmp_path / "task"
    code = run_capture.main(
        ["--camera-index", "0", "--duration", "2", "--interval", "1",
         "--output-dir", str(output_dir)],
        camera_factory=lambda index: camera, clock=clock,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "采集完成" in out
    report = json.loads((output_dir / "capture_task.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["counts"]["samples_completed"] == 2
    assert camera.released == 1


def test_cli_defined_failure_returns_2(tmp_path, capsys):
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, None)])
    code = run_capture.main(
        ["--duration", "5", "--interval", "1", "--output-dir", str(tmp_path / "task")],
        camera_factory=lambda index: camera, clock=clock,
    )
    assert code == 2
    assert "采集失败" in capsys.readouterr().err
    assert camera.released == 1


def test_cli_interrupt_returns_130(tmp_path, capsys):
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, KeyboardInterrupt())])
    code = run_capture.main(
        ["--duration", "5", "--interval", "1", "--output-dir", str(tmp_path / "task")],
        camera_factory=lambda index: camera, clock=clock,
    )
    assert code == 130
    assert "中断" in capsys.readouterr().err
    assert camera.released == 1


def _raising(error):
    def _boom(*args, **kwargs):
        raise error
    return _boom


def test_cli_exposes_secondary_report_failure(tmp_path, capsys, monkeypatch):
    """读取失败 + 发布失败：CLI 必须把附加错误写进 stderr，且不返回成功。"""
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, None)])
    marker = "报告写入被拒绝"
    monkeypatch.setattr(capture_task, "_publish_report", _raising(OSError(marker)))
    output_dir = tmp_path / "task"
    code = run_capture.main(
        ["--duration", "1", "--interval", "1", "--output-dir", str(output_dir)],
        camera_factory=lambda index: camera, clock=clock,
    )
    assert code == 2
    assert camera.released == 1
    assert not (output_dir / "capture_task.json").exists()
    err = capsys.readouterr().err
    assert marker in err
    assert "阶段=report" in err and "OSError" in err
    assert "采集失败" in err


def test_cli_interrupt_exposes_secondary_report_failure(tmp_path, capsys, monkeypatch):
    """采集中断 + 发布失败：退出码仍为 130，附加错误必须可见。"""
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, KeyboardInterrupt())])
    marker = "中断后发布也失败"
    monkeypatch.setattr(capture_task, "_publish_report", _raising(OSError(marker)))
    output_dir = tmp_path / "task"
    code = run_capture.main(
        ["--duration", "5", "--interval", "1", "--output-dir", str(output_dir)],
        camera_factory=lambda index: camera, clock=clock,
    )
    assert code == 130
    assert camera.released == 1
    err = capsys.readouterr().err
    assert "中断" in err
    assert marker in err
    assert "阶段=report" in err


def test_cli_unexpected_exception_keeps_traceback(tmp_path):
    clock = FakeClock()
    camera = ScriptedCamera(clock, [(0.5, MemoryError("模拟内存不足"))])
    with pytest.raises(MemoryError):
        run_capture.main(
            ["--duration", "5", "--interval", "1", "--output-dir", str(tmp_path / "task")],
            camera_factory=lambda index: camera, clock=clock,
        )
    assert camera.released == 1
