"""Phase 4.2 关联层验收测试（对应规格 B01–B18）。

期望值来自**独立调用**（`analyze_quality` / `analyze_label`）与证据目录里**冻结的** oracle
（`qr-stable-fields-oracle.json`，**只读加载**），不由被测模块的输出反向生成。
解码层注入夹具遵守规格 6.7.1 的结构契约，只替代解码调用，不伪造整个关联报告。
"""

from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import __version__ as pillow_version
import pytest

from src import analyze_image as images
from src import analyze_label as label_module
from src import label_analysis as core
from src import quality_analysis as quality_module
from src import quality_qr_analysis as association
from src.quality_qr_analysis import QualityQrAssociationError


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
SYNTHETIC = SAMPLES / "synthetic-qr-v1" / "development"
TEST_SPLIT = SAMPLES / "synthetic-qr-v1" / "test"
EVIDENCE = ROOT / "docs" / "tasks" / "evidence" / "phase-4.2-quality-qr-association"
ORACLE = EVIDENCE / "qr-stable-fields-oracle.json"

STAGE2 = SAMPLES / "stage2-known-qr.png"
STAGE2_EXPECTED = SAMPLES / "stage2-known-qr.expected.txt"
STAGE2_ROI = (66, 66, 132, 132)

VOLATILE_PATHS = [
    "analysis_id",
    "analyzed_at",
    "analysis_duration_seconds",
    "provenance.git",
    "attempts[].decode.duration_seconds",
]

# 规格 5.4：既有 analyze_label 报告里允许变化的 volatile 路径，逐路径列出，禁止笼统忽略。
def strip_volatile(report):
    stable = deepcopy(report)
    stable.pop("analysis_id", None)
    stable.pop("analyzed_at", None)
    stable.pop("analysis_duration_seconds", None)
    provenance = stable.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("git", None)
    for attempt in stable.get("attempts", []):
        attempt.get("decode", {}).pop("duration_seconds", None)
    return stable


def normalized(path=STAGE2):
    bgr, _ = images.load_normalized_image(path)
    return bgr


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


# --- 解码层注入夹具（规格 6.7.1）--------------------------------------------

def make_symbol(payload, *, valid=True, error=None):
    raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    local = [[8, 8], [56, 8], [56, 56], [8, 56]]
    return {
        "valid": valid, "format": "QR Code", "text": raw.decode("utf-8"),
        "payload_base64": b64encode(raw).decode("ascii"),
        "position_region": local,
        "position_analysis_image": [list(corner) for corner in local],
        "error": error,
    }


def make_decode(status, *, try_downscale=False, payload="INJECTED", error=None):
    """结构完整的 decode 夹具：status/symbols/error/decoder/config/duration_seconds 全部存在。"""
    if status == "decoded":
        symbols = [make_symbol(payload)]
    elif status == "decode_error":
        symbols = [make_symbol(payload, valid=False,
                               error={"type": "Checksum", "message": "injected bad checksum"})]
        error = {"code": "symbol_decode_error", "message": "检测到候选码但解码报告错误"}
    elif status == "execution_error":
        symbols = []
        error = {"code": "decoder_execution_error", "exception_type": "RuntimeError",
                 "message": "injected decoder failure"}
    else:
        symbols = []
    return {
        "status": status, "symbols": symbols, "error": error,
        "decoder": {"name": "zxing-cpp", "version": "3.1.1"},
        "config": {**core.DECODER_CONFIG, "try_downscale": try_downscale},
        "duration_seconds": 0.0,
    }


def install_decoder(monkeypatch, responder):
    """只替代 `analyze_label` 内部的 `decode_qr`；不伪造整个报告。"""
    def fake(frame, region, *, try_downscale=False):
        return responder(try_downscale)
    monkeypatch.setattr(label_module, "decode_qr", fake)


# --- B01 -------------------------------------------------------------------

