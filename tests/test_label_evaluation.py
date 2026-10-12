"""Evaluation accounting, leakage prevention, and real decoder integration."""

from hashlib import sha256
import json
from pathlib import Path

import cv2
from PIL import Image
import pytest

from src import evaluate_labels as cli
from src import label_evaluation as evaluation


def make_sample(tmp_path, name="one", payload="KNOWN-ONE", truth=True, split="development"):
    code = cv2.QRCodeEncoder_create().encode(payload)
    code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    code = cv2.resize(code, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    image = tmp_path / f"{name}.png"
    Image.fromarray(code).save(image)
    sample = {"id": name, "image": image.name, "sha256": sha256(image.read_bytes()).hexdigest(),
              "label_id": name, "batch_id": name, "split": split,
              "source_kind": "synthetic", "source": "OpenCV encoder; predetermined input"}
    if truth:
        expected = tmp_path / f"{name}.txt"
        expected.write_bytes(payload.encode("utf-8"))
        sample.update(expected_file=expected.name, expected_sha256=sha256(expected.read_bytes()).hexdigest(),
                      truth_source="encoder input fixed independently before decode")
    return sample


def manifest(tmp_path, samples):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "samples": samples}), encoding="utf-8")
    return path


def test_real_batch_known_unknown_and_roi_are_separate(tmp_path, monkeypatch):
    known = make_sample(tmp_path, payload="标签-ONE")
    unknown = make_sample(tmp_path, "two", "KNOWN-TWO", truth=False)
    unknown["source_kind"] = "unknown"
    with Image.open(tmp_path / known["image"]) as image:
        known["roi"] = [0, 0, image.width, image.height]
    path = manifest(tmp_path, [known, unknown])
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    # Manifest-relative paths still work when the caller is elsewhere.
    monkeypatch.chdir(tmp_path.parent)
    report = evaluation.evaluate_manifest(path)
    assert report["status"] == "completed"
    assert len(report["results"]) == 2
    assert len(report["summaries"]) == 3
    for summary in report["summaries"]:
        method = summary["methods"]["with_downscale_search"]
        if summary["source_kind"] == "unknown":
            assert method["correctness"]["denominator"] == 0
            assert method["correctness"]["fraction"] is None
            assert method["outcomes"]["decoded_unverified"] == 1
        else:
            assert method["correctness"]["numerator"] == method["correctness"]["denominator"] == 1
        assert method["decode_timing"]["count"] == 1
    assert report["manifest"]["sha256"] == sha256(path.read_bytes()).hexdigest()
    assert report["evaluation_policy"]["selection_uses_truth"] is False
    assert all(p.read_bytes() == contents for p, contents in before.items())


@pytest.mark.parametrize("mutate,code", [
    (lambda s: s.update(id=""), "invalid_manifest"),
    (lambda s: s.update(sha256="x" * 64), "invalid_manifest"),
    (lambda s: s.update(split="training"), "invalid_manifest"),
    (lambda s: s.update(source_kind="camera"), "invalid_manifest"),
    (lambda s: s.update(roi=[True, 0, 1, 1]), "invalid_manifest"),
    (lambda s: s.update(roi=[0, 0, 0, 1]), "invalid_manifest"),
    (lambda s: s.update(unrecognized=True), "invalid_manifest"),
    (lambda s: s.update(image="bad\x00.png"), "invalid_manifest"),
    (lambda s: s.pop("truth_source"), "invalid_manifest"),
    (lambda s: s.pop("source"), "invalid_manifest"),
])
def test_invalid_manifest_fails_before_analysis(tmp_path, monkeypatch, mutate, code):
    sample = make_sample(tmp_path)
    mutate(sample)
    monkeypatch.setattr(evaluation, "analyze_label", lambda *a, **kw: pytest.fail("must validate first"))
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.evaluate_manifest(manifest(tmp_path, [sample]))
    assert caught.value.code == code


@pytest.mark.parametrize("field", ["label_id", "batch_id", "expected_sha256"])
def test_group_leakage_checked_even_for_selected_split(tmp_path, field):
    one = make_sample(tmp_path)
    two = make_sample(tmp_path, "two", "OTHER", split="test")
    two[field] = one[field]
    if field == "label_id":
        # Isolate split leakage from the separately tested inconsistent-truth rule.
        for key in ("expected_file", "expected_sha256", "truth_source"):
            two.pop(key)
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.evaluate_manifest(manifest(tmp_path, [one, two]), split="development")
    assert caught.value.code == "split_leakage"


@pytest.mark.parametrize("field,code", [("id", "duplicate_sample"), ("sha256", "duplicate_image")])
def test_duplicates_are_rejected(tmp_path, field, code):
    one, two = make_sample(tmp_path), make_sample(tmp_path, "two", "OTHER")
    two[field] = one[field]
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.load_manifest(manifest(tmp_path, [one, two]))
    assert caught.value.code == code


