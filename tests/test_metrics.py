"""图像质量指标测试。"""

import numpy as np
import pytest

from src.metrics import calculate_mean_brightness


@pytest.mark.parametrize(
    ("pixel_value", "expected"),
    [(0, 0.0), (128, 128.0), (255, 255.0)],
)
def test_mean_brightness_for_grayscale_image(pixel_value, expected):
    image = np.full((20, 30), pixel_value, dtype=np.uint8)

    assert calculate_mean_brightness(image) == expected


def test_mean_brightness_converts_bgr_to_grayscale():
    blue_image = np.zeros((10, 10, 3), dtype=np.uint8)
    blue_image[:, :, 0] = 255

    assert calculate_mean_brightness(blue_image) == pytest.approx(29.0, abs=1.0)


def test_mean_brightness_rejects_empty_image():
    empty_image = np.array([], dtype=np.uint8)

    with pytest.raises(ValueError, match="图像不能为空"):
        calculate_mean_brightness(empty_image)