def _corrupt(field, value):
    if field in {"width", "height", "analysis_width", "analysis_height"}:
        return value + 1
    if field == "sha256":
        return "0" * 64
    if field == "exif_orientation":
        return 3
    return {"format": "TIFF", "mode": "CMYK"}[field]


@pytest.mark.parametrize("field", association.CHECKED_FIELDS)
def test_read_consistency_refusal(monkeypatch, field):
    """每次仅注入一个字段差异，其余一致；必须拒绝关联且不返回报告。"""
    original = images.load_normalized_image
    calls = {"count": 0}

    def patched(path):
        bgr, metadata = original(path)
        calls["count"] += 1
        if calls["count"] == 1:  # 关联层自己那次读取
            if field in {"sha256", "format", "mode", "width", "height"}:
                metadata["source"][field] = _corrupt(field, metadata["source"][field])
            else:
                metadata["preprocessing"][field] = _corrupt(field, metadata["preprocessing"][field])
        return bgr, metadata

    monkeypatch.setattr(images, "load_normalized_image", patched)
    with pytest.raises(QualityQrAssociationError) as caught:
        association.analyze_quality_and_qr(STAGE2)
    assert caught.value.code == "source_changed_between_reads"
    assert isinstance(caught.value, ValueError)


def test_read_consistency_refusal_control():
    """全一致对照：正常返回，且 checked_fields 恰为规定的 8 个字段（顺序固定）。"""
    result = association.analyze_quality_and_qr(STAGE2)
    consistency = result["read_consistency"]
    assert set(consistency) == {"qr_read_sha256", "quality_read_sha256", "consistent",
                                "checked_fields"}
    assert consistency["checked_fields"] == [
        "sha256", "format", "mode", "width", "height",
        "exif_orientation", "analysis_width", "analysis_height",
    ]
    assert consistency["consistent"] is True
    assert consistency["qr_read_sha256"] == consistency["quality_read_sha256"]
    assert consistency["qr_read_sha256"] == result["qr_report"]["source"]["sha256"]


# --- B02 -------------------------------------------------------------------

