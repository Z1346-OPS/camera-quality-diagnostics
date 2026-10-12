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


@pytest.mark.parametrize("split", gate.SPLITS)
def test_synthetic_dataset_matches_expectations(split):
    expected = gate.load_expectations().get(split)
    assert expected is not None, f"期望文件中缺少 {split}，请运行 tools/check_evaluation_expectations.py --refresh"

    actual = gate.summarize(gate.run_evaluation(split))
    problems = gate.diff(expected, actual)
    assert not problems, "评测结果与入库期望不一致：\n" + "\n".join(problems)
