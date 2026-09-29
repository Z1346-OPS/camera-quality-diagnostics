"""首次保存图像指标时，独立记录程序可确认的会话信息。"""

from datetime import datetime
import json
from pathlib import Path
from uuid import UUID


REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"


def save_session_metadata(
    run_id: str, camera_index: int, backend: str | None,
    width: int, height: int, output_path: Path | None = None,
) -> Path:
    """独占新建会话 JSON；后端未知时保存 null，不推断曝光状态。"""
    if not isinstance(run_id, str) or UUID(hex=run_id).hex != run_id:
        raise ValueError("run_id 格式无效")
    if (type(camera_index) is not int or camera_index < 0 or
            type(width) is not int or width < 1 or type(height) is not int or height < 1):
        raise ValueError("摄像头编号或画面尺寸无效")
    if backend is not None and (not isinstance(backend, str) or not backend.strip()):
        raise ValueError("后端名称无效")
    target = Path(output_path) if output_path is not None else REPORT_DIR / f"camera_session_{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1, "run_id": run_id, "source": "camera_test_runtime",
        "metadata_recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "camera_index_configured": camera_index,
        "backend_reported_by_opencv": backend,
        "frame_width_px": width, "frame_height_px": height,
    }
    with target.open("x", encoding="utf-8") as result:
        json.dump(payload, result, ensure_ascii=False, indent=2)
        result.write("\n")
    return target
