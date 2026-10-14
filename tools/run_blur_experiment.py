"""Phase 4.3: fixed-matrix Gaussian-blur experiment over the Phase 4.2 association layer.

The experiment answers one narrow question: for the *same* QR base image, how do the
quality measurements and the two decode profiles (``baseline`` and
``internal_downscale_search``) behave as the applied Gaussian blur strength increases?

The protocol is fixed by the task prompt and is not configurable here:

* four existing clean grayscale PNGs taken from the two synthetic manifests;
* ``sigma`` in ``{0, 1, 3, 5, 8}`` image pixels;
* ``sigma == 0`` references the original file byte-for-byte -- no blur, no re-encode;
* ``sigma > 0`` is generated from the *original* base image each time, never chained;
* OpenCV ``GaussianBlur`` with ``ksize=(0, 0)``, ``sigmaX = sigmaY = sigma``,
  ``borderType = BORDER_REFLECT_101``, saved as a grayscale PNG with compression 6;
* every condition is analysed exactly once with
  ``analyze_quality_and_qr(..., roi=None, expected_file=<manifest answer>,
  truth_source=<manifest source>, try_downscale=True)``.

The ``development`` and ``test`` groups are executed as separate runs and reported
separately.  Output goes to a fresh ``<output-root>/<run-id>/`` directory; an existing
directory is never overwritten.  Business outcomes (``not_decoded``, ``decode_error``,
``ambiguous``, ``conflict``, ``incorrect``, ``execution_error``, ``quality_error``) are
experiment results and are kept as-is -- they are not turned into input errors.

This tool writes files and is **not** a product entry point.  It reads the manifests and
base images, never modifies them, and adds no third-party dependency.

Run from the project root::

    .\\.venv\\Scripts\\python.exe -X utf8 tools\\run_blur_experiment.py --group development
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\run_blur_experiment.py --group test
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as _package_version
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import quality_qr_analysis  # noqa: E402


PROTOCOL_VERSION = "phase-4.3-blur-v1"
SIGMAS = (0, 1, 3, 5, 8)
PNG_COMPRESSION = 6
BORDER_TYPE_NAME = "BORDER_REFLECT_101"
BORDER_TYPE = cv2.BORDER_REFLECT_101
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "experiments" / "phase-4.3-blur-v1"

# The fixed matrix.  Sizes and module widths are the protocol's; they are re-checked
# against the actual files and manifests before anything is generated.
FIXED_SAMPLES = (
    {"group": "development", "sample_id": "synthetic-qr-v1-development-01",
     "size": (264, 264), "module_px": 8},
    {"group": "development", "sample_id": "synthetic-qr-v1-development-02",
     "size": (198, 198), "module_px": 6},
    {"group": "test", "sample_id": "synthetic-qr-v1-test-01",
     "size": (264, 264), "module_px": 8},
    {"group": "test", "sample_id": "synthetic-qr-v1-test-02",
     "size": (198, 198), "module_px": 6},
)

MANIFESTS = {
    "development": ROOT / "data" / "manifests" / "evaluation-synthetic-development.json",
    "test": ROOT / "data" / "manifests" / "evaluation-synthetic-test.json",
}


class BlurExperimentError(RuntimeError):
    """The fixed protocol cannot be honoured: bad manifest, digest mismatch, overwrite."""


def _relative(path):
    """Render a path relative to the project root, or absolute when it lies outside it."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _require(condition, message):
    if not condition:
        raise BlurExperimentError(message)


def _runtime_versions():
    try:
        zxing_version = _package_version("zxing-cpp")
    except PackageNotFoundError:
        zxing_version = None
    return {"python": sys.version.split()[0], "opencv": cv2.__version__,
            "numpy": np.__version__, "pillow": pillow_version, "zxing_cpp": zxing_version}


