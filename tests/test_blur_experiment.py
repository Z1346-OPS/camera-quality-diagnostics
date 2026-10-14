"""Phase 4.3 固定矩阵模糊实验的验收测试。

期望值来自**独立复算**（直接对原图施加协议规定的变换）与**独立调用**既有
`analyze_quality` / `analyze_label`，不由被测生成或汇总函数自身产生。
被测工具位于 `tools/run_blur_experiment.py`，本测试只读清单、基图与答案。
"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import run_blur_experiment as experiment  # noqa: E402

from src import analyze_image as images  # noqa: E402
from src import analyze_label as label_module  # noqa: E402
from src import quality_analysis as quality_module  # noqa: E402


GROUPS = ("development", "test")
EXPECTED_BASES = {
    "development": [("synthetic-qr-v1-development-01", [264, 264], 8),
                    ("synthetic-qr-v1-development-02", [198, 198], 6)],
    "test": [("synthetic-qr-v1-test-01", [264, 264], 8),
             ("synthetic-qr-v1-test-02", [198, 198], 6)],
}
VOLATILE_PATHS = ("analysis_id", "analyzed_at", "analysis_duration_seconds",
                  "provenance.git", "attempts[].decode.duration_seconds")

# 原资产与冻结证据：本实验不得改动其中任何一项。
FROZEN_ASSETS = [
    PROJECT_ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/protected-sha256.txt",
    PROJECT_ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json",
    PROJECT_ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py",
]


def _resolve(path):
    """把工具记录里的路径（项目根相对或绝对）解析为绝对路径。"""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _strip_volatile(report):
    """只去掉 Phase 4.2 明确列出的 volatile 路径，其余业务字段一律参与比较。"""
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


def _digests(paths):
    return {str(path): sha256(path.read_bytes()).hexdigest() for path in paths}


def _asset_paths():
    paths = list(FROZEN_ASSETS)
    for group in GROUPS:
        for base in experiment.load_base_samples(group):
            paths += [base["image"], base["expected"]]
    return paths


@pytest.fixture(scope="module")
def formal_runs(tmp_path_factory):
    """执行两组固定矩阵（共 20 个条件），并记录运行前后的原资产摘要。"""
    before = _digests(_asset_paths())
    root = tmp_path_factory.mktemp("phase-4.3-runs")
    runs = {}
    for group in GROUPS:
        run_dir, document = experiment.run_experiment(group, root, f"{group}-formal")
        runs[group] = (run_dir, document)
    return runs, before, _digests(_asset_paths())


# --- 1. 固定矩阵 ------------------------------------------------------------

def test_fixed_matrix_shape_and_group_mapping():
    assert len(experiment.FIXED_SAMPLES) == 4
    assert tuple(experiment.SIGMAS) == (0, 1, 3, 5, 8)
    assert experiment.PROTOCOL_VERSION == "phase-4.3-blur-v1"

    for group in GROUPS:
        bases = experiment.load_base_samples(group)
        assert [(b["sample_id"], b["size"], b["module_px"]) for b in bases] == \
            EXPECTED_BASES[group]
        for base in bases:
            assert base["group"] == group
            # 答案与来源直接来自清单，不由解码输出生成
            assert base["expected"].is_file()
            assert sha256(base["expected"].read_bytes()).hexdigest() == base["expected_sha256"]
            assert base["truth_source"] == "tools/generate_synthetic_samples.py 预先固定的载荷文本，与解码输出无关"


def test_formal_conditions_and_new_images(tmp_path):
    conditions = []
    for group in GROUPS:
        conditions += experiment.build_conditions(
            experiment.load_base_samples(group), tmp_path / group)
    assert len(conditions) == 20
    degraded = [c for c in conditions if c["sigma"] > 0]
    assert len(degraded) == 16
    for condition in degraded:
        assert _resolve(condition["image_path"]).is_file()
    # 每组恰 8 张新图，sigma=0 不产生新文件
    for group in GROUPS:
        assert len(list((tmp_path / group).glob("*.png"))) == 8
    assert {c["sigma"] for c in conditions} == {0, 1, 3, 5, 8}
    assert len({c["condition_id"] for c in conditions}) == 20


# --- 2. 生成正确性 ----------------------------------------------------------

def test_sigma_zero_references_original_without_reencoding(tmp_path):
    conditions = experiment.build_conditions(
        experiment.load_base_samples("development"), tmp_path / "degraded")
    for condition in (c for c in conditions if c["sigma"] == 0):
        assert condition["generation"]["applied"] is False
        assert condition["image_sha256"] == condition["base"]["image_sha256"]
        assert _resolve(condition["image_path"]) == _resolve(condition["base"]["image"])


def test_degraded_versions_match_independent_transform(tmp_path):
    """对原图独立复算协议变换作对照；串联模糊会得到不同像素，因此该对照非空跑。"""
    border = cv2.BORDER_REFLECT_101
    conditions = experiment.build_conditions(
        experiment.load_base_samples("development"), tmp_path / "degraded")
    for condition in (c for c in conditions if c["sigma"] > 0):
        base_gray = cv2.imread(str(_resolve(condition["base"]["image"])), cv2.IMREAD_GRAYSCALE)
        expected = cv2.GaussianBlur(base_gray, (0, 0), sigmaX=condition["sigma"],
                                    sigmaY=condition["sigma"], borderType=border)
        actual = cv2.imread(str(_resolve(condition["image_path"])), cv2.IMREAD_GRAYSCALE)
        assert actual is not None and actual.dtype == np.uint8 and actual.ndim == 2
        assert actual.shape == base_gray.shape
        np.testing.assert_array_equal(actual, expected)

    # 串联模糊可被区分：先 1 再 4 不等于直接 5
    base_gray = cv2.imread(
        str(_resolve(experiment.load_base_samples("development")[0]["image"])),
        cv2.IMREAD_GRAYSCALE)
    chained = cv2.GaussianBlur(cv2.GaussianBlur(base_gray, (0, 0), 1, 1, border),
                               (0, 0), 4, 4, border)
    direct = cv2.GaussianBlur(base_gray, (0, 0), 5, 5, border)
    assert not np.array_equal(chained, direct)


def test_generation_is_deterministic_and_leaves_originals_alone(tmp_path):
    bases = experiment.load_base_samples("development")
    originals = {b["sample_id"]: sha256(b["image"].read_bytes()).hexdigest() for b in bases}

    first = experiment.build_conditions(bases, tmp_path / "a")
    second = experiment.build_conditions(bases, tmp_path / "b")

    for left, right in zip(first, second):
        assert left["image_sha256"] == right["image_sha256"]
        if left["sigma"] > 0:
            assert _resolve(left["image_path"]).read_bytes() == \
                _resolve(right["image_path"]).read_bytes()

    for base in bases:
        assert sha256(base["image"].read_bytes()).hexdigest() == originals[base["sample_id"]]


# --- 3. 结果正确性 ----------------------------------------------------------

def test_formal_runs_cover_twenty_conditions(formal_runs):
    runs, _, _ = formal_runs
    total = 0
    for group in GROUPS:
        run_dir, document = runs[group]
        assert document["status"] == "completed"
        assert document["planned_conditions"] == 10
        assert document["executed_conditions"] == 10
        assert document["unexecuted_conditions"] == 0
        assert len(document["results"]) == 10
        assert {entry["group"] for entry in document["results"]} == {group}
        assert {entry["sigma"] for entry in document["results"]} == {0, 1, 3, 5, 8}
        assert (run_dir / "experiment-plan.json").is_file()
        assert (run_dir / "report.md").is_file()
        total += document["executed_conditions"]
    assert total == 20

    for group in GROUPS:
        run_dir, document = runs[group]
        # 严格 JSON：写盘的文件必须能读回并与内存文档逐字段一致
        reloaded = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        assert reloaded == document


def test_each_condition_has_one_measurement_and_two_attempts(formal_runs):
    runs, _, _ = formal_runs
    for group in GROUPS:
        for entry in runs[group][1]["results"]:
            report = entry["report"]
            assert len(report["measurements"]) == 1
            assert [m["measurement_id"] for m in report["measurements"]] == ["full_image"]
            assert report["requested_roi"] is None

            attempts = report["qr_report"]["attempts"]
            assert [a["profile"] for a in attempts] == ["baseline", "internal_downscale_search"]
            assert [a["region"]["kind"] for a in attempts] == ["full_image", "full_image"]

            summaries = report["qr_report"]["decode_summaries"]
            assert len(summaries) == 1
            assert summaries[0]["attempt_indices"] == [0, 1]

            # 两个 profile 引用同一条测量：profile 不是独立样本
            assert {a["measurement_id"] for a in report["associations"]} == {"full_image"}
            assert len(report["associations"]) == len(attempts) == 2
            assert len({a["measurement_id"] for a in report["associations"]}) == \
                len(report["measurements"])


def test_quality_matches_independent_call(formal_runs):
    runs, _, _ = formal_runs
    for group in GROUPS:
        for entry in runs[group][1]["results"]:
            image = _resolve(entry["image_path"])
            bgr, _ = images.load_normalized_image(image)
            assert entry["report"]["measurements"][0]["quality"] == \
                quality_module.analyze_quality(bgr, None)


def test_qr_report_matches_independent_call(formal_runs):
    runs, _, _ = formal_runs
    for group in GROUPS:
        for entry in runs[group][1]["results"]:
            independent = label_module.analyze_label(
                _resolve(entry["image_path"]), None, _resolve(entry["expected"]["path"]),
                entry["expected"]["truth_source"], try_downscale=True)
            assert _strip_volatile(entry["report"]["qr_report"]) == _strip_volatile(independent)


def test_report_separates_attempts_from_summary(formal_runs):
    runs, _, _ = formal_runs
    for group in GROUPS:
        text = (runs[group][0] / "report.md").read_text(encoding="utf-8")
        assert "baseline 状态" in text
        assert "internal_downscale_search" not in text or "downscale 状态" in text
        assert "decode_summaries 汇总" in text
        # 必须显式说明第二条 attempt 不是组合的最终结论
        assert "不是" in text and "decode_summaries" in text


# --- 4. 边界与非破坏性 ------------------------------------------------------

def test_refuses_existing_output_directory(tmp_path):
    root = tmp_path / "out"
    (root / "dup").mkdir(parents=True)
    with pytest.raises(experiment.BlurExperimentError, match="拒绝覆盖"):
        experiment.run_experiment("development", root, "dup")


def _fake_manifest(tmp_path, image_sha=None, expected_sha=None):
    """构造一份只含固定样本 ID 的最小清单，用于摘要不匹配的反例。"""
    base = experiment.load_base_samples("development")[0]
    image_copy = tmp_path / "base.png"
    image_copy.write_bytes(base["image"].read_bytes())
    expected_copy = tmp_path / "answer.txt"
    expected_copy.write_bytes(base["expected"].read_bytes())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "samples": [{
            "id": "synthetic-qr-v1-development-01",
            "image": image_copy.name,
            "sha256": image_sha or base["image_sha256"],
            "expected_file": expected_copy.name,
            "expected_sha256": expected_sha or base["expected_sha256"],
            "truth_source": base["truth_source"],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    return manifest


def test_refuses_base_image_digest_mismatch(tmp_path, monkeypatch):
    manifest = _fake_manifest(tmp_path, image_sha="0" * 64)
    monkeypatch.setitem(experiment.MANIFESTS, "development", manifest)
    with pytest.raises(experiment.BlurExperimentError, match="基图摘要"):
        experiment.load_base_samples("development")


def test_refuses_answer_digest_mismatch(tmp_path, monkeypatch):
    manifest = _fake_manifest(tmp_path, expected_sha="0" * 64)
    monkeypatch.setitem(experiment.MANIFESTS, "development", manifest)
    with pytest.raises(experiment.BlurExperimentError, match="独立答案摘要"):
        experiment.load_base_samples("development")


@pytest.mark.parametrize("changed_input", ["image", "answer"])
def test_refuses_changed_inputs_used_by_analysis(tmp_path, monkeypatch, changed_input):
    """文件在分析前变化、分析后恢复，仍须依据实际使用的摘要拒绝结果。"""
    bases = experiment.load_base_samples("development")
    for base in bases:
        answer_copy = tmp_path / f"{base['sample_id']}.txt"
        answer_copy.write_bytes(base["expected"].read_bytes())
        base["expected"] = answer_copy
    monkeypatch.setattr(experiment, "load_base_samples", lambda group: bases)
    real_analyze = experiment.quality_qr_analysis.analyze_quality_and_qr
    changed = {}

    def analyze_with_changed_input(path, roi, expected_file, truth_source, **kwargs):
        target = Path(path if changed_input == "image" else expected_file).resolve()
        eligible = changed_input == "answer" or target.parent.name == "degraded"
        if changed or not eligible:
            return real_analyze(path, roi, expected_file, truth_source, **kwargs)
        assert target.is_relative_to(tmp_path.resolve())
        original = target.read_bytes()
        if changed_input == "image":
            gray = cv2.imread(str(target), cv2.IMREAD_GRAYSCALE)
            gray[0, 0] = 0 if gray[0, 0] else 255
            assert cv2.imwrite(str(target), gray)
        else:
            target.write_bytes(b"CHANGED-ANSWER-DURING-ANALYSIS")
        try:
            report = real_analyze(path, roi, expected_file, truth_source, **kwargs)
        finally:
            target.write_bytes(original)
        changed.update(path=target, original_sha256=sha256(original).hexdigest(), report=report)
        return report

    monkeypatch.setattr(experiment.quality_qr_analysis, "analyze_quality_and_qr",
                        analyze_with_changed_input)
    output_root = tmp_path / "out"
    with pytest.raises(experiment.BlurExperimentError, match="摘要与计划不一致") as caught:
        experiment.run_experiment("development", output_root, "input-change")

    # 事后重读文件已经与计划相同，不能替代报告中实际使用的摘要。
    assert sha256(changed["path"].read_bytes()).hexdigest() == changed["original_sha256"]
    qr = changed["report"]["qr_report"]
    actual_sha = qr["source"]["sha256"] if changed_input == "image" else qr["known_truth"]["sha256"]
    assert actual_sha != changed["original_sha256"]
    run_dir = output_root / "input-change"
    document = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    completed = 1 if changed_input == "image" else 0
    assert document["status"] == "aborted"
    assert document["executed_conditions"] == completed
    assert document["unexecuted_conditions"] == 10 - completed
    assert len(document["results"]) == completed
    assert document["error"]["type"] == "BlurExperimentError"
    assert document["error"]["message"] == str(caught.value)
    failed_id = f"synthetic-qr-v1-development-01-sigma{1 if changed_input == 'image' else 0}"
    assert failed_id in str(caught.value)
    assert "中断" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_aborted_run_is_not_reported_as_complete(tmp_path, monkeypatch):
    real = experiment.execute_condition
    calls = {"count": 0}

    def failing(condition):
        calls["count"] += 1
        if calls["count"] == 3:
            raise MemoryError("injected failure")
        return real(condition)

    monkeypatch.setattr(experiment, "execute_condition", failing)
    root = tmp_path / "out"
    with pytest.raises(MemoryError):
        experiment.run_experiment("development", root, "abort-test")

    document = json.loads((root / "abort-test" / "results.json").read_text(encoding="utf-8"))
    assert document["status"] == "aborted"
    assert document["planned_conditions"] == 10
    assert document["executed_conditions"] == 2
    assert document["unexecuted_conditions"] == 8
    assert document["error"] == {"type": "MemoryError", "message": "injected failure"}
    assert "中断" in (root / "abort-test" / "report.md").read_text(encoding="utf-8")


def test_original_assets_and_frozen_evidence_unchanged(formal_runs):
    _, before, after = formal_runs
    assert before == after
    # 清单本身也必须仍在原处且内容未变
    for group in GROUPS:
        for base in experiment.load_base_samples(group):
            assert sha256(base["image"].read_bytes()).hexdigest() == base["image_sha256"]
            assert sha256(base["expected"].read_bytes()).hexdigest() == base["expected_sha256"]