@pytest.mark.parametrize("raw", [b"not-json", b"\xff", b'{"schema_version":1,"schema_version":1,"samples":[]}',
                                 b'{"schema_version":NaN,"samples":[]}', b'[]',
                                 b'{"schema_version":true,"samples":[]}'])
def test_bad_json_and_version(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(evaluation.EvaluationError):
        evaluation.load_manifest(path)


def test_manifest_resource_limits_and_missing_file(tmp_path, monkeypatch):
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.load_manifest(tmp_path / "missing.json")
    assert caught.value.code == "manifest_read_failed"
    path = manifest(tmp_path, [make_sample(tmp_path)])
    monkeypatch.setattr(evaluation, "MAX_MANIFEST_BYTES", 10)
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.load_manifest(path)
    assert caught.value.code == "manifest_limit_exceeded"
    monkeypatch.setattr(evaluation, "MAX_MANIFEST_BYTES", 1024 * 1024)
    monkeypatch.setattr(evaluation, "MAX_SAMPLES", 0)
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.load_manifest(path)
    assert caught.value.code == "sample_limit_exceeded"


@pytest.mark.parametrize("failure,code", [("image_hash", "image_hash_mismatch"),
                                        ("truth_hash", "expected_hash_mismatch"),
                                        ("missing", "sample_read_failed"),
                                        ("corrupt", "corrupt_image"),
                                        ("roi", "invalid_roi"),
                                        ("limit", "sample_file_limit_exceeded")])
def test_bad_samples_remain_in_denominator_and_batch_continues(tmp_path, monkeypatch, failure, code):
    bad = make_sample(tmp_path)
    good = make_sample(tmp_path, "two", "OTHER")
    if failure == "image_hash":
        bad["sha256"] = "0" * 64
    elif failure == "truth_hash":
        bad["expected_sha256"] = "0" * 64
    elif failure == "missing":
        bad["image"] = "missing.png"
    elif failure == "corrupt":
        (tmp_path / bad["image"]).write_bytes(b"not an image")
        bad["sha256"] = sha256(b"not an image").hexdigest()
    elif failure == "roi":
        bad["roi"] = [0, 0, 10000, 10000]
    else:
        monkeypatch.setattr(evaluation.images, "MAX_FILE_BYTES", 1)
    report = evaluation.evaluate_manifest(manifest(tmp_path, [bad, good]))
    assert report["status"] == "completed_with_errors"
    assert report["results"][0]["error"]["code"] == code
    assert len(report["results"]) == 2
    if failure != "limit":
        assert report["results"][1]["status"] == "completed"
    full = next(s for s in report["summaries"] if s["region"] == "full_image")
    assert full["methods"]["baseline"]["correctness"]["denominator"] == 2
    assert full["methods"]["baseline"]["outcomes"]["input_error"] >= 1


def test_split_selection_and_empty_selection(tmp_path):
    one = make_sample(tmp_path)
    two = make_sample(tmp_path, "two", "OTHER", split="test")
    path = manifest(tmp_path, [one, two])
    report = evaluation.evaluate_manifest(path, split="test")
    assert [r["sample"]["id"] for r in report["results"]] == ["two"]
    assert len(report["manifest"]["samples"]) == 2
    path = manifest(tmp_path, [one])
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.evaluate_manifest(path, split="test")
    assert caught.value.code == "empty_selection"
    with pytest.raises(evaluation.EvaluationError):
        evaluation.evaluate_manifest(path, split="bad")


def test_statistics_denominators_changes_conflicts_and_nearest_rank():
    rows = []
    pairs = [("not_decoded", "correct"), ("correct", "conflict"), ("incorrect", "incorrect"),
             ("execution_error", "execution_error"), ("input_error", "input_error"),
             ("ambiguous", "ambiguous"), ("decode_error", "not_decoded")]
    for index, (base, candidate) in enumerate(pairs):
        rows.append({"sample": {"split": "development", "source_kind": "phone_photo", "expected_file": "truth"},
                     "comparisons": [{"region": "full_image",
                         "baseline": {"outcome": base, "decode_duration_seconds": index + 1},
                         "with_downscale_search": {"outcome": candidate, "decode_duration_seconds": index + 2}}]})
    summary = evaluation.summarize_results(rows)[0]
    assert summary["methods"]["baseline"]["correctness"]["denominator"] == 7
    assert summary["methods"]["baseline"]["correctness"]["numerator"] == 1
    assert summary["paired_change"] == {"denominator": 5,
        "excluded_unknown_truth_or_input_execution_error": 2, "improved": 1, "degraded": 1}
    assert summary["methods"]["baseline"]["decode_timing"] == {
        "count": 7, "median_seconds": 4, "p95_seconds": 7}
    assert evaluation._timing([])["p95_seconds"] is None


def test_file_change_during_analysis_is_not_counted_as_correct(tmp_path, monkeypatch):
    one = make_sample(tmp_path)
    real = evaluation.analyze_label
    def changed(*args, **kwargs):
        report = real(*args, **kwargs)
        report["source"]["sha256"] = "0" * 64
        return report
    monkeypatch.setattr(evaluation, "analyze_label", changed)
    report = evaluation.evaluate_manifest(manifest(tmp_path, [one]))
    assert report["results"][0]["error"]["code"] == "image_hash_mismatch"
    assert report["summaries"][0]["methods"]["baseline"]["correctness"]["numerator"] == 0


def test_cli_utf8_output_reanalysis_and_no_overwrite(tmp_path, capsys):
    path = manifest(tmp_path, [make_sample(tmp_path, payload="标签-ONE")])
    output = tmp_path / "output.json"
    assert cli.main([str(path), "--output", str(output)]) == 0
    first = json.loads(capsys.readouterr().out)
    original = output.read_bytes()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["results"][0]["analysis"]["known_truth"]["text"] == "标签-ONE"
    assert cli.main([str(path)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["evaluation_id"] != second["evaluation_id"]
    assert cli.main([str(path), "--output", str(output)]) == 2
    assert output.read_bytes() == original
    assert "[output_exists]" in capsys.readouterr().err


def test_cli_bad_manifest_does_not_create_output(tmp_path, capsys):
    output = tmp_path / "output.json"
    assert cli.main([str(tmp_path / "missing.json"), "--output", str(output)]) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[manifest_read_failed]" in captured.err


def test_cli_sample_failure_is_structured_and_nonzero(tmp_path, capsys):
    sample = make_sample(tmp_path)
    sample["sha256"] = "0" * 64
    assert cli.main([str(manifest(tmp_path, [sample]))]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["results"][0]["error"]["code"] == "image_hash_mismatch"


def test_resource_exhaustion_is_explicit_and_next_sample_runs(tmp_path, monkeypatch):
    one, two = make_sample(tmp_path), make_sample(tmp_path, "two", "OTHER")
    real = evaluation.analyze_label
    def exhausted(path, *args, **kwargs):
        if Path(path).name == one["image"]:
            raise MemoryError("injected exhaustion")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(evaluation, "analyze_label", exhausted)
    report = evaluation.evaluate_manifest(manifest(tmp_path, [one, two]))
    assert report["results"][0]["error"]["code"] == "resource_exhausted"
    assert report["results"][0]["comparisons"][0]["baseline"]["outcome"] == "execution_error"
    assert report["results"][1]["status"] == "completed"


def test_same_group_within_development_is_allowed(tmp_path):
    one, two = make_sample(tmp_path), make_sample(tmp_path, "two", "OTHER")
    two["batch_id"] = one["batch_id"]
    loaded = evaluation.load_manifest(manifest(tmp_path, [one, two]))
    assert len(loaded["samples"]) == 2


def test_same_label_cannot_have_conflicting_known_truth(tmp_path):
    one, two = make_sample(tmp_path), make_sample(tmp_path, "two", "OTHER")
    two["label_id"] = one["label_id"]
    with pytest.raises(evaluation.EvaluationError) as caught:
        evaluation.load_manifest(manifest(tmp_path, [one, two]))
    assert caught.value.code == "inconsistent_truth"


def test_truth_file_change_during_analysis_is_rejected(tmp_path, monkeypatch):
    one = make_sample(tmp_path)
    real = evaluation.analyze_label
    def changed(*args, **kwargs):
        report = real(*args, **kwargs)
        report["known_truth"]["sha256"] = "0" * 64
        return report
    monkeypatch.setattr(evaluation, "analyze_label", changed)
    report = evaluation.evaluate_manifest(manifest(tmp_path, [one]))
    assert report["results"][0]["error"]["code"] == "expected_hash_mismatch"


def test_actual_multi_code_stays_ambiguous_even_with_matching_truth(tmp_path):
    one, two = make_sample(tmp_path), make_sample(tmp_path, "two", "OTHER")
    with Image.open(tmp_path / one["image"]) as left, Image.open(tmp_path / two["image"]) as right:
        combined = Image.new("L", (left.width + right.width + 80, left.height), 255)
        combined.paste(left, (0, 0))
        combined.paste(right, (left.width + 80, 0))
        combined.save(tmp_path / one["image"])
    one["sha256"] = sha256((tmp_path / one["image"]).read_bytes()).hexdigest()
    report = evaluation.evaluate_manifest(manifest(tmp_path, [one]))
    summary = report["summaries"][0]
    assert summary["methods"]["with_downscale_search"]["outcomes"]["ambiguous"] == 1
    assert summary["methods"]["with_downscale_search"]["correctness"]["numerator"] == 0
