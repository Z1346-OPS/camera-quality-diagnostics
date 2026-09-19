"""图像质量指标计算。"""

import cv2
import numpy as np


def _to_grayscale(frame: np.ndarray) -> np.ndarray:
    """检查输入并转换为灰度图。"""
    if frame is None:
        raise ValueError("图像不能是 None")

    if not isinstance(frame, np.ndarray):
        raise TypeError("图像必须是 NumPy 数组")

    if frame.size == 0:
        raise ValueError("图像不能为空")

    if frame.ndim == 2:
        return frame

    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    raise ValueError("图像必须是灰度图或 BGR 三通道图")


def calculate_mean_brightness(frame: np.ndarray) -> float:
    """计算图像的平均灰度亮度，返回范围为 0.0 到 255.0。"""
    gray = _to_grayscale(frame)

    return float(gray.mean())


def calculate_contrast(frame: np.ndarray) -> float:
    """使用灰度标准差计算全局对比度分数。"""
    gray = _to_grayscale(frame)

    return float(gray.std())


def calculate_sharpness(frame: np.ndarray) -> float:
    """使用拉普拉斯方差计算清晰度分数，分数越高通常表示边缘越丰富。"""
    gray = _to_grayscale(frame)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)

    return float(laplacian.var())


def calculate_exposure_ratios(
    frame: np.ndarray,
    dark_threshold: int = 30,
    bright_threshold: int = 225,
) -> tuple[float, float]:
    """返回欠曝和过曝像素百分比，两个结果的范围均为 0.0 到 100.0。"""
    if not 0 <= dark_threshold < bright_threshold <= 255:
        raise ValueError("阈值必须满足 0 <= dark_threshold < bright_threshold <= 255")

    gray = _to_grayscale(frame)
    pixel_count = gray.size
    dark_ratio = np.count_nonzero(gray <= dark_threshold) / pixel_count * 100
    bright_ratio = np.count_nonzero(gray >= bright_threshold) / pixel_count * 100

    return float(dark_ratio), float(bright_ratio)