def load_base_samples(group):
    """Return the fixed base samples for ``group``, validated against its manifest."""
    manifest_path = MANIFESTS[group]
    _require(manifest_path.is_file(), f"清单不存在: {manifest_path}")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {sample["id"]: sample for sample in document["samples"]}

    bases = []
    for spec in FIXED_SAMPLES:
        if spec["group"] != group:
            continue
        sample = by_id.get(spec["sample_id"])
        _require(sample is not None, f"清单缺少固定样本: {spec['sample_id']}")
        image = (manifest_path.parent / sample["image"]).resolve()
        expected = (manifest_path.parent / sample["expected_file"]).resolve()
        _require(image.is_file(), f"基图不存在: {image}")
        _require(expected.is_file(), f"独立答案不存在: {expected}")

        image_sha = sha256(image.read_bytes()).hexdigest()
        _require(image_sha == sample["sha256"],
                 f"基图摘要与清单不一致: {spec['sample_id']}")
        expected_sha = sha256(expected.read_bytes()).hexdigest()
        _require(expected_sha == sample["expected_sha256"],
                 f"独立答案摘要与清单不一致: {spec['sample_id']}")

        gray = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
        _require(gray is not None, f"无法按灰度读取基图: {image}")
        _require(gray.dtype == np.uint8 and gray.ndim == 2,
                 f"基图必须是 uint8 灰度图: {spec['sample_id']}")
        width, height = gray.shape[1], gray.shape[0]
        _require((width, height) == spec["size"],
                 f"基图尺寸与协议不符: {spec['sample_id']} 实际 {width}x{height}")

        bases.append({
            "sample_id": spec["sample_id"], "group": group, "module_px": spec["module_px"],
            "size": [width, height], "image": image, "image_sha256": image_sha,
            "expected": expected, "expected_sha256": expected_sha,
            "truth_source": sample["truth_source"], "gray": gray,
        })
    _require(len(bases) == 2, f"{group} 组的固定基图数量不是 2")
    return bases


def blur_gray(gray, sigma):
    """Apply the fixed Gaussian blur to a uint8 grayscale array (``sigma`` must be > 0)."""
    _require(sigma > 0, "sigma=0 必须直接引用原图，不得调用模糊")
    return cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=BORDER_TYPE)


def write_gray_png(path, gray):
    """Write a uint8 grayscale array as PNG with the fixed compression parameter."""
    if not cv2.imwrite(str(path), gray, [int(cv2.IMWRITE_PNG_COMPRESSION), PNG_COMPRESSION]):
        raise BlurExperimentError(f"无法写入 PNG: {path}")


def build_conditions(bases, degraded_dir):
    """Generate the degraded PNGs and return the condition list (metadata only)."""
    degraded_dir = Path(degraded_dir)
    degraded_dir.mkdir(parents=True, exist_ok=True)
    conditions = []
    for base in bases:
        for sigma in SIGMAS:
            if sigma == 0:
                image_path = base["image"]
                image_sha = base["image_sha256"]
                generation = {"applied": False, "source": "original_base_image",
                              "reason": "sigma=0 直接引用原图：不模糊、不重新编码"}
            else:
                image_path = degraded_dir / f"{base['sample_id']}-sigma{sigma}.png"
                write_gray_png(image_path, blur_gray(base["gray"], sigma))
                image_sha = sha256(image_path.read_bytes()).hexdigest()
                generation = {"applied": True, "source": "original_base_image",
                              "operation": "cv2.GaussianBlur", "ksize": [0, 0],
                              "sigma_x": sigma, "sigma_y": sigma,
                              "border_type": BORDER_TYPE_NAME,
                              "png_compression": PNG_COMPRESSION}
            conditions.append({
                "condition_id": f"{base['sample_id']}-sigma{sigma}",
                "group": base["group"], "sigma": sigma,
                "base": {"sample_id": base["sample_id"], "group": base["group"],
                         "module_px": base["module_px"], "size": base["size"],
                         "image": _relative(base["image"]),
                         "image_sha256": base["image_sha256"]},
                "expected": {"path": _relative(base["expected"]),
                             "sha256": base["expected_sha256"],
                             "truth_source": base["truth_source"]},
                "generation": generation,
                "image_path": _relative(image_path), "image_sha256": image_sha,
                "_absolute_image": Path(image_path).resolve(),
                "_absolute_expected": Path(base["expected"]).resolve(),
            })
    return conditions


def execute_condition(condition):
    """Run one condition through the Phase 4.2 association layer, unchanged."""
    report = quality_qr_analysis.analyze_quality_and_qr(
        condition["_absolute_image"], None, condition["_absolute_expected"],
        condition["expected"]["truth_source"], try_downscale=True)
    # 绑定计划与实际参与分析的字节；事后重读文件可能已恢复，不能替代此检查。
    qr_report = report["qr_report"]
    _require(qr_report["source"]["sha256"] == condition["image_sha256"],
             f"分析图片摘要与计划不一致: {condition['condition_id']}")
    _require(qr_report["known_truth"]["sha256"] == condition["expected"]["sha256"],
             f"分析答案摘要与计划不一致: {condition['condition_id']}")
    return {
        "condition_id": condition["condition_id"], "group": condition["group"],
        "sigma": condition["sigma"], "base": condition["base"],
        "expected": condition["expected"], "generation": condition["generation"],
        "image_path": condition["image_path"], "image_sha256": condition["image_sha256"],
        "report": report,
    }


