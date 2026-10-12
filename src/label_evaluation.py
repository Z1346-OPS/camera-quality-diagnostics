"""Bounded local manifests and reproducible QR evaluation; no network or writes."""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import cv2

if __package__:
    from . import analyze_image as images
    from .analyze_label import analyze_label, read_expected
    from .label_analysis import LabelAnalysisError, check_expected
else:
    import analyze_image as images
    from analyze_label import analyze_label, read_expected
    from label_analysis import LabelAnalysisError, check_expected


MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SAMPLES = 1000
SOURCE_KINDS = {"phone_photo", "screenshot", "synthetic", "unknown"}
SPLITS = {"development", "test"}
OUTCOMES = ("correct", "incorrect", "decoded_unverified", "not_decoded", "decode_error",
            "ambiguous", "conflict", "execution_error", "input_error")


class EvaluationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _require(condition, message, code="invalid_manifest"):
    if not condition:
        raise EvaluationError(code, message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"JSON 重复字段: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise EvaluationError("invalid_manifest", f"JSON 不允许 {value}")


def load_manifest(path):
    """Freeze manifest bytes; paths are relative to its directory, never to CWD."""
    path = Path(path).resolve()
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
    except OSError as error:
        raise EvaluationError("manifest_read_failed", "无法读取样本清单") from error
    _require(len(raw) <= MAX_MANIFEST_BYTES, "清单超过 1 MiB", "manifest_limit_exceeded")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise EvaluationError("invalid_manifest", "清单必须是有效的 UTF-8 JSON") from error
    _require(isinstance(data, dict) and set(data) == {"schema_version", "samples"},
             "清单仅包含 schema_version 和 samples")
    _require(type(data["schema_version"]) is int and data["schema_version"] == 1, "清单版本必须为 1")
    rows = data["samples"]
    _require(isinstance(rows, list) and 0 < len(rows) <= MAX_SAMPLES,
             f"样本数必须在 1 到 {MAX_SAMPLES} 之间", "sample_limit_exceeded")
    required = {"id", "image", "sha256", "label_id", "batch_id", "split", "source_kind", "source"}
    optional = {"expected_file", "expected_sha256", "truth_source", "roi"}
    samples, ids, hashes, groups, label_truths = [], set(), set(), {}, {}
    for row in rows:
        _require(isinstance(row, dict) and required <= row.keys() and row.keys() <= required | optional,
                 "样本字段缺失或包含未知字段")
        _require(all(_text(row[k]) for k in required), "样本必填字段必须是非空文本")
        _require("\x00" not in row["image"], "图片路径包含无效字符")
        _require(row["split"] in SPLITS and row["source_kind"] in SOURCE_KINDS, "无效的 split 或 source_kind")
        _require(_digest(row["sha256"]), "图片 sha256 必须是小写十六进制 64 位")
        _require(row["id"] not in ids, f"重复样本 ID: {row['id']}", "duplicate_sample")
        _require(row["sha256"] not in hashes, "重复图片哈希；同一原图只能列一次", "duplicate_image")
        ids.add(row["id"])
        hashes.add(row["sha256"])
        truth_keys = {"expected_file", "expected_sha256", "truth_source"}
        present = truth_keys & row.keys()
        _require(not present or present == truth_keys, "已知答案需要文件、哈希和独立来源三个字段")
        if present:
            _require(_text(row["expected_file"]) and _text(row["truth_source"]) and
                     _digest(row["expected_sha256"]), "已知答案字段无效")
            _require("\x00" not in row["expected_file"], "答案路径包含无效字符")
            _require(label_truths.get(row["label_id"], row["expected_sha256"]) == row["expected_sha256"],
                     "同一标签声明了不同的已知答案", "inconsistent_truth")
            label_truths[row["label_id"]] = row["expected_sha256"]
        roi = row.get("roi")
        _require("roi" not in row or (isinstance(roi, list) and len(roi) == 4 and
                 all(type(v) is int for v in roi) and min(roi[:2]) >= 0 and min(roi[2:]) > 0),
                 "ROI 必须为非负 x/y 和正宽高的四个整数")
        # All photos of a label, acquisition batch, or identical known payload stay together.
        keys = [("label", row["label_id"]), ("batch", row["batch_id"])]
        if present:
            keys.append(("truth", row["expected_sha256"]))
        for key in keys:
            _require(groups.get(key, row["split"]) == row["split"],
                     "同一标签、采集批次或已知编码跨开发/测试组", "split_leakage")
            groups[key] = row["split"]
        sample = dict(row)
        try:
            sample["image"] = str((path.parent / row["image"]).resolve())
            if present:
                sample["expected_file"] = str((path.parent / row["expected_file"]).resolve())
        except (OSError, ValueError) as error:
            raise EvaluationError("invalid_manifest", "样本文件路径无效") from error
        samples.append(sample)
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "schema_version": 1, "samples": samples}


