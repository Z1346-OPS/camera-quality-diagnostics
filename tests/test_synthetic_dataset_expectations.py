"""Keep the synthetic dataset's evaluation outcomes pinned to committed expectations.

These cases call the gate in ``tools/check_evaluation_expectations.py`` so that a plain
``pytest`` run -- locally and in CI -- fails when the dataset's behaviour drifts, instead of
relying on the evaluator's exit code (which is 2 both for a business outcome and for a crash).
"""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import check_evaluation_expectations as gate  # noqa: E402
from src.label_evaluation import summarize_results  # noqa: E402


@pytest.mark.parametrize("split", gate.SPLITS)
def test_synthetic_dataset_matches_expectations(split):
    expected = gate.load_expectations().get(split)
    assert expected is not None, f"期望文件中缺少 {split}，请运行 tools/check_evaluation_expectations.py --refresh"

    report = gate.run_evaluation(split)
    actual = gate.summarize(report)
    problems = gate.diff(expected, actual)
    assert not problems, "评测结果与入库期望不一致：\n" + "\n".join(problems)

    # Reordering is harmless. Swapping a clean and blurred sample's outcomes is not,
    # even when recomputing the aggregate counters produces exactly the same totals.
    report["results"].reverse()
    assert gate.summarize(report) == actual
    by_id = {row["sample"]["id"]: row for row in report["results"]}
    clean_id = f"synthetic-qr-v1-{split}-01"
    blur_id = f"synthetic-qr-v1-{split}-07"
    clean, blur = by_id[clean_id], by_id[blur_id]
    clean["comparisons"], blur["comparisons"] = blur["comparisons"], clean["comparisons"]
    report["summaries"] = summarize_results(report["results"])
    differences = gate.diff(expected, gate.summarize(report))
    assert {item.split(": ", 1)[0] for item in differences} == {
        f"samples.{ident}.regions.full_image.{method}"
        for ident in (clean_id, blur_id)
        for method in ("baseline", "with_downscale_search")
    }