def _plan_document(group, run_id, conditions):
    return {
        "protocol_version": PROTOCOL_VERSION, "experiment_id": run_id, "group": group,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "implementation": {"module": _relative(__file__),
                           "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest()},
        "environment": _runtime_versions(),
        "fixed_protocol": {
            "sigmas": list(SIGMAS), "sigma_0": "references the original image unchanged",
            "generation": {"operation": "cv2.GaussianBlur", "ksize": [0, 0],
                           "sigma_x": "sigma", "sigma_y": "sigma",
                           "border_type": BORDER_TYPE_NAME,
                           "png_compression": PNG_COMPRESSION,
                           "source": "each version generated from the original base image, never chained"},
            "analysis": {"function": "quality_qr_analysis.analyze_quality_and_qr",
                         "roi": None, "try_downscale": True,
                         "expected_file": "manifest expected_file",
                         "truth_source": "manifest truth_source"},
        },
        "conditions": [{key: value for key, value in condition.items()
                        if not key.startswith("_")} for condition in conditions],
    }


def _count_statuses(results):
    counts = {"baseline": {}, "internal_downscale_search": {}, "summary": {}}
    for entry in results:
        attempts = entry["report"]["qr_report"]["attempts"]
        for attempt in attempts:
            bucket = counts[attempt["profile"]]
            bucket[attempt["decode"]["status"]] = bucket.get(attempt["decode"]["status"], 0) + 1
        summaries = entry["report"]["qr_report"]["decode_summaries"]
        for summary in summaries:
            status = summary["decode"]["status"]
            counts["summary"][status] = counts["summary"].get(status, 0) + 1
    return counts


def _fmt(value, digits=4):
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_report(group, run_id, conditions, results, aborted_error):
    """Render the short Markdown report: one row per base image and sigma."""
    by_id = {entry["condition_id"]: entry for entry in results}
    lines = [
        f"# Phase 4.3 固定矩阵模糊实验报告（{group} 组）", "",
        f"- 协议版本：`{PROTOCOL_VERSION}`",
        f"- 实验 ID：`{run_id}`",
        f"- 组别：`{group}`（开发组与验证组分别执行、分别报告；验证组已在历史回归中出现，**不称盲测**）",
        f"- 状态：{'**完成**' if aborted_error is None else '**中断（未完成全部条件）**'}",
        f"- 本组条件数：{len(conditions)}（2 张基图 × 5 个 sigma）",
        f"- 全实验规模：20 个条件 / 4 张基图；本报告只覆盖本组",
        "",
        "本实验不输出准确率、通用阈值、故障原因或跨场景有效性结论。",
        "σ=0 直接引用原图；σ>0 每次从原图独立生成，不串联叠加。",
        "每个条件恰一条质量测量、两条解码尝试；**尝试数不是独立样本数**。",
        "",
    ]
    if aborted_error is not None:
        lines += [f"> 中断原因：`{aborted_error['type']}`：{aborted_error['message']}",
                  f"> 已执行 {len(results)} / {len(conditions)} 个条件。", ""]

    for base_id in sorted({condition["base"]["sample_id"] for condition in conditions}):
        base_conditions = [c for c in conditions if c["base"]["sample_id"] == base_id]
        spec = base_conditions[0]["base"]
        lines += [
            f"## 基图 `{base_id}`", "",
            f"- 组别：`{spec['group']}`；尺寸 {spec['size'][0]}×{spec['size'][1]}；模块宽度 {spec['module_px']} px",
            f"- 原图：`{spec['image']}`（SHA-256 `{spec['image_sha256'][:16]}…`）",
            f"- 独立答案：`{base_conditions[0]['expected']['path']}`",
            "",
            "| σ | 清晰度 | 亮度 | 对比度 | 块间均值极差 | baseline 状态 | baseline 真值 | downscale 状态 | downscale 真值 | decode_summaries 汇总 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for condition in base_conditions:
            entry = by_id.get(condition["condition_id"])
            if entry is None:
                lines.append(f"| {condition['sigma']} | 未执行 | — | — | — | — | — | — | — | — |")
                continue
            report = entry["report"]
            quality = report["measurements"][0]["quality"]
            metrics = quality["metrics"] if quality else {}
            uniformity = metrics.get("brightness_uniformity") or {}
            attempts = {a["profile"]: a for a in report["qr_report"]["attempts"]}
            baseline = attempts.get("baseline", {})
            downscale = attempts.get("internal_downscale_search", {})
            summaries = report["qr_report"]["decode_summaries"]
            summary_status = summaries[0]["decode"]["status"] if summaries else "—"
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                condition["sigma"],
                _fmt(metrics.get("sharpness")), _fmt(metrics.get("brightness")),
                _fmt(metrics.get("contrast")), _fmt(uniformity.get("mean_range")),
                baseline.get("decode", {}).get("status", "—"),
                baseline.get("truth_check", {}).get("status", "—"),
                downscale.get("decode", {}).get("status", "—"),
                downscale.get("truth_check", {}).get("status", "—"),
                summary_status))
        lines += [
            "",
            "> 「downscale 状态」是第二条 attempt 自身的结果，**不是**组合的最终结论；",
            "> 最终汇总以 `decode_summaries` 列为准。完整四项质量输出见 `results.json`。",
            "",
        ]

    counts = _count_statuses(results)
    lines += ["## 本组状态计数", "",
              f"仅代表本组 {len(conditions)} 个条件与 {len({c['base']['sample_id'] for c in conditions})} 张基图；",
              "全实验为 20 个条件与 4 张基图，本表不能外推。", "",
              "| 层 | 状态 | 数量 |", "| --- | --- | --- |"]
    for layer in ("baseline", "internal_downscale_search", "summary"):
        for status, count in sorted(counts[layer].items()):
            lines.append(f"| {layer} | {status} | {count} |")
    lines += ["", "## 限制", "",
              "- 只做固定矩阵的模糊实验，不含其他退化类型、多因素组合或 ROI 实验。",
              "- 不要求清晰度或识读结果随 sigma 单调变化；每张基图只在本基图内部比较。",
              "- 耗时沿用 Phase 4.2 的定义，本实验不新增性能统计体系。",
              "- 全部结论限于本机、项目 `.venv` 与本次运行。", ""]
    return "\n".join(lines)