def _bounded_hash(path, limit):
    try:
        digest, count = sha256(), 0
        with Path(path).open("rb") as stream:
            while True:
                block = stream.read(min(1024 * 1024, limit + 1 - count))
                if not block:
                    break
                count += len(block)
                _require(count <= limit, "样本文件超过资源限制", "sample_file_limit_exceeded")
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise EvaluationError("sample_read_failed", "无法读取样本文件") from error


def _validate_files(sample):
    actual = _bounded_hash(sample["image"], images.MAX_FILE_BYTES)
    _require(actual == sample["sha256"], "原图与清单哈希不一致", "image_hash_mismatch")
    if "expected_file" in sample:
        expected, info = read_expected(sample["expected_file"], sample["truth_source"])
        _require(info["sha256"] == sample["expected_sha256"],
                 "答案文件与清单哈希不一致", "expected_hash_mismatch")
        return expected
    return None


def _observation(decoded, expected, duration):
    truth = check_expected(decoded, expected)
    outcome = truth["status"] if expected is not None else decoded["status"]
    if outcome == "decoded":
        outcome = "decoded_unverified"
    return {"outcome": outcome, "decode_status": decoded["status"], "truth_check": truth,
            "decode_duration_seconds": duration}


def _timing(values):
    if not values:
        return {"count": 0, "median_seconds": None, "p95_seconds": None}
    return {"count": len(values), "median_seconds": median(values),
            "p95_seconds": sorted(values)[ceil(0.95 * len(values)) - 1]}


def summarize_results(results):
    """Every requested sample stays in its group, including input failures."""
    buckets = {}
    for result in results:
        sample = result["sample"]
        for comparison in result["comparisons"]:
            key = (sample["split"], sample["source_kind"], comparison["region"])
            buckets.setdefault(key, []).append((result, comparison))
    summaries = []
    for (split, source_kind, region), entries in sorted(buckets.items()):
        summary = {"split": split, "source_kind": source_kind, "region": region,
                   "total_samples": len(entries), "methods": {}}
        for method in ("baseline", "with_downscale_search"):
            known = [(r, c) for r, c in entries if "expected_file" in r["sample"]]
            counts = Counter(c[method]["outcome"] for _, c in entries)
            correct = sum(c[method]["outcome"] == "correct" for _, c in known)
            summary["methods"][method] = {
                "outcomes": {state: counts[state] for state in OUTCOMES},
                "correctness": {"numerator": correct, "denominator": len(known),
                                "fraction": correct / len(known) if known else None,
                                "unknown_truth_excluded": len(entries) - len(known),
                                "rule": "all_manifest_samples_with_truth_including_failures"},
                "decode_timing": _timing([c[method]["decode_duration_seconds"] for _, c in entries
                                          if c[method]["decode_duration_seconds"] is not None]),
            }
        paired = [c for r, c in entries if "expected_file" in r["sample"] and
                  all(c[m]["outcome"] not in {"input_error", "execution_error"}
                      for m in ("baseline", "with_downscale_search"))]
        summary["paired_change"] = {
            "denominator": len(paired),
            "excluded_unknown_truth_or_input_execution_error": len(entries) - len(paired),
            "improved": sum(c["baseline"]["outcome"] != "correct" and
                            c["with_downscale_search"]["outcome"] == "correct" for c in paired),
            "degraded": sum(c["baseline"]["outcome"] == "correct" and
                            c["with_downscale_search"]["outcome"] != "correct" for c in paired),
        }
        summaries.append(summary)
    return summaries


