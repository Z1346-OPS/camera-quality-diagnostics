"""Regression gate for the synthetic QR dataset: outcomes must match the recorded values.

Why this gate does not trust the exit code
------------------------------------------
``src/evaluate_labels.py`` returns exit code 2 for a hard failure (``EvaluationError``,
``OSError``, ``MemoryError``) **and** for the business outcome ``completed_with_errors``
(samples that are expected not to decode).  A CI step cannot tell those two apart from the
exit code alone, so this gate accepts exit codes 0 and 2 but *judges the JSON report*: it
compares ``status``, every per-method outcome counter, the correctness denominators and the
paired change against committed expectations.  Any drift fails with a per-item diff instead
of a bare "exit 2".

``--refresh`` records the current behaviour as the new expectation.  That is a deliberate,
reviewable act: it changes what the project claims the dataset does.

Usage (from the project root):

    .\\.venv\\Scripts\\python.exe -X utf8 tools\\check_evaluation_expectations.py
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\check_evaluation_expectations.py --split test
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\check_evaluation_expectations.py --refresh
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
EXPECTATIONS_PATH = MANIFEST_DIR / "evaluation-synthetic-expectations.json"
SPLITS = ("development", "test")
EXPECTATIONS_SCHEMA_VERSION = 1
# exit 0 = completed, exit 2 = completed_with_errors (a business outcome, not a crash)
ACCEPTED_EXIT_CODES = (0, 2)


class GateError(RuntimeError):
    pass


def manifest_path(split):
    return MANIFEST_DIR / f"evaluation-synthetic-{split}.json"


def run_evaluation(split):
    """Run the real CLI entry point and return its JSON report."""
    with tempfile.TemporaryDirectory() as workdir:
        output = Path(workdir) / f"report-{split}.json"
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "src.evaluate_labels", str(manifest_path(split)),
             "--split", split, "--output", str(output)],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
            # The child runs with -X utf8 and prints JSON with ensure_ascii=False, so its
            # output is always UTF-8.  Decoding it with the locale codec breaks on a GBK
            # Windows console (and only there -- Linux CI would never reveal it).
            encoding="utf-8", errors="replace")
        if completed.returncode not in ACCEPTED_EXIT_CODES:
            message = (completed.stderr or completed.stdout or "").strip().splitlines()
            detail = message[-1] if message else "无输出"
            raise GateError(f"评测进程异常退出 {completed.returncode}: {detail}")
        if not output.exists():
            raise GateError("评测进程没有生成报告 JSON（脚本异常不能只用退出码判断）")
        return json.loads(output.read_text(encoding="utf-8"))


def summarize(report):
    """Keep only the values the gate pins; timings and IDs are expected to vary."""
    summary = report["summaries"][0]
    return {
        "status": report["status"],
        "total_samples": summary["total_samples"],
        "methods": {
            name: {"outcomes": dict(method["outcomes"]),
                   "denominator": method["correctness"]["denominator"]}
            for name, method in sorted(summary["methods"].items())
        },
        "paired_change": dict(summary["paired_change"]),
    }


def diff(expected, actual, prefix=""):
    """Recursively compare nested dicts of scalars and return readable differences."""
    problems = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{prefix}: 期望映射，实际为 {type(actual).__name__}"]
        for key in sorted(set(expected) | set(actual)):
            label = f"{prefix}.{key}" if prefix else key
            if key not in expected:
                problems.append(f"{label}: 期望中没有这一项，实际为 {actual[key]!r}")
            elif key not in actual:
                problems.append(f"{label}: 实际结果缺少这一项（期望 {expected[key]!r}）")
            else:
                problems.extend(diff(expected[key], actual[key], label))
        return problems
    if expected != actual:
        problems.append(f"{prefix}: 期望 {expected!r}，实际 {actual!r}")
    return problems


def load_expectations():
    if not EXPECTATIONS_PATH.exists():
        return {}
    data = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    return data.get("splits", {})


def save_expectations(splits):
    payload = {
        "schema_version": EXPECTATIONS_SCHEMA_VERSION,
        "note": ("合成数据集 synthetic-qr-v1 的入库评测期望。由 tools/check_evaluation_expectations.py "
                 "--refresh 生成；数值变化必须由人工确认后随提交更新。"),
        "splits": splits,
    }
    EXPECTATIONS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")


def describe(split, report):
    summary = report["summaries"][0]
    print(f"\n=== {split} ===")
    print(f"  样本 {summary['total_samples']}   status={report['status']}")
    for name, method in sorted(summary["methods"].items()):
        correctness = method["correctness"]
        counters = "  ".join(f"{key}={value}" for key, value in sorted(method["outcomes"].items()) if value)
        print(f"  {name:<22} 正确 {correctness['numerator']}/{correctness['denominator']}   {counters}")
    paired = summary["paired_change"]
    print(f"  paired_change: improved={paired['improved']} degraded={paired['degraded']} "
          f"分母={paired['denominator']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验合成数据集的评测结果与入库期望完全一致")
    parser.add_argument("--split", choices=SPLITS + ("all",), default="all")
    parser.add_argument("--refresh", action="store_true",
                        help="把当前结果写回期望文件（人工确认后再提交）")
    args = parser.parse_args(argv)

    splits = SPLITS if args.split == "all" else (args.split,)
    expectations = load_expectations()
    failures = 0

    for split in splits:
        report = run_evaluation(split)
        describe(split, report)
        actual = summarize(report)
        if args.refresh:
            expectations[split] = actual
            print("  -> 已记录为期望值")
            continue
        expected = expectations.get(split)
        if expected is None:
            print("  ❌ 期望文件里没有这个 split：先运行 --refresh 并提交")
            failures += 1
            continue
        problems = diff(expected, actual)
        if problems:
            print(f"  ❌ 与入库期望有 {len(problems)} 处不一致：")
            for problem in problems:
                print(f"     - {problem}")
            failures += len(problems)
        else:
            print("  ✅ 与入库期望完全一致")

    if args.refresh:
        save_expectations(expectations)
        print(f"\n期望已写入 {EXPECTATIONS_PATH.relative_to(PROJECT_ROOT)}（请人工确认后提交）")
        return 0
    if failures:
        print(f"\n闸门失败：{failures} 处不一致。行为确实变了就 --refresh 后提交，否则修代码。")
        return 1
    print("\n闸门通过：数据集行为与入库期望一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
