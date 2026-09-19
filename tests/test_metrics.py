"""图像质量指标测试。"""

import cv2
import numpy as np
import pytest

from src.metrics import (
    calculate_contrast,
    calculate_exposure_ratios,
    calculate_mean_brightness,
    calculate_sharpness,
)


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


def test_contrast_is_zero_for_uniform_image():
    uniform_image = np.full((20, 20), 128, dtype=np.uint8)

    assert calculate_contrast(uniform_image) == 0.0


def test_contrast_is_higher_for_wider_gray_range():
    low_contrast = np.array([[120, 136]], dtype=np.uint8)
    high_contrast = np.array([[0, 255]], dtype=np.uint8)

    low_score = calculate_contrast(low_contrast)
    high_score = calculate_contrast(high_contrast)

    assert low_score == 8.0
    assert high_score == 127.5
    assert high_score > low_score


def test_sharpness_is_zero_for_uniform_image():
    uniform_image = np.full((60, 60), 128, dtype=np.uint8)

    assert calculate_sharpness(uniform_image) == 0.0


def test_sharpness_decreases_after_blurring():
    checker = np.zeros((60, 60), dtype=np.uint8)
    checker[::2, ::2] = 255
    checker[1::2, 1::2] = 255
    blurred = cv2.GaussianBlur(checker, (7, 7), 0)

    sharp_score = calculate_sharpness(checker)
    blurred_score = calculate_sharpness(blurred)

    assert sharp_score > blurred_score
    assert blurred_score >= 0.0


@pytest.mark.parametrize(
    ("pixel_value", "expected_dark", "expected_bright"),
    [(0, 100.0, 0.0), (128, 0.0, 0.0), (255, 0.0, 100.0)],
)
def test_exposure_ratios_for_uniform_image(
    pixel_value, expected_dark, expected_bright
):
    image = np.full((10, 10), pixel_value, dtype=np.uint8)

    dark_ratio, bright_ratio = calculate_exposure_ratios(image)

    assert dark_ratio == expected_dark
    assert bright_ratio == expected_bright


def test_exposure_ratios_include_threshold_boundaries():
    image = np.array([[0, 29, 30, 31, 224, 225, 226, 255]], dtype=np.uint8)

    dark_ratio, bright_ratio = calculate_exposure_ratios(image)

    assert dark_ratio == 37.5
    assert bright_ratio == 37.5


@pytest.mark.parametrize(
    ("dark_threshold", "bright_threshold"),
    [(-1, 225), (30, 256), (30, 30), (225, 30)],
)
def test_exposure_ratios_reject_invalid_thresholds(
    dark_threshold, bright_threshold
):
    image = np.full((10, 10), 128, dtype=np.uint8)

    with pytest.raises(ValueError, match="阈值必须满足"):
        calculate_exposure_ratios(image, dark_threshold, bright_threshold)
