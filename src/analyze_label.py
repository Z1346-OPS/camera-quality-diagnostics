"""Local full-image / ROI QR baseline, preserving original evidence."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

import cv2

if __package__:
    from . import analyze_image as images
    from .label_analysis import LabelAnalysisError, DECODER_CONFIG, select_region, decode_qr, summarize_decodes, check_expected
else:
    import analyze_image as images
    from label_analysis import LabelAnalysisError, DECODER_CONFIG, select_region, decode_qr, summarize_decodes, check_expected


MAX_EXPECTED_BYTES = 64 * 1024


def read_expected(path, truth_source):
    if path is None:
        if truth_source is not None:
            raise LabelAnalysisError("invalid_truth", "指定真值来源时必须同时指定 --expected-file")
        return None, {"status": "not_provided"}
    if not isinstance(truth_source, str) or not truth_source.strip():
        raise LabelAnalysisError("invalid_truth", "已知答案必须用 --truth-source 说明独立来源")
    try:
        with Path(path).open("rb") as stream:
            contents = stream.read(MAX_EXPECTED_BYTES + 1)
    except OSError as error:
        raise LabelAnalysisError("expected_read_failed", "无法读取已知答案文件") from error
    if len(contents) > MAX_EXPECTED_BYTES:
        raise LabelAnalysisError("expected_limit_exceeded", "已知答案文件超过 64 KiB")
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LabelAnalysisError("invalid_expected_encoding", "已知答案文件必须是 UTF-8") from error
    # No strip, BOM removal, URL normalization or Unicode normalization.
    return contents, {"status": "provided", "source_description": truth_source,
                      "sha256": sha256(contents).hexdigest(), "text": text,
                      "encoding": "utf-8", "verification": "user_asserted_independent"}


def analyze_label(path, roi=None, expected_file=None, truth_source=None, *, try_downscale=False):
    if type(try_downscale) is not bool:
        raise LabelAnalysisError("invalid_decoder_config", "try_downscale 必须是布尔值")
    started = perf_counter()
    expected, truth = read_expected(expected_file, truth_source)
    bgr, metadata = images.load_normalized_image(path)
    selected, selected_region = select_region(bgr, roi)
    _, full_region = select_region(bgr)
    config = {"image": images.image_analysis_config(), "decoder": dict(DECODER_CONFIG),
              "roi": selected_region, "roi_coordinates": "exif_normalized_image;xywh;right_bottom_exclusive",
              "expected_comparison": "exact_payload_bytes", "max_expected_bytes": MAX_EXPECTED_BYTES,
              "additional_downscale_search": try_downscale,
              "decode_summary_policy": "execution_error_then_ambiguity_then_payload_consensus"}
    profiles = [("baseline", False)] + ([("internal_downscale_search", True)] if try_downscale else [])
    config["decoder_attempts"] = [
        {"profile": name, "config": {**DECODER_CONFIG, "try_downscale": enabled}}
        for name, enabled in profiles
    ]
    attempts = []
    summaries = []
    for frame, region in [(bgr, full_region)] + ([(selected, selected_region)] if roi is not None else []):
        metrics = images.calculate_image_metrics(frame)
        start_index = len(attempts)
        decodes = []
        for profile, enabled in profiles:
            # Keep the baseline call compatible with existing callers and tests.
            decoded = decode_qr(frame, region, try_downscale=True) if enabled else decode_qr(frame, region)
            decodes.append(decoded)
            attempts.append({"region": region, "profile": profile, "metrics": metrics,
                             "decode": decoded, "truth_check": check_expected(decoded, expected)})
        summary = summarize_decodes(decodes)
        if summary["selected_attempt_index"] is not None:
            summary["selected_attempt_index"] += start_index
        summary["failed_attempt_indices"] = [i + start_index for i in summary["failed_attempt_indices"]]
        summaries.append({"region": region, "attempt_indices": list(range(start_index, len(attempts))),
                          "decode": summary, "truth_check": check_expected(summary, expected)})
    provenance = images._provenance(("analyze_image.py", "analysis_config.py", "metrics.py",
                                     "analyze_label.py", "label_analysis.py"))
    provenance["implementation_version"] = "local-label-analysis-2"
    # Failed attempts remain intact, even when an additional attempt reads the code.
    failed_indices = [i for i, a in enumerate(attempts)
                      if a["decode"]["status"] in {"decode_error", "execution_error"}]
    if failed_indices:
        metadata["warnings"].append({"code": "decode_attempt_errors",
                                     "message": "部分解码尝试失败，详见 attempts",
                                     "attempt_indices": failed_indices})
    execution_failed = any(a["decode"]["status"] in {"execution_error", "decode_error"} for a in summaries)
    return {"schema_version": 2, "report_type": "label_baseline", "analysis_id": uuid4().hex,
            "status": "completed_with_errors" if execution_failed else "completed",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "analysis_duration_seconds": perf_counter() - started,
            "provenance": provenance, **metadata, "analysis_config": config,
            "config_sha256": sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest(),
            "known_truth": truth, "attempts": attempts, "decode_summaries": summaries}


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读本地 QR 基线：整图、人工 ROI 与独立答案核对")
    parser.add_argument("image", type=Path)
    parser.add_argument("--roi", nargs=4, type=int, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    parser.add_argument("--expected-file", type=Path, help="独立已知答案的 UTF-8 文件；不去除末尾换行")
    parser.add_argument("--truth-source", help="独立答案来源描述，不能是本次解码输出")
    parser.add_argument("--try-downscale", action="store_true",
                        help="保留原基线，并额外尝试解码器内部降采样搜索；结果汇总见 decode_summaries")
    parser.add_argument("--output", type=Path, help="独占新建结果 JSON；不覆盖")
    args = parser.parse_args(argv)
    try:
        result = analyze_label(args.image, args.roi, args.expected_file, args.truth_source,
                               try_downscale=args.try_downscale)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
    except (images.AnalysisError, LabelAnalysisError, OSError, ValueError, cv2.error, MemoryError) as error:
        if isinstance(error, (images.AnalysisError, LabelAnalysisError)):
            code = error.code
        elif isinstance(error, FileExistsError):
            code = "output_exists"
        elif isinstance(error, PermissionError):
            code = "output_access_denied"
        elif isinstance(error, OSError):
            code = "output_write_failed"
        elif isinstance(error, MemoryError):
            code = "resource_exhausted"
        else:
            code = "analysis_failed"
        print(f"分析失败 [{code}]: {error}", file=sys.stderr)
        return 2
    print(rendered)
    return 2 if result["status"] == "completed_with_errors" else 0


if __name__ == "__main__":
    sys.exit(main())
