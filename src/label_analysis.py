"""Array-only QR baseline and explicit ROI; no files, UI or network."""

from base64 import b64encode
from importlib.metadata import version
from time import perf_counter

import numpy as np


DECODER_CONFIG = {
    "formats": ["QRCode"], "try_rotate": True, "try_downscale": False,
    "try_invert": False, "text_mode": "Plain", "binarizer": "LocalAverage",
    "is_pure": False, "return_errors": True,
    "external_enhancement": "none",
}


class LabelAnalysisError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def select_region(bgr, roi=None):
    """ROI is x,y,width,height, with an exclusive right/bottom boundary."""
    if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or (
        bgr.ndim != 3 or bgr.shape[2] != 3 or min(bgr.shape[:2]) < 1
    ):
        raise LabelAnalysisError("invalid_analysis_image", "分析图必须是非空 uint8 BGR 三通道数组")
    height, width = bgr.shape[:2]
    if roi is None:
        return bgr, {"kind": "full_image", "x": 0, "y": 0, "width": width, "height": height}
    if not isinstance(roi, (list, tuple)) or len(roi) != 4 or any(type(v) is not int for v in roi):
        raise LabelAnalysisError("invalid_roi", "ROI 必须是四个整数：x y width height")
    x, y, w, h = roi
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise LabelAnalysisError("invalid_roi", f"ROI 必须完整位于转正后的 {width}×{height} 图像内，且宽高为正")
    return bgr[y:y+h, x:x+w], {"kind": "roi", "x": x, "y": y, "width": w, "height": h}


def decode_qr(bgr, region, *, try_downscale=False):
    """Decode once; never select one of multiple symbols using known truth."""
    started = perf_counter()
    if type(try_downscale) is not bool:
        raise LabelAnalysisError("invalid_decoder_config", "try_downscale 必须是布尔值")
    config = dict(DECODER_CONFIG)
    config["try_downscale"] = try_downscale
    result = {"status": "execution_error", "symbols": [], "error": None,
              "decoder": {"name": "zxing-cpp", "version": None},
              "config": config}
    try:
        import zxingcpp
        result["decoder"]["version"] = version("zxing-cpp")
    except ImportError:
        result["error"] = {"code": "decoder_unavailable", "message": "缺少 zxing-cpp；请安装项目依赖"}
        result["duration_seconds"] = perf_counter() - started
        return result
    try:
        symbols = zxingcpp.read_barcodes(
            np.ascontiguousarray(bgr), formats=zxingcpp.BarcodeFormat.QRCode,
            try_rotate=True, try_downscale=try_downscale, try_invert=False,
            text_mode=zxingcpp.TextMode.Plain, binarizer=zxingcpp.Binarizer.LocalAverage,
            is_pure=False, return_errors=True,
        )
        for symbol in symbols:
            local = [[getattr(symbol.position, corner).x, getattr(symbol.position, corner).y]
                     for corner in ("top_left", "top_right", "bottom_right", "bottom_left")]
            raw = bytes(symbol.bytes)
            result["symbols"].append({
                "valid": bool(symbol.valid), "format": str(symbol.format),
                "text": symbol.text, "payload_base64": b64encode(raw).decode("ascii"),
                "position_region": local,
                "position_analysis_image": [[x + region["x"], y + region["y"]] for x, y in local],
                "error": None if symbol.error is None else {
                    "type": str(symbol.error.type), "message": symbol.error.message,
                },
            })
        count = len(result["symbols"])
        if count == 0:
            result["status"] = "not_decoded"
        elif count > 1:
            result["status"] = "ambiguous"
        elif result["symbols"][0]["valid"]:
            result["status"] = "decoded"
        else:
            result["status"] = "decode_error"
            result["error"] = {"code": "symbol_decode_error", "message": "检测到候选码但解码报告错误"}
    except MemoryError:
        raise
    except Exception as error:
        # Retain a failed attempt instead of silently counting it as no QR.
        result["error"] = {"code": "decoder_execution_error", "exception_type": type(error).__name__,
                           "message": str(error)}
    result["duration_seconds"] = perf_counter() - started
    return result


def summarize_decodes(decodes):
    """Aggregate without truth: any multi-target or execution failure stays visible."""
    summary = {"status": "not_decoded", "symbols": [], "selected_attempt_index": None,
               "failed_attempt_indices": [i for i, d in enumerate(decodes)
                                          if d["status"] in {"decode_error", "execution_error"}]}
    statuses = {d["status"] for d in decodes}
    if "execution_error" in statuses:
        summary["status"] = "execution_error"
    elif "ambiguous" in statuses:
        summary["status"] = "ambiguous"
    else:
        valid = [(i, d["symbols"][0]) for i, d in enumerate(decodes) if d["status"] == "decoded"]
        if len({s["payload_base64"] for _, s in valid}) > 1:
            summary["status"] = "conflict"
        elif valid:
            index, symbol = valid[0]
            summary.update(status="decoded", symbols=[symbol], selected_attempt_index=index)
        elif "decode_error" in statuses:
            summary["status"] = "decode_error"
    return summary


def check_expected(decoded, expected=None):
    """Expected is independently supplied UTF-8 bytes, never decoder-derived."""
    if expected is None:
        return {"status": "not_provided", "comparison": "exact_payload_bytes"}
    status = decoded["status"]
    if status == "decoded":
        status = "correct" if decoded["symbols"][0]["payload_base64"] == b64encode(expected).decode("ascii") else "incorrect"
    return {"status": status, "comparison": "exact_payload_bytes"}