def test_full_and_roi_regions_do_not_cross():
    bgr = normalized()
    height, width = bgr.shape[:2]
    for roi in (STAGE2_ROI, (0, 0, width, height), (width // 2, height // 2, width // 2, height // 2)):
        result = association.analyze_quality_and_qr(STAGE2, roi)
        assert [m["measurement_id"] for m in result["measurements"]] == ["full_image", "roi"]
        assert len({m["measurement_id"] for m in result["measurements"]}) == 2

        full, roi_measure = result["measurements"]
        assert full["region"] == {"kind": "full_image", "x": 0, "y": 0,
                                  "width": width, "height": height}
        x, y, w, h = roi
        assert roi_measure["region"] == {"kind": "roi", "x": x, "y": y, "width": w, "height": h}

        # 块坐标指向原数组，右/下边界不包含
        blocks = roi_measure["quality"]["metrics"]["brightness_uniformity"]["blocks"]
        assert min(block["x"] for block in blocks) == x
        assert min(block["y"] for block in blocks) == y
        assert max(block["x"] + block["width"] for block in blocks) == x + w
        assert max(block["y"] + block["height"] for block in blocks) == y + h

        # 整图与 ROI 互不串配：各自等于对应的独立调用
        assert full["quality"] == quality_module.analyze_quality(bgr, None)
        assert roi_measure["quality"] == quality_module.analyze_quality(bgr, roi)


# --- B03 -------------------------------------------------------------------

def test_profiles_share_single_measurement(monkeypatch):
    real = quality_module.analyze_quality
    calls = []

    def counting(image, roi=None):
        calls.append(roi)
        return real(image, roi)

    monkeypatch.setattr(association, "analyze_quality", counting)

    for roi, expected_calls in ((None, 1), (STAGE2_ROI, 2)):
        for try_downscale in (False, True):
            calls.clear()
            result = association.analyze_quality_and_qr(STAGE2, roi, try_downscale=try_downscale)
            assert len(calls) == expected_calls, (roi, try_downscale)
            assert [m["measurement_id"] for m in result["measurements"]] == (
                ["full_image"] if roi is None else ["full_image", "roi"])
            # profile 数变化不增加测量次数；同一区域的多 profile 引用同一条测量
            assert len({a["measurement_id"] for a in result["associations"]}) == len(result["measurements"])
            assert len(result["associations"]) == len(result["qr_report"]["attempts"])


# --- B04 -------------------------------------------------------------------

def test_quality_matches_independent_call():
    bgr = normalized()
    result = association.analyze_quality_and_qr(STAGE2, STAGE2_ROI)
    by_id = {m["measurement_id"]: m for m in result["measurements"]}
    assert by_id["full_image"]["quality"] == quality_module.analyze_quality(bgr, None)
    assert by_id["roi"]["quality"] == quality_module.analyze_quality(bgr, STAGE2_ROI)


# --- B05 -------------------------------------------------------------------

def test_qr_subobject_unchanged():
    result = association.analyze_quality_and_qr(STAGE2, STAGE2_ROI)
    independent = label_module.analyze_label(STAGE2, STAGE2_ROI)
    assert strip_volatile(result["qr_report"]) == strip_volatile(independent)

    snapshot = deepcopy(result["qr_report"])
    result["measurements"][0]["region"]["x"] = 999
    assert result["qr_report"] == snapshot
    result["associations"][0]["region"]["kind"] = "mutated"
    assert result["qr_report"] == snapshot
    result["associations"][1]["region"]["width"] = -1
    assert result["qr_report"] == snapshot


# --- B06 -------------------------------------------------------------------

REAL_DECODE_FIXTURES = [
    (SYNTHETIC / "dev-01-clean-module8-A.png", SYNTHETIC / "answers" / "A.txt", "decoded"),
    (SYNTHETIC / "dev-08-blur-sigma8-D.png", SYNTHETIC / "answers" / "D.txt", "not_decoded"),
    (SYNTHETIC / "dev-07-blur-sigma5-C.png", SYNTHETIC / "answers" / "C.txt", "decode_error"),
    (TEST_SPLIT / "test-07-blur-sigma5-C.png", TEST_SPLIT / "answers" / "C.txt", "ambiguous"),
]


def test_fixture_matrix_covers_states(monkeypatch, tmp_path):
    # 1) 真实解码覆盖 attempt 的 decoded / not_decoded / decode_error / ambiguous
    for image, expected, status in REAL_DECODE_FIXTURES:
        result = association.analyze_quality_and_qr(
            image, None, expected, "合成数据集独立答案（编码器输入，早于解码）",
            try_downscale=True)
        assert {a["decode_status"] for a in result["associations"]} == {status}, image.name

    # 2) decoded + 独立错误答案 → truth_status == "incorrect"
    wrong = association.analyze_quality_and_qr(STAGE2, None, SYNTHETIC / "answers" / "A.txt",
                                               "另一份既有独立答案文件（非解码器输出）")
    assert [a["truth_status"] for a in wrong["associations"]] == ["incorrect"]

    # 3) 无真值 → not_provided
    no_truth = association.analyze_quality_and_qr(STAGE2)
    assert [a["truth_status"] for a in no_truth["associations"]] == ["not_provided"]

    # 4) 小区域（任一边 < 3 / < 4）仍能产出记录
    small = association.analyze_quality_and_qr(STAGE2, (0, 0, 2, 2))
    roi_quality = {m["measurement_id"]: m["quality"] for m in small["measurements"]}["roi"]
    assert roi_quality["metrics"]["sharpness"] is None
    assert roi_quality["metrics"]["brightness_uniformity"] is None

    # 5) 测量异常 → quality_error 且保留 QR
    def failing(image, roi=None):
        raise quality_module.QualityAnalysisError("invalid_roi", "injected measurement failure")
    monkeypatch.setattr(association, "analyze_quality", failing)
    anomalous = association.analyze_quality_and_qr(STAGE2)
    assert anomalous["measurements"][0]["quality"] is None
    assert anomalous["measurements"][0]["quality_error"]["code"] == "invalid_roi"
    assert anomalous["status"] == "completed_with_errors"
    monkeypatch.undo()

    # 6) 解码层注入：execution_error
    install_decoder(monkeypatch, lambda td: make_decode("execution_error", try_downscale=td))
    execution = association.analyze_quality_and_qr(STAGE2)
    assert [a["decode_status"] for a in execution["associations"]] == ["execution_error"]
    assert execution["qr_report"]["decode_summaries"][0]["decode"]["status"] == "execution_error"

    # 7) 两 profile 均为 decoded、payload 不同 → summary 为 conflict，关联表仍为 decoded
    def conflicting(td):
        return make_decode("decoded", try_downscale=td, payload="A" if not td else "B")
    install_decoder(monkeypatch, conflicting)
    conflict = association.analyze_quality_and_qr(STAGE2, None, None, None, try_downscale=True)
    assert [a["decode_status"] for a in conflict["associations"]] == ["decoded", "decoded"]
    assert conflict["qr_report"]["decode_summaries"][0]["decode"]["status"] == "conflict"

    # 8) 恢复：前 profile decode_error、后 profile decoded；失败记录与警告保留
    def recovering(td):
        return make_decode("decoded" if td else "decode_error", try_downscale=td)
    install_decoder(monkeypatch, recovering)
    recovered = association.analyze_quality_and_qr(STAGE2, None, None, None, try_downscale=True)
    assert [a["decode_status"] for a in recovered["associations"]] == ["decode_error", "decoded"]
    assert recovered["qr_report"]["attempts"][0]["decode"]["status"] == "decode_error"
    assert any(w["code"] == "decode_attempt_errors" for w in recovered["qr_report"]["warnings"])
    assert recovered["qr_report"]["decode_summaries"][0]["decode"]["status"] == "decoded"


# --- B07 -------------------------------------------------------------------

def _assert_portable_qr_report(report, record, *, source_path, runtime, decoder_version):
    """业务字段对照冻结值；环境身份及源码摘要从当前文件独立核对。"""
    expected = deepcopy(record["stable"])
    expected["source"]["path"] = source_path
    expected["provenance"]["runtime"] = dict(runtime)
    expected["provenance"]["source_sha256"] = {
        name: sha256((ROOT / "src" / name).read_bytes()).hexdigest()
        for name in ("analyze_image.py", "analysis_config.py", "metrics.py",
                     "analyze_label.py", "label_analysis.py")
    }
    for attempt in expected["attempts"]:
        attempt["decode"]["decoder"]["version"] = decoder_version
    assert strip_volatile(report) == expected, record["name"]


def test_qr_stable_fields_oracle():
    document = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert [entry["path"] for entry in document["volatile_paths"]] == VOLATILE_PATHS
    assert document["generator_source_sha256"] == sha256(
        (EVIDENCE / "extract_qr_stable_fields.py").read_bytes()).hexdigest()
    # 期望来自当前路径与独立读取的运行库版本，不从被测报告取环境身份。
    runtime = {"python": sys.version.split()[0], "opencv": cv2.__version__,
               "numpy": np.__version__, "pillow": pillow_version}
    decoder_version = version("zxing-cpp")

    for record in document["records"]:
        stable = record["stable"]
        roi = tuple(record["roi"]) if record["roi"] else None
        expected_file = (ROOT / record["expected_file"]) if record["expected_file"] else None
        truth_source = stable["known_truth"].get("source_description")
        result = association.analyze_quality_and_qr(
            ROOT / record["image"], roi, expected_file, truth_source,
            try_downscale=record["try_downscale"])
        _assert_portable_qr_report(
            result["qr_report"], record, source_path=str((ROOT / record["image"]).resolve()),
            runtime=runtime, decoder_version=decoder_version)


@pytest.mark.parametrize("source_path,python_version", [
    ("/home/runner/work/camera-quality-diagnostics/data/samples/stage2-known-qr.png", "3.12.11"),
    (r"E:\checkout\camera-quality-diagnostics\data\samples\stage2-known-qr.png", "3.12.10"),
])
def test_qr_oracle_checks_portable_identity_and_business(source_path, python_version):
    """模拟另一平台/路径；错误身份与错误载荷仍须失败，不能整体忽略元数据。"""
    document = json.loads(ORACLE.read_text(encoding="utf-8"))
    record = document["records"][0]
    stable_before = deepcopy(record["stable"])
    runtime = {"python": python_version, "opencv": cv2.__version__,
               "numpy": np.__version__, "pillow": pillow_version}
    decoder_version = version("zxing-cpp")
    report = label_module.analyze_label(
        STAGE2, expected_file=STAGE2_EXPECTED,
        truth_source=record["stable"]["known_truth"]["source_description"])
    report["source"]["path"] = source_path
    report["provenance"]["runtime"] = dict(runtime)

    def check(candidate):
        _assert_portable_qr_report(candidate, record, source_path=source_path,
                                  runtime=runtime, decoder_version=decoder_version)

    check(report)
    bad_path = deepcopy(report)
    bad_path["source"]["path"] += ".wrong"
    bad_runtime = deepcopy(report)
    bad_runtime["provenance"]["runtime"]["python"] = "incorrect"
    bad_decoder = deepcopy(report)
    bad_decoder["attempts"][0]["decode"]["decoder"]["version"] = "incorrect"
    bad_payload = deepcopy(report)
    bad_payload["attempts"][0]["decode"]["symbols"][0]["payload_base64"] = "YmFk"
    bad_sources = []
    for name in report["provenance"]["source_sha256"]:
        bad_source = deepcopy(report)
        bad_source["provenance"]["source_sha256"][name] = "0" * 64
        bad_sources.append(bad_source)
    missing_sources = deepcopy(report)
    missing_sources["provenance"].pop("source_sha256")
    for candidate in (bad_path, bad_runtime, bad_decoder, bad_payload, missing_sources, *bad_sources):
        with pytest.raises(AssertionError):
            check(candidate)
    assert record["stable"] == stable_before


# --- B08 -------------------------------------------------------------------

def test_real_png_smoke_and_serialization():
    before = sha256(STAGE2.read_bytes()).hexdigest()
    for roi in (None, STAGE2_ROI):
        result = association.analyze_quality_and_qr(STAGE2, roi, STAGE2_EXPECTED, "stage2 独立答案")
        assert result["status"] == "completed", roi
        for measurement in result["measurements"]:
            assert measurement["quality"] is not None, roi
            assert measurement["quality_error"] is None, roi
        assert json.loads(json.dumps(result, allow_nan=False)) == result, roi
    assert sha256(STAGE2.read_bytes()).hexdigest() == before


# --- B11 -------------------------------------------------------------------

def test_no_truth_is_not_correct():
    result = association.analyze_quality_and_qr(SYNTHETIC / "dev-01-clean-module8-A.png")
    assert result["qr_report"]["known_truth"]["status"] == "not_provided"
    assert all(a["truth_status"] == "not_provided" for a in result["associations"])
    rendered = json.dumps(result, ensure_ascii=False)
    assert "correct" not in rendered


# --- B12 -------------------------------------------------------------------

def test_small_region_passthrough():
    bgr = normalized()
    for roi, expected_reasons in (
        ((0, 0, 2, 2), ["sharpness_insufficient_dimensions", "uniformity_insufficient_dimensions"]),
        ((0, 0, 3, 3), ["uniformity_insufficient_dimensions"]),
    ):
        result = association.analyze_quality_and_qr(STAGE2, roi)
        roi_measure = {m["measurement_id"]: m for m in result["measurements"]}["roi"]
        independent = quality_module.analyze_quality(bgr, roi)
        assert roi_measure["quality"] == independent
        assert roi_measure["quality"]["metrics"]["brightness_uniformity"] is None
        assert roi_measure["quality"]["applicability"]["reasons"] == expected_reasons
        assert roi_measure["quality"]["applicability"]["reasons"] == \
            independent["applicability"]["reasons"]
        assert roi_measure["quality"]["metrics"]["brightness"] is not None


# --- B13 -------------------------------------------------------------------

def test_quality_failure_keeps_qr(monkeypatch):
    independent = label_module.analyze_label(STAGE2, STAGE2_ROI)

    def failing(image, roi=None):
        raise quality_module.QualityAnalysisError("invalid_image", "injected quality failure")
    monkeypatch.setattr(association, "analyze_quality", failing)

    result = association.analyze_quality_and_qr(STAGE2, STAGE2_ROI)
    assert result["status"] == "completed_with_errors"
    for measurement in result["measurements"]:
        assert measurement["quality"] is None
        assert set(measurement["quality_error"]) == {"code", "message", "exception_type"}
        assert measurement["quality_error"]["code"] == "invalid_image"
        assert measurement["quality_error"]["exception_type"] == "QualityAnalysisError"
    assert strip_volatile(result["qr_report"]) == strip_volatile(independent)


# --- B14 -------------------------------------------------------------------

def test_timings_are_defined_separately(monkeypatch):
    cases = [
        (STAGE2, None, None, None, False),
        (STAGE2, STAGE2_ROI, STAGE2_EXPECTED, "stage2 独立答案", True),
        (SYNTHETIC / "dev-07-blur-sigma5-C.png", None, SYNTHETIC / "answers" / "C.txt",
         "合成数据集独立答案", True),
    ]
    for image, roi, expected, truth, try_downscale in cases:
        result = association.analyze_quality_and_qr(image, roi, expected, truth,
                                                    try_downscale=try_downscale)
        timings = result["timings"]
        assert set(timings) == {"decode_seconds", "quality_seconds", "total_seconds"}
        assert all(isinstance(timings[key], float) and timings[key] >= 0 for key in timings)
        assert timings["decode_seconds"] == sum(
            attempt["decode"]["duration_seconds"] for attempt in result["qr_report"]["attempts"])
        assert timings["quality_seconds"] == sum(
            measurement["duration_seconds"] for measurement in result["measurements"])
        assert timings["total_seconds"] >= timings["decode_seconds"] + timings["quality_seconds"]

    # 注入夹具（duration 0.0）同样成立，且错误状态也返回 timings
    install_decoder(monkeypatch, lambda td: make_decode("execution_error", try_downscale=td))
    injected = association.analyze_quality_and_qr(STAGE2)
    assert injected["qr_report"]["status"] == "completed_with_errors"
    assert injected["timings"]["decode_seconds"] == 0.0
    assert injected["timings"]["total_seconds"] >= injected["timings"]["quality_seconds"]


def test_total_seconds_includes_provenance_collection(monkeypatch):
    """用确定性时钟计入尾部工作，无 sleep 或机器速度阈值。"""
    clock = {"now": 10.0}
    real_sources = association._source_sha256
    real_runtime = association._runtime_versions

    def sources():
        clock["now"] += 2.0
        return real_sources()

    def runtime():
        clock["now"] += 3.0
        return real_runtime()

    monkeypatch.setattr(association, "perf_counter", lambda: clock["now"])
    monkeypatch.setattr(association, "_source_sha256", sources)
    monkeypatch.setattr(association, "_runtime_versions", runtime)
    result = association.analyze_quality_and_qr(STAGE2)
    assert result["timings"]["total_seconds"] == 5.0
    assert result["timings"]["quality_seconds"] == 0.0


# --- B15 -------------------------------------------------------------------

TOP_LEVEL_FIELDS = {
    "schema_version", "report_type", "association_id", "analyzed_at", "status", "timings",
    "provenance", "read_consistency", "requested_roi", "measurements", "associations",
    "qr_report", "warnings",
}


def test_output_schema_and_provenance(monkeypatch):
    outputs = [
        association.analyze_quality_and_qr(STAGE2),
        association.analyze_quality_and_qr(STAGE2, (0, 0, 2, 2)),
    ]

    def failing(image, roi=None):
        raise quality_module.QualityAnalysisError("invalid_roi", "injected")
    monkeypatch.setattr(association, "analyze_quality", failing)
    outputs.append(association.analyze_quality_and_qr(STAGE2))
    monkeypatch.undo()

    for result in outputs:
        assert set(result) == TOP_LEVEL_FIELDS
        assert result["schema_version"] == 1
        assert result["report_type"] == "quality_qr_association"
        assert result["status"] in {"completed", "completed_with_errors"}
        _assert_native_types(result)
        rendered = json.dumps(result, allow_nan=False)
        assert json.loads(rendered) == result

        provenance = result["provenance"]
        assert provenance["implementation_version"] == "quality-qr-association-1"
        assert provenance["quality_module_version"] is None
        assert provenance["source_sha256"]["quality_qr_analysis.py"] == sha256(
            (ROOT / "src" / "quality_qr_analysis.py").read_bytes()).hexdigest()
        assert provenance["source_sha256"]["quality_analysis.py"] == sha256(
            (ROOT / "src" / "quality_analysis.py").read_bytes()).hexdigest()
        assert set(provenance["runtime"]) == {"python", "opencv", "numpy", "pillow", "zxing_cpp"}


# --- B16 -------------------------------------------------------------------

def _block_bounds(total, parts=4):
    base, extra = divmod(total, parts)
    bounds, start = [], 0
    for index in range(parts):
        size = base + (1 if index < extra else 0)
        bounds.append((start, start + size))
        start += size
    return bounds


def test_measurement_basis_is_original_image(monkeypatch):
    expected_bgr = normalized()
    real = quality_module.analyze_quality
    captured = []

    def capturing(image, roi=None):
        copied = np.array(image, copy=True)
        captured.append((copied, roi))
        return real(image, roi)
    monkeypatch.setattr(association, "analyze_quality", capturing)

    assert association.BASIS == "original_normalized_image_region"

    results = {}
    for try_downscale in (False, True):
        captured.clear()
        results[try_downscale] = association.analyze_quality_and_qr(
            STAGE2, STAGE2_ROI, try_downscale=try_downscale)
        # 整图传 None，ROI 传原图 ROI；实际数组等于独立标准化的完整原图
        assert [roi for _, roi in captured] == [None, STAGE2_ROI]
        for array, _ in captured:
            assert array.shape == expected_bgr.shape and array.dtype == expected_bgr.dtype
            assert np.array_equal(array, expected_bgr)

    # 最终测量区域像素等于对应切片
    x, y, w, h = STAGE2_ROI
    roi_quality = results[False]["measurements"][1]["quality"]
    blocks = roi_quality["metrics"]["brightness_uniformity"]["blocks"]
    row_bounds, column_bounds = _block_bounds(h), _block_bounds(w)
    slice_ = expected_bgr[y:y + h, x:x + w]
    for index, block in enumerate(blocks):
        row, column = divmod(index, 4)
        top, bottom = row_bounds[row]
        left, right = column_bounds[column]
        assert (block["x"], block["y"]) == (x + left, y + top)
        assert (block["width"], block["height"]) == (right - left, bottom - top)
        assert block["mean"] == float(slice_[top:bottom, left:right].mean())

    # 两种 profile 设置得到相同 quality / region / basis
    first, second = results[False]["measurements"], results[True]["measurements"]
    assert [m["basis"] for m in first] == [association.BASIS, association.BASIS]
    assert [m["region"] for m in first] == [m["region"] for m in second]
    assert [m["quality"] for m in first] == [m["quality"] for m in second]


# --- B17 -------------------------------------------------------------------

def test_association_warnings_contract(monkeypatch):
    bgr = normalized()
    normal = association.analyze_quality_and_qr(STAGE2, STAGE2_ROI)
    assert normal["warnings"] == []
    assert normal["measurements"][0]["quality"]["warnings"] == \
        quality_module.analyze_quality(bgr, None)["warnings"]
    assert normal["measurements"][1]["quality"]["warnings"] == \
        quality_module.analyze_quality(bgr, STAGE2_ROI)["warnings"]
    assert normal["qr_report"]["warnings"] == label_module.analyze_label(STAGE2, STAGE2_ROI)["warnings"]

    # 小区域：quality 侧 warning 原样透传，关联层仍为空
    small = association.analyze_quality_and_qr(STAGE2, (0, 0, 2, 2))
    assert small["warnings"] == []
    assert [w["type"] for w in small["measurements"][1]["quality"]["warnings"]] == [
        "measurement_scope", "constant_region", "insufficient_spatial_support"]

    # 解码侧 warning 原样保留，不被合并进关联层
    with_decode_warning = association.analyze_quality_and_qr(
        SYNTHETIC / "dev-07-blur-sigma5-C.png", None, SYNTHETIC / "answers" / "C.txt",
        "合成数据集独立答案", try_downscale=True)
    assert with_decode_warning["warnings"] == []
    assert any(w["code"] == "decode_attempt_errors"
               for w in with_decode_warning["qr_report"]["warnings"])

    # 质量测量失败时关联层仍为空
    def failing(image, roi=None):
        raise quality_module.QualityAnalysisError("invalid_image", "injected")
    monkeypatch.setattr(association, "analyze_quality", failing)
    assert association.analyze_quality_and_qr(STAGE2)["warnings"] == []


# --- B18 -------------------------------------------------------------------

def test_exception_taxonomy(monkeypatch, tmp_path):
    # 输入失败：继续抛出，不返回报告
    with pytest.raises(images.AnalysisError) as caught:
        association.analyze_quality_and_qr(tmp_path / "missing.png")
    assert caught.value.code == "input_not_found"

    # 校验失败：ROI / 解码配置，继续抛出
    with pytest.raises(core.LabelAnalysisError) as caught:
        association.analyze_quality_and_qr(STAGE2, (-1, 0, 4, 4))
    assert caught.value.code == "invalid_roi"
    with pytest.raises(core.LabelAnalysisError) as caught:
        association.analyze_quality_and_qr(STAGE2, try_downscale=1)
    assert caught.value.code == "invalid_decoder_config"

    # 一致性失败：关联层自定义错误码
    original = images.load_normalized_image
    calls = {"count": 0}
    def patched(path):
        bgr, metadata = original(path)
        calls["count"] += 1
        if calls["count"] == 1:
            metadata["source"]["sha256"] = "0" * 64
        return bgr, metadata
    monkeypatch.setattr(images, "load_normalized_image", patched)
    with pytest.raises(QualityQrAssociationError) as caught:
        association.analyze_quality_and_qr(STAGE2)
    assert caught.value.code == "source_changed_between_reads"
    monkeypatch.undo()

    # MemoryError / cv2.error：继续抛出，不得转成 quality_error
    def exhausted(image, roi=None):
        raise MemoryError()
    monkeypatch.setattr(association, "analyze_quality", exhausted)
    with pytest.raises(MemoryError):
        association.analyze_quality_and_qr(STAGE2)

    def cv_failure(image, roi=None):
        raise cv2.error("injected opencv failure")
    monkeypatch.setattr(association, "analyze_quality", cv_failure)
    with pytest.raises(cv2.error):
        association.analyze_quality_and_qr(STAGE2)

    # 仅 QualityAnalysisError 转 quality_error 并保留 QR
    def quality_failure(image, roi=None):
        raise quality_module.QualityAnalysisError("invalid_image", "injected quality failure")
    monkeypatch.setattr(association, "analyze_quality", quality_failure)
    result = association.analyze_quality_and_qr(STAGE2)
    assert result["measurements"][0]["quality_error"]["code"] == "invalid_image"
    assert result["measurements"][0]["quality"] is None
    assert result["status"] == "completed_with_errors"
    assert result["qr_report"]["status"] == "completed"
    assert result["qr_report"]["attempts"][0]["decode"]["status"] == "decoded"
