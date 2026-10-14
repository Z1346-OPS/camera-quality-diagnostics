"""Phase 4.1 独立质量测量模块的验收测试（对应规格 A01–A16）。

期望值来自固定像素的数学定义与**改动前**的 `src/metrics.py` 基线（规格第 5.2 节），
不调用被测模块的分块辅助函数，也不由新模块输出反向生成。
"""

from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import pytest

from src import analyze_image as image_module
from src import metrics
from src.quality_analysis import QualityAnalysisError, analyze_quality


ROOT = Path(__file__).resolve().parents[1]

# 规格第 5.2 节：改动前用现有 src.metrics 实测的基线（外部 oracle，不由新模块重生成）。
PRECHANGE_BASELINE = {
    "constant128": {"brightness": 128.0, "contrast": 0.0, "sharpness": 0.0},
    "left40_right120": {"brightness": 80.0, "contrast": 40.0, "sharpness": 1600.0},
    "center_impulse100": {
        "brightness": 4.0,
        "contrast": 19.595917942265423,
        "sharpness": 8000.0,
    },
}

# 规格第 4.3 节：整数可精确表示的结果精确比较，sqrt(384) 等浮点结果用固定误差界。
FLOAT_TOLERANCE = {"rel": 1e-12, "abs": 1e-12}


def _constant_128():
    return np.full((8, 8), 128, dtype=np.uint8)


def _left40_right120():
    image = np.empty((8, 8), dtype=np.uint8)
    image[:, :4] = 40
    image[:, 4:] = 120
    return image


def _center_impulse_100():
    image = np.zeros((5, 5), dtype=np.uint8)
    image[2, 2] = 100
    return image


