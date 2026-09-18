"""图像质量指标计算。"""

import cv2
import numpy as np


def calculate_mean_brightness(frame: np.ndarray) -> float:
    """计算图像的平均灰度亮度，返回范围为 0.0 到 255.0。"""
    if frame is None:
        raise ValueError("图像不能是 None")

    if not isinstance(frame, np.ndarray):
        raise TypeError("图像必须是 NumPy 数组")

    if frame.size == 0:
        raise ValueError("图像不能为空")

    if frame.ndim == 2:
        gray = frame
    elif frame.ndim == 3 and frame.shape[2] == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError("图像必须是灰度图或 BGR 三通道图")

    return float(gray.mean())