def evaluate_manifest(path, split=None):
    _require(split is None or split in SPLITS, "split 只能为 development 或 test")
    started = perf_counter()
    manifest = load_manifest(path)  # Validate all splits even if only one is selected.
    samples = [s for s in manifest["samples"] if split is None or s["split"] == split]
    _require(bool(samples), "所选组没有样本", "empty_selection")
    results = []
    for sample in samples:
        result = {"sample": sample, "status": "completed", "error": None, "analysis": None,
                  "comparisons": []}
        try:
            expected = _validate_files(sample)
            analysis = analyze_label(sample["image"], sample.get("roi"), sample.get("expected_file"),
                                     sample.get("truth_source"), try_downscale=True)
            _require(analysis["source"]["sha256"] == sample["sha256"],
                     "分析期间图片改变", "image_hash_mismatch")
            if expected is not None:
                _require(analysis["known_truth"]["sha256"] == sample["expected_sha256"],
                         "分析期间答案改变", "expected_hash_mismatch")
            result["analysis"] = analysis
            for summary in analysis["decode_summaries"]:
                attempts = [analysis["attempts"][i] for i in summary["attempt_indices"]]
                base = attempts[0]["decode"]
                result["comparisons"].append({
                    "region": summary["region"]["kind"],
                    "baseline": _observation(base, expected, base["duration_seconds"]),
                    "with_downscale_search": _observation(summary["decode"], expected,
                        sum(a["decode"]["duration_seconds"] for a in attempts)),
                })
            result["status"] = analysis["status"]
        except (EvaluationError, images.AnalysisError, LabelAnalysisError, OSError, cv2.error, MemoryError) as error:
            execution = isinstance(error, (MemoryError, cv2.error))
            result["status"] = "failed"
            result["error"] = {"code": getattr(error, "code", "resource_exhausted" if isinstance(error, MemoryError)
                                                else "analysis_execution_error" if execution else "sample_read_failed"),
                               "message": str(error), "exception_type": type(error).__name__}
            failed = {"outcome": "execution_error" if execution else "input_error", "decode_status": None,
                      "truth_check": {"status": "not_evaluated"}, "decode_duration_seconds": None}
            result["comparisons"] = [{"region": region, "baseline": dict(failed),
                                      "with_downscale_search": dict(failed)}
                                     for region in (["full_image", "roi"] if "roi" in sample else ["full_image"])]
        results.append(result)
    provenance = images._provenance(("analyze_image.py", "analysis_config.py", "metrics.py", "analyze_label.py",
                                     "label_analysis.py", "label_evaluation.py", "evaluate_labels.py"))
    provenance["implementation_version"] = "local-label-evaluation-1"
    return {"schema_version": 1, "report_type": "label_evaluation", "evaluation_id": uuid4().hex,
            "analyzed_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance,
            "status": "completed_with_errors" if any(r["status"] != "completed" for r in results) else "completed",
            "manifest": manifest, "selected_split": split, "results": results,
            "summaries": summarize_results(results), "duration_seconds": perf_counter() - started,
            "evaluation_policy": {"candidate": "baseline_plus_internal_downscale_search",
                "selection_uses_truth": False, "group_by": ["split", "source_kind", "region"],
                "p95": "nearest_rank", "decoder_timing": "sum_of_attempts_excluding_metrics_and_io",
                "truth": "user_asserted_independent;exact_bytes;unknown_excluded_from_correctness",
                "limits": {"manifest_bytes": MAX_MANIFEST_BYTES, "samples": MAX_SAMPLES,
                           "concurrent_samples": 1},
                "independence": "group_checks_only;capture_history_and_truth_require_human_verification"}}
