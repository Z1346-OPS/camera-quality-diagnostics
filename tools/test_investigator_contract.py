"""两个本地仓库的可选联合回归。运行方式见 docs/tasks/investigator-contract.md。"""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from tests import test_review_capture as fixtures
from tests.test_capture_task import Harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def assistant(monkeypatch):
    checkout = Path(os.environ["INVESTIGATOR_ROOT"]).resolve()
    if not (checkout / "src/investigator/reports.py").is_file():
        pytest.fail("INVESTIGATOR_ROOT 必须指向本次核验的排查助手仓库")
    monkeypatch.syspath_prepend(str(checkout / "src"))
    from investigator import explain, export, reports, session

    return explain.explain_report, export, reports.load_report, session.Session()


def review_cli(task_dir, target, expected_exit):
    completed = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(ROOT / "src/review_capture.py"), str(task_dir)],
        capture_output=True,
    )
    assert completed.returncode == expected_exit, completed.stderr.decode("utf-8", errors="replace")
    target.write_bytes(completed.stdout)
    return target


def test_capture_report_replay_and_scope(tmp_path, monkeypatch, assistant):
    explain, export, load, investigation = assistant
    frame = np.full((4, 5, 3), 100, dtype=np.uint8)
    capture = Harness(tmp_path, [(0.2, frame), (1.2, frame), (2.2, frame)], duration=2, interval=1)
    capture.run()
    task = load(capture.output_dir / "capture_task.json")
    original = load(review_cli(capture.output_dir, tmp_path / "original.json", 0))
    assert task.get("run_id") == original.get("run_id") and not task.warnings
    investigation.load_primary(original, explain(original))

    def add(path):
        report = load(path)
        return investigation.add_addition(report, explain(report))

    # 构造同批次不同范围的独立输入副本；仅修改临时目录中的合成数据。
    monkeypatch.setattr(fixtures, "uuid4", lambda: UUID(task.get("run_id")))
    missing_dir, run_id, _ = fixtures.make_task(tmp_path, (1, 2), name="missing")
    fixtures.png_path(missing_dir, run_id, 2).unlink()
    add(review_cli(missing_dir, tmp_path / "missing.json", 1))
    partial_dir, _, _ = fixtures.make_task(tmp_path, (1,), name="partial")
    add(review_cli(partial_dir, tmp_path / "partial.json", 0))
    replay = tmp_path / "old-reformatted.json"
    replay.write_text(json.dumps(original.data), encoding="utf-8")
    assert add(replay).is_repeat
    assert [p.frame for p in investigation.unresolved_review_problems()] == [2]
    pending = export.save_markdown(investigation, tmp_path / "pending.md")
    assert "未解决" in pending.read_text(encoding="utf-8")

    restored = add(review_cli(capture.output_dir, tmp_path / "restored.json", 0))
    assert not restored.is_repeat and not investigation.unresolved_review_problems()
    assert investigation.investigation_summary()[0] == "范围内通过"
    preview = export.render_markdown(investigation)
    saved = export.save_markdown(investigation, tmp_path / "restored.md", payload=preview)
    assert saved.read_text(encoding="utf-8") == preview

    global_dir, _, _ = fixtures.make_task(tmp_path, (1, 2), name="global")
    fixtures.drop_quality_frame(global_dir, 2)
    problem = load(review_cli(global_dir, tmp_path / "global.json", 1))
    investigation.load_primary(problem, explain(problem))
    other_dir, _, _ = fixtures.make_task(tmp_path, (3, 4), name="other-frames")
    assert add(review_cli(other_dir, tmp_path / "other.json", 0)).recheck_result == "证据不足"
    assert investigation.unresolved_review_problems()
    assert add(review_cli(capture.output_dir, tmp_path / "covered.json", 0)).recheck_result == "范围内通过"
    assert not investigation.unresolved_review_problems()


def test_qr_two_answers_and_missing_identity(tmp_path, assistant):
    explain, _, load, investigation = assistant
    source = ROOT / "data/samples/stage2-known-qr.png"
    actual_answer = source.with_suffix(".expected.txt")
    wrong_answer = tmp_path / "wrong.txt"
    wrong_answer.write_text("different", encoding="utf-8")
    reports = []
    for answer, name in ((wrong_answer, "wrong"), (actual_answer, "correct")):
        target = tmp_path / f"{name}.json"
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "src/analyze_label.py"),
                        str(source), "--expected-file", str(answer), "--truth-source", "contract test",
                        "--output", str(target)], check=True, capture_output=True)
        reports.append(load(target))
    first, second = reports
    assert first.get("decode_summaries")[0]["truth_check"]["status"] == "incorrect"
    assert second.get("decode_summaries")[0]["truth_check"]["status"] == "correct"
    investigation.load_primary(first, explain(first))
    assert investigation.add_addition(second, explain(second)).recheck_result == "不可比较"
    incomplete = json.loads((tmp_path / "correct.json").read_bytes())
    del incomplete["known_truth"]["sha256"]
    target = tmp_path / "no-answer-identity.json"
    target.write_text(json.dumps(incomplete), encoding="utf-8")
    report = load(target)
    assert investigation.add_addition(report, explain(report)).recheck_result == "证据不足"
