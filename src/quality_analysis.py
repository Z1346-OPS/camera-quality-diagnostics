"""只处理图像数组的质量测量：输出测量事实与适用性限制，**不给出质量结论**。

本模块不读文件、不调用解码器、不做场景标定。首版不输出「模糊」「曝光异常」「照明故障」
「不合格」等结论——这些必须针对受控数据完成阈值标定后才能给出。

约定（与 `src/metrics.py`、`src/analyze_image.py` 保持一致）：

- 输入为 `uint8` 灰度图或 BGR 三通道数组；BGR 先转灰度。
- ROI 为 `(x, y, width, height)`，基于传入数组，右/下边界**不包含**；越界直接拒绝，不裁剪、不补边。
- 不修改输入数组、不读写文件、不调用 QR 解码。
- 分块亮度均衡固定使用 **4×4 网格**：这是可复现的采样约定，对单个块**内部**的局部照明
  变化不敏感（例如 1600×1200 的区域，块为 400×300）。固定网格**不保证**不同场景或不同
  尺寸之间可直接比较，也**不是**工业合格标准，更不是"能发现局部暗角"的保证。
"""

import cv2
import numpy as np

if __package__:
    from . import metrics
else:
    import metrics

GRID_SIZE = 4
MIN_SHARPNESS_SIDE = 3
MIN_UNIFORMITY_SIDE = 4


class QualityAnalysisError(ValueError):
    """带稳定 `code` 的输入错误，用于区分 `invalid_image` 与 `invalid_roi`。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _require(condition, code, message):
    if not condition:
        raise QualityAnalysisError(code, message)


def _to_gray(image):
    _require(isinstance(image, np.ndarray), "invalid_image", "图像必须是 NumPy 数组")
    _require(image.dtype == np.uint8, "invalid_image", "图像 dtype 必须是 uint8")
    _require(image.ndim in (2, 3), "invalid_image", "图像必须是灰度图或 BGR 三通道图")
    if image.ndim == 3:
        _require(image.shape[2] == 3, "invalid_image", "三通道图必须是 BGR 三通道")
    _require(image.shape[0] >= 1 and image.shape[1] >= 1, "invalid_image", "图像不能为空")
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _select_roi(gray, roi):
    height, width = gray.shape[:2]
    if roi is None:
        return gray, {"kind": "full_image", "x": 0, "y": 0, "width": width, "height": height}
    _require(isinstance(roi, (list, tuple)) and len(roi) == 4, "invalid_roi",
             "ROI 必须是 (x, y, width, height) 四个整数")
    _require(all(type(value) is int for value in roi), "invalid_roi", "ROI 必须是整数，不接受浮点或布尔值")
    x, y, roi_width, roi_height = roi
    _require(x >= 0 and y >= 0, "invalid_roi", "ROI 的 x / y 不能为负")
    _require(roi_width > 0 and roi_height > 0, "invalid_roi", "ROI 的宽高必须为正")
    _require(x + roi_width <= width and y + roi_height <= height, "invalid_roi",
             f"ROI 必须完整位于 {width}×{height} 图像内")
    return (gray[y:y + roi_height, x:x + roi_width],
            {"kind": "roi", "x": x, "y": y, "width": roi_width, "height": roi_height})


def _boundaries(total, parts):
    """把 [0, total) 切成 parts 段连续整数边界，完全覆盖且不重叠。"""
    base, extra = divmod(total, parts)
    bounds, start = [], 0
    for index in range(parts):
        size = base + (1 if index < extra else 0)
        bounds.append((start, start + size))
        start += size
    return bounds


def _brightness_uniformity(gray, region):
    """固定 4×4 网格的块均值统计；区域任一边不足 4 像素时返回 None（不缩减网格）。"""
    height, width = gray.shape[:2]
    if width < MIN_UNIFORMITY_SIDE or height < MIN_UNIFORMITY_SIDE:
        return None
    columns = _boundaries(width, GRID_SIZE)
    rows = _boundaries(height, GRID_SIZE)
    blocks = []
    for top, bottom in rows:
        for left, right in columns:
            block = gray[top:bottom, left:right]
            blocks.append({"x": region["x"] + left, "y": region["y"] + top,
                           "width": right - left, "height": bottom - top,
                           "mean": float(block.mean())})
    means = np.array([block["mean"] for block in blocks], dtype=np.float64)
    return {"grid_shape": [GRID_SIZE, GRID_SIZE], "blocks": blocks,
            "mean_range": float(means.max() - means.min()),
            "mean_std": float(means.std())}


def _build_warnings(region, gray, unavailable):
    warnings = [{
        "type": "measurement_scope",
        "severity": "info",
        "evidence": {
            "region": region,
            "scene_calibration": "none",
            "limitations": [
                "块间差异可能来自图案内容、颜色或阴影，不等同于照明异常",
                "固定 4×4 网格对块内部的局部暗点或局部变化不敏感",
                "固定网格不保证不同场景或不同尺寸之间可直接比较",
            ],
        },
    }]
    low, high = int(gray.min()), int(gray.max())
    if low == high:
        warnings.append({
            "type": "constant_region", "severity": "info",
            "evidence": {"min_gray": low, "max_gray": high},
        })
    if unavailable:
        warnings.append({
            "type": "insufficient_spatial_support", "severity": "warning",
            "evidence": {"region": region, "unavailable": list(unavailable),
                         "required_minimum_side": {"sharpness": MIN_SHARPNESS_SIDE,
                                                   "brightness_uniformity": MIN_UNIFORMITY_SIDE}},
        })
    return warnings


def analyze_quality(image, roi=None):
    """测量给定数组（或 ROI）的质量指标，并说明这些测量在什么条件下成立。

    返回 `{"metrics": ..., "warnings": ..., "applicability": ...}`。
    `applicability.valid` 只表示四项测量都满足接口规定的空间条件，
    **不表示**图像清晰、曝光正常、可识读或工业合格。
    """
    gray = _to_gray(image)
    selected, region = _select_roi(gray, roi)
    height, width = selected.shape[:2]
    sharpness = (metrics.calculate_sharpness(selected)
                 if width >= MIN_SHARPNESS_SIDE and height >= MIN_SHARPNESS_SIDE else None)
    uniformity = _brightness_uniformity(selected, region)
    unavailable = []
    if sharpness is None:
        unavailable.append("sharpness_insufficient_dimensions")
    if uniformity is None:
        unavailable.append("uniformity_insufficient_dimensions")
    return {
        "metrics": {"sharpness": sharpness,
                    "brightness": metrics.calculate_mean_brightness(selected),
                    "contrast": metrics.calculate_contrast(selected),
                    "brightness_uniformity": uniformity},
        "warnings": _build_warnings(region, selected, unavailable),
        "applicability": {"valid": not unavailable, "reasons": unavailable},
    }