def _assert_native_types(node):
    """递归断言结构里只有 Python 原生类型，且浮点有限（不允许 NaN / Infinity）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            assert isinstance(key, str)
            _assert_native_types(value)
    elif isinstance(node, list):
        for item in node:
            _assert_native_types(item)
    elif isinstance(node, bool):
        assert type(node) is bool
    elif isinstance(node, int):
        assert type(node) is int
    elif isinstance(node, float):
        assert type(node) is float
        assert math.isfinite(node)
    else:
        assert isinstance(node, str) or node is None


# --- A01 -------------------------------------------------------------------


def test_constant_image_oracle():
    result = analyze_quality(_constant_128())

    assert result["metrics"]["brightness"] == 128.0
    assert result["metrics"]["contrast"] == 0.0
    assert result["metrics"]["sharpness"] == 0.0

    uniformity = result["metrics"]["brightness_uniformity"]
    assert uniformity["grid_shape"] == [4, 4]
    assert len(uniformity["blocks"]) == 16
    assert [block["mean"] for block in uniformity["blocks"]] == [128.0] * 16
    assert uniformity["mean_range"] == 0.0
    assert uniformity["mean_std"] == 0.0

    assert result["applicability"] == {"valid": True, "reasons": []}


# --- A02 -------------------------------------------------------------------


def test_two_level_image_oracle():
    result = analyze_quality(_left40_right120())

    assert result["metrics"]["brightness"] == 80.0
    assert result["metrics"]["contrast"] == 40.0

    blocks = result["metrics"]["brightness_uniformity"]["blocks"]
    assert len(blocks) == 16
    # 8 列切成 [0,2) [2,4) [4,6) [6,8)，每行块均值为 [40, 40, 120, 120]
    for row in range(4):
        row_means = [blocks[row * 4 + column]["mean"] for column in range(4)]
        assert row_means == [40.0, 40.0, 120.0, 120.0]

    uniformity = result["metrics"]["brightness_uniformity"]
    assert uniformity["mean_range"] == 80.0
    assert uniformity["mean_std"] == 40.0


# --- A03 -------------------------------------------------------------------


def test_impulse_image_oracle():
    result = analyze_quality(_center_impulse_100())

    assert result["metrics"]["brightness"] == 4.0
    assert result["metrics"]["contrast"] == pytest.approx(math.sqrt(384), **FLOAT_TOLERANCE)
    assert result["metrics"]["sharpness"] == 8000.0


# --- A04 -------------------------------------------------------------------


def test_prechange_metrics_baseline():
    """现有基础指标与改动前基线逐字段一致；oracle 为规格第 5.2 节固定常量。"""
    images = {
        "constant128": _constant_128(),
        "left40_right120": _left40_right120(),
        "center_impulse100": _center_impulse_100(),
    }

    for name, image in images.items():
        expected = PRECHANGE_BASELINE[name]
        assert metrics.calculate_mean_brightness(image) == expected["brightness"]
        assert metrics.calculate_contrast(image) == pytest.approx(
            expected["contrast"], **FLOAT_TOLERANCE
        )
        assert metrics.calculate_sharpness(image) == expected["sharpness"]


# --- A05 -------------------------------------------------------------------


def test_roi_isolation_and_coordinates():
    base = np.zeros((12, 12), dtype=np.uint8)
    base[2:8, 2:8] = 100  # ROI (2, 2, 6, 6)
    base[2:8, 8] = 200  # 右边界外一列，必须不被包含
    base[8, 2:8] = 200  # 下边界外一行，必须不被包含

    first = analyze_quality(base, (2, 2, 6, 6))
    assert first["metrics"]["brightness"] == 100.0
    assert first["metrics"]["contrast"] == 0.0
    assert first["metrics"]["sharpness"] == 0.0

    changed = base.copy()
    changed[:, :] = 255
    changed[2:8, 2:8] = 100  # 只恢复 ROI 内像素

    second = analyze_quality(changed, (2, 2, 6, 6))
    assert second["metrics"] == first["metrics"]

    blocks = first["metrics"]["brightness_uniformity"]["blocks"]
    assert len(blocks) == 16
    assert min(block["x"] for block in blocks) == 2
    assert min(block["y"] for block in blocks) == 2
    assert max(block["x"] + block["width"] for block in blocks) == 8
    assert max(block["y"] + block["height"] for block in blocks) == 8
    # 块坐标指向原输入数组，而不是 ROI 局部坐标
    assert blocks[0]["x"] == 2 and blocks[0]["y"] == 2


# --- A06 -------------------------------------------------------------------


def test_nondivisible_grid_oracle():
    image = np.arange(35, dtype=np.uint8).reshape(5, 7)
    row_bounds = [(0, 2), (2, 3), (3, 4), (4, 5)]
    column_bounds = [(0, 2), (2, 4), (4, 6), (6, 7)]

    assert [bottom - top for top, bottom in row_bounds] == [2, 1, 1, 1]
    assert [right - left for left, right in column_bounds] == [2, 2, 2, 1]

    result = analyze_quality(image)
    blocks = result["metrics"]["brightness_uniformity"]["blocks"]
    assert len(blocks) == 16

    covered = np.zeros((5, 7), dtype=int)
    for index, block in enumerate(blocks):
        row, column = divmod(index, 4)
        top, bottom = row_bounds[row]
        left, right = column_bounds[column]
        assert block["width"] > 0 and block["height"] > 0
        assert (block["x"], block["y"]) == (left, top)
        assert (block["width"], block["height"]) == (right - left, bottom - top)
        assert block["mean"] == float(image[top:bottom, left:right].mean())
        covered[top:bottom, left:right] += 1

    assert covered.sum() == 35
    assert covered.min() == 1 and covered.max() == 1  # 每像素恰好覆盖一次

    canvas = np.zeros((9, 11), dtype=np.uint8)
    canvas[3:8, 4:11] = image  # 同尺寸区域偏移到 (x=4, y=3)
    offset = analyze_quality(canvas, (4, 3, 7, 5))
    offset_blocks = offset["metrics"]["brightness_uniformity"]["blocks"]
    for index, block in enumerate(offset_blocks):
        row, column = divmod(index, 4)
        top, bottom = row_bounds[row]
        left, right = column_bounds[column]
        assert (block["x"], block["y"]) == (4 + left, 3 + top)
        assert block["mean"] == float(image[top:bottom, left:right].mean())
    assert [b["mean"] for b in offset_blocks] == [b["mean"] for b in blocks]


# --- A07 -------------------------------------------------------------------


def test_small_region_contract():
    cases = [
        ((1, 1), False, False),
        ((2, 2), False, False),
        ((1, 10), False, False),
        ((10, 1), False, False),
        ((3, 3), True, False),
        ((3, 10), True, False),
        ((10, 3), True, False),
        ((4, 4), True, True),
        ((4, 10), True, True),
    ]

    for (width, height), has_sharpness, has_uniformity in cases:
        image = np.full((height, width), 90, dtype=np.uint8)
        result = analyze_quality(image)
        metrics_result = result["metrics"]
        label = f"{width}x{height}"

        assert metrics_result["brightness"] == 90.0, label
        assert metrics_result["contrast"] == 0.0, label
        if has_sharpness:
            assert metrics_result["sharpness"] == 0.0, label
        else:
            assert metrics_result["sharpness"] is None, label
        if has_uniformity:
            assert metrics_result["brightness_uniformity"] is not None, label
        else:
            assert metrics_result["brightness_uniformity"] is None, label

        expected_reasons = []
        if not has_sharpness:
            expected_reasons.append("sharpness_insufficient_dimensions")
        if not has_uniformity:
            expected_reasons.append("uniformity_insufficient_dimensions")
        assert result["applicability"]["reasons"] == expected_reasons, label
        assert result["applicability"]["valid"] is (has_sharpness and has_uniformity), label


# --- A08 -------------------------------------------------------------------


def test_invalid_images():
    cases = [
        ("not_array", [[1, 2], [3, 4]]),
        ("none", None),
        ("empty_1d", np.array([], dtype=np.uint8)),
        ("empty_2d", np.zeros((0, 5), dtype=np.uint8)),
        ("empty_3d", np.zeros((0, 0, 3), dtype=np.uint8)),
        ("float32", np.zeros((4, 4), dtype=np.float32)),
        ("uint16", np.zeros((4, 4), dtype=np.uint16)),
        ("bool", np.zeros((4, 4), dtype=bool)),
        ("one_dimension", np.zeros(5, dtype=np.uint8)),
        ("four_dimensions", np.zeros((2, 2, 2, 2), dtype=np.uint8)),
        ("four_channels", np.zeros((4, 4, 4), dtype=np.uint8)),
        ("two_channels", np.zeros((4, 4, 2), dtype=np.uint8)),
    ]

    for name, image in cases:
        with pytest.raises(QualityAnalysisError) as error:
            analyze_quality(image)
        assert error.value.code == "invalid_image", name
        assert isinstance(error.value, ValueError), name


# --- A09 -------------------------------------------------------------------


def test_roi_validation_boundaries():
    image = np.full((10, 10), 50, dtype=np.uint8)
    invalid_rois = [
        (0.0, 0, 4, 4),
        (0, 0, 4.5, 4),
        (True, 0, 4, 4),
        (0, 0, True, 4),
        (0, 0, np.int64(4), 4),
        (-1, 0, 4, 4),
        (0, -1, 4, 4),
        (0, 0, 0, 4),
        (0, 0, 4, 0),
        (0, 0, -4, 4),
        (7, 0, 4, 4),
        (0, 7, 4, 4),
        (0, 0, 11, 4),
        (0, 0, 4, 11),
        (0, 0, 4),
        (0, 0, 4, 4, 1),
        np.array([0, 0, 4, 4]),
        "0 0 4 4",
    ]

    for roi in invalid_rois:
        with pytest.raises(QualityAnalysisError) as error:
            analyze_quality(image, roi)
        assert error.value.code == "invalid_roi", repr(roi)

    # 合法贴边 ROI 必须正常接受，不裁剪、不补边
    for roi in [(0, 0, 10, 10), (6, 6, 4, 4), (0, 0, 1, 1), (9, 9, 1, 1), [0, 0, 4, 4]]:
        result = analyze_quality(image, roi)
        assert result["metrics"]["brightness"] == 50.0, repr(roi)


# --- A10 -------------------------------------------------------------------


def test_input_preservation_and_views():
    base = np.arange(64, dtype=np.uint8).reshape(8, 8)
    original = base.copy()

    readonly = base.copy()
    readonly.setflags(write=False)

    carrier = np.zeros((16, 16), dtype=np.uint8)
    carrier[::2, ::2] = base
    view = carrier[::2, ::2]
    assert not view.flags["C_CONTIGUOUS"]
    assert np.array_equal(view, base)

    contiguous = np.ascontiguousarray(view)

    results = [
        analyze_quality(source) for source in (base, readonly, view, contiguous)
    ]

    assert np.array_equal(base, original)
    assert base.dtype == np.uint8
    for result in results:
        assert result["metrics"] == results[0]["metrics"]


# --- A11 -------------------------------------------------------------------


def test_grayscale_and_bgr_contract():
    gray = np.arange(48, dtype=np.uint8).reshape(6, 8)
    replicated = np.repeat(gray[:, :, None], 3, axis=2)

    gray_result = analyze_quality(gray)
    replicated_result = analyze_quality(replicated)
    assert replicated_result["metrics"] == gray_result["metrics"]
    assert replicated_result["applicability"] == gray_result["applicability"]

    # 纯蓝 BGR：(B, G, R) = (255, 0, 0) → 灰度 0.114 × 255 = 29；若误当 RGB 会得到 76
    blue = np.zeros((4, 4, 3), dtype=np.uint8)
    blue[:, :, 0] = 255
    blue_result = analyze_quality(blue)
    assert blue_result["metrics"]["brightness"] == 29.0
    assert blue_result["metrics"]["contrast"] == 0.0
    assert blue_result["metrics"]["sharpness"] == 0.0


# --- A12 -------------------------------------------------------------------


def test_output_schema_and_serialization():
    images = {
        "normal": np.arange(64, dtype=np.uint8).reshape(8, 8),
        "constant": np.full((8, 8), 128, dtype=np.uint8),
        "small": np.full((2, 2), 10, dtype=np.uint8),
    }

    for name, image in images.items():
        result = analyze_quality(image)
        assert set(result) == {"metrics", "warnings", "applicability"}, name
        assert set(result["metrics"]) == {
            "sharpness", "brightness", "contrast", "brightness_uniformity",
        }, name
        assert set(result["applicability"]) == {"valid", "reasons"}, name
        assert isinstance(result["applicability"]["valid"], bool), name
        for reason in result["applicability"]["reasons"]:
            assert isinstance(reason, str), name
        for warning in result["warnings"]:
            assert set(warning) == {"type", "evidence", "severity"}, name
            assert warning["severity"] in {"info", "warning"}, name

        _assert_native_types(result)
        rendered = json.dumps(result, allow_nan=False)
        assert json.loads(rendered) == result, name

    assert [w["type"] for w in analyze_quality(images["normal"])["warnings"]] == [
        "measurement_scope"
    ]
    assert [w["type"] for w in analyze_quality(images["constant"])["warnings"]] == [
        "measurement_scope", "constant_region"
    ]
    small = analyze_quality(images["small"])
    assert [w["type"] for w in small["warnings"]] == [
        "measurement_scope", "constant_region", "insufficient_spatial_support"
    ]
    assert small["applicability"]["reasons"] == [
        "sharpness_insufficient_dimensions", "uniformity_insufficient_dimensions"
    ]


# --- A13 -------------------------------------------------------------------


def test_measurement_only_warnings():
    constant = np.full((8, 8), 128, dtype=np.uint8)
    # 2 像素格黑白棋盘：每块均值在 0 / 255 之间交替，块间差异明确非零
    rows, columns = np.indices((8, 8))
    checker = np.where(((rows // 2) + (columns // 2)) % 2 == 0, 255, 0).astype(np.uint8)
    gradient = np.tile(np.arange(8, dtype=np.uint8) * 32, (8, 1))

    forbidden = {
        "score", "grade", "quality_score", "pass", "pass_fail", "failure_reason",
        "defect", "fault", "is_ok", "acceptable", "block_brightness_variation",
        "small_blocks",
    }

    for name, image in (("constant", constant), ("checker", checker), ("gradient", gradient)):
        result = analyze_quality(image)
        assert set(result) == {"metrics", "warnings", "applicability"}, name
        types = [warning["type"] for warning in result["warnings"]]
        for banned in forbidden:
            assert banned not in types, f"{name}:{banned}"
        for warning in result["warnings"]:
            assert set(warning) == {"type", "evidence", "severity"}, name
            assert warning["severity"] in {"info", "warning"}, name

    # 块间差异非零属于测量事实，不得产生异常/阈值类警告
    for name, image in (("checker", checker), ("gradient", gradient)):
        result = analyze_quality(image)
        assert result["metrics"]["brightness_uniformity"]["mean_range"] > 0, name
        assert [w["type"] for w in result["warnings"]] == ["measurement_scope"], name

    scope = analyze_quality(checker)["warnings"][0]
    assert scope["evidence"]["scene_calibration"] == "none"
    assert set(scope["evidence"]) == {"region", "scene_calibration", "limitations"}

    constant_region = analyze_quality(constant)["warnings"][1]
    assert constant_region["type"] == "constant_region"
    assert set(constant_region["evidence"]) == {"min_gray", "max_gray"}
    assert constant_region["evidence"] == {"min_gray": 128, "max_gray": 128}


# --- A16 -------------------------------------------------------------------


def test_real_png_smoke():
    source = ROOT / "data" / "samples" / "stage2-known-qr.png"
    before = sha256(source.read_bytes()).hexdigest()

    bgr, metadata = image_module.load_normalized_image(source)
    assert bgr.dtype == np.uint8
    assert bgr.ndim == 3 and bgr.shape[2] == 3
    height, width = bgr.shape[:2]
    assert (width, height) == (metadata["source"]["width"], metadata["source"]["height"])

    full = analyze_quality(bgr)
    roi = (width // 4, height // 4, width // 2, height // 2)
    roi_result = analyze_quality(bgr, roi)

    for result in (full, roi_result):
        assert set(result) == {"metrics", "warnings", "applicability"}
        assert result["applicability"]["valid"] is True
        assert result["metrics"]["brightness_uniformity"] is not None
        json.dumps(result, allow_nan=False)

    assert roi_result["warnings"][0]["evidence"]["region"] == {
        "kind": "roi", "x": roi[0], "y": roi[1], "width": roi[2], "height": roi[3],
    }
    assert full["warnings"][0]["evidence"]["region"]["kind"] == "full_image"

    after = sha256(source.read_bytes()).hexdigest()
    assert after == before