def run_experiment(group, output_root, run_id):
    """Execute one group's fixed matrix into a fresh ``<output_root>/<run_id>`` directory."""
    _require(group in MANIFESTS, f"未知组别: {group}")
    bases = load_base_samples(group)

    run_dir = Path(output_root) / run_id
    if run_dir.exists():
        raise BlurExperimentError(f"输出目录已存在，拒绝覆盖: {run_dir}")
    run_dir.mkdir(parents=True)

    conditions = build_conditions(bases, run_dir / "degraded")
    (run_dir / "experiment-plan.json").write_text(
        json.dumps(_plan_document(group, run_id, conditions), ensure_ascii=False,
                   indent=2, allow_nan=False) + "\n", encoding="utf-8")

    results = []
    try:
        for condition in conditions:
            results.append(execute_condition(condition))
    finally:
        # No broad ``except``: the original exception propagates after the partial
        # record is written, so an interrupted run is never reported as complete.
        error = sys.exc_info()[1]
        aborted_error = None if error is None else {
            "type": type(error).__name__, "message": str(error)}
        document = {
            "protocol_version": PROTOCOL_VERSION, "experiment_id": run_id, "group": group,
            "status": "completed" if aborted_error is None else "aborted",
            "planned_conditions": len(conditions), "executed_conditions": len(results),
            "unexecuted_conditions": len(conditions) - len(results),
            "environment": _runtime_versions(),
            "results": [{key: value for key, value in entry.items()} for entry in results],
        }
        if aborted_error is not None:
            document["error"] = aborted_error
        (run_dir / "results.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        (run_dir / "report.md").write_text(
            render_report(group, run_id, conditions, results, aborted_error),
            encoding="utf-8")

    return run_dir, document


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phase 4.3 固定矩阵高斯模糊实验（复用 Phase 4.2 关联层）")
    parser.add_argument("--group", choices=sorted(MANIFESTS), required=True,
                        help="执行哪一组；开发组与验证组分别执行、分别报告")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT,
                        help="实验产物根目录；每轮在其下新建 <run-id> 子目录")
    parser.add_argument("--run-id", help="本轮目录名；缺省为 <group>-<UTC 时间戳>")
    args = parser.parse_args(argv)

    run_id = args.run_id or (
        f"{args.group}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    try:
        run_dir, document = run_experiment(args.group, args.output_root, run_id)
    except BlurExperimentError as error:
        print(f"实验失败: {error}", file=sys.stderr)
        return 2
    print(f"实验完成: {run_dir}")
    print(f"  条件 {document['executed_conditions']}/{document['planned_conditions']}"
          f"，状态 {document['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
