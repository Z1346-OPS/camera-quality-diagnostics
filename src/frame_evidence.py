"""按用户显式选择保存未叠加文字的单帧 PNG 证据。"""

from pathlib import Path
from uuid import UUID

import cv2


REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"


def save_frame_evidence(frame, run_id: str, frame_count: int, output_path: Path | None = None) -> Path:
    """把原始帧独占新建为 PNG；不覆盖已有图片。"""
    try:
        if not isinstance(run_id, str) or UUID(hex=run_id).hex != run_id:
            raise ValueError
    except ValueError as error:
        raise ValueError("run_id 格式无效") from error
    if type(frame_count) is not int or frame_count < 1:
        raise ValueError("帧号无效")
    encoded_ok, encoded = cv2.imencode(".png", frame)
    if not encoded_ok:
        raise ValueError("PNG 编码失败")
    target = Path(output_path) if output_path is not None else (
        REPORT_DIR / f"camera_frame_{run_id}_{frame_count}.png"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as result:
        result.write(encoded.tobytes())
    return target
