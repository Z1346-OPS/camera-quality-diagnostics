"""Known encoder input is the synthetic truth; real device evidence is separate."""

from base64 import b64encode
from hashlib import sha256
import builtins
import json
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image
import pytest
import zxingcpp

from src import analyze_image as images
from src import analyze_label as cli
from src import label_analysis as core


def qr_image(text="STAGE2-KNOWN-A"):
    # Use the existing OpenCV encoder, independently of the ZXing decoder.
    code = cv2.QRCodeEncoder_create().encode(text)
    code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    code = cv2.resize(code, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(code, cv2.COLOR_GRAY2BGR)


def save_bgr(path, bgr, orientation=None):
    image = Image.fromarray(bgr[:, :, ::-1])
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(path, exif=exif)


def test_known_single_qr_raw_bytes_and_config():
    bgr = qr_image()
    frame, region = core.select_region(bgr)
    result = core.decode_qr(frame, region)
    assert result["status"] == "decoded"
    assert result["symbols"][0]["text"] == "STAGE2-KNOWN-A"
    assert result["symbols"][0]["payload_base64"] == b64encode(b"STAGE2-KNOWN-A").decode()
    assert result["config"]["try_downscale"] is False
    assert result["config"]["try_invert"] is False
    assert result["config"]["external_enhancement"] == "none"
    assert result["decoder"]["version"] == "3.1.1"
    assert result["duration_seconds"] >= 0
    assert core.check_expected(result)["status"] == "not_provided"
    assert core.check_expected(result, b"STAGE2-KNOWN-A")["status"] == "correct"
    assert core.check_expected(result, b"other")["status"] == "incorrect"
    assert core.check_expected(result, b"STAGE2-KNOWN-A\n")["status"] == "incorrect"


def test_blank_is_not_decoded_not_execution_error():
    frame, region = core.select_region(np.full((160, 220, 3), 255, dtype=np.uint8))
    result = core.decode_qr(frame, region)
    assert result["status"] == "not_decoded"
    assert result["error"] is None
    assert result["symbols"] == []
    assert core.check_expected(result, b"answer")["status"] == "not_decoded"


def test_multiple_qr_is_ambiguous_even_when_one_matches():
    left, right = qr_image("STAGE2-KNOWN-A"), qr_image("STAGE2-KNOWN-B")
    frame = np.concatenate([left, np.full((left.shape[0], 80, 3), 255, dtype=np.uint8), right], axis=1)
    _, region = core.select_region(frame)
    result = core.decode_qr(frame, region)
    assert result["status"] == "ambiguous"
    assert len(result["symbols"]) == 2
    assert {s["text"] for s in result["symbols"]} == {"STAGE2-KNOWN-A", "STAGE2-KNOWN-B"}
    assert core.check_expected(result, b"STAGE2-KNOWN-A")["status"] == "ambiguous"


@pytest.mark.parametrize("roi", [(-1, 0, 3, 3), (0, -1, 3, 3), (0, 0, 0, 3),
                                 (0, 0, 3, -1), (8, 0, 3, 3), (0, 8, 3, 3),
                                 (0.0, 0, 3, 3), (True, 0, 3, 3), (0, 0, 3)])
def test_invalid_roi_is_rejected(roi):
    with pytest.raises(core.LabelAnalysisError) as caught:
        core.select_region(np.zeros((10, 10, 3), dtype=np.uint8), roi)
    assert caught.value.code == "invalid_roi"


@pytest.mark.parametrize("frame", [np.zeros((2, 2), dtype=np.uint8), np.zeros((2, 2, 4), dtype=np.uint8),
                                    np.zeros((2, 2, 3), dtype=np.float32), np.zeros((0, 2, 3), dtype=np.uint8)])
def test_invalid_array_is_rejected(frame):
    with pytest.raises(core.LabelAnalysisError, match="uint8 BGR"):
        core.select_region(frame)


def test_roi_metrics_coordinates_and_no_original_overwrite(tmp_path):
    qr = qr_image()
    h, w = qr.shape[:2]
    frame = np.full((h+80, w+120, 3), 60, dtype=np.uint8)
    frame[30:30+h, 50:50+w] = qr
    source = tmp_path / "label.png"
    save_bgr(source, frame)
    original = source.read_bytes()
    truth = tmp_path / "truth.txt"
    truth.write_bytes(b"STAGE2-KNOWN-A")
    result = cli.analyze_label(source, (50, 30, w, h), truth, "OpenCV encoder input fixed before decoding")
    assert source.read_bytes() == original
    full, roi = result["attempts"]
    assert full["region"]["kind"] == "full_image"
    assert roi["region"]["kind"] == "roi"
    assert roi["truth_check"]["status"] == "correct"
    assert roi["metrics"] == images.calculate_image_metrics(qr)
    assert full["metrics"] != roi["metrics"]
    symbol = roi["decode"]["symbols"][0]
    assert symbol["position_analysis_image"] == [[x+50, y+30] for x,y in symbol["position_region"]]
    assert result["known_truth"]["sha256"] == sha256(b"STAGE2-KNOWN-A").hexdigest()
    assert result["config_sha256"] == sha256(json.dumps(result["analysis_config"], sort_keys=True).encode()).hexdigest()


def test_roi_uses_exif_normalized_coordinates(tmp_path):
    qr = qr_image()
    h, w = qr.shape[:2]
    desired = np.full((h+80, w+160, 3), 255, dtype=np.uint8)
    desired[20:20+h, 100:100+w] = qr
    source = tmp_path / "rotated.png"
    save_bgr(source, np.rot90(desired, 1), orientation=6)
    result = cli.analyze_label(source, (100, 20, w, h))
    assert result["preprocessing"]["exif_transposed"] is True
    assert result["attempts"][1]["decode"]["symbols"][0]["text"] == "STAGE2-KNOWN-A"
    assert result["attempts"][1]["metrics"] == images.calculate_image_metrics(qr)


def test_roi_can_resolve_full_image_multi_target_without_truth_selection(tmp_path):
    left, right = qr_image("STAGE2-KNOWN-A"), qr_image("STAGE2-KNOWN-B")
    source = tmp_path / "two.png"
    frame = np.concatenate([left, np.full((left.shape[0], 80, 3), 255, dtype=np.uint8), right], axis=1)
    save_bgr(source, frame)
    result = cli.analyze_label(source, (0, 0, left.shape[1], left.shape[0]))
    assert result["attempts"][0]["decode"]["status"] == "ambiguous"
    assert result["attempts"][1]["decode"]["status"] == "decoded"
    assert result["attempts"][1]["truth_check"]["status"] == "not_provided"


def test_decoder_exception_is_preserved_and_cli_nonzero(tmp_path, monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise RuntimeError("injected decoder failure")
    monkeypatch.setattr(zxingcpp, "read_barcodes", broken)
    source, output = tmp_path / "label.png", tmp_path / "failure.json"
    save_bgr(source, qr_image())
    assert cli.main([str(source), "--output", str(output)]) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "completed_with_errors"
    assert result["attempts"][0]["decode"]["error"]["code"] == "decoder_execution_error"
    assert result["attempts"][0]["decode"]["error"]["exception_type"] == "RuntimeError"
    assert json.loads(capsys.readouterr().out)["status"] == "completed_with_errors"


def test_missing_decoder_does_not_become_no_code(monkeypatch):
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == "zxingcpp":
            raise ImportError("injected unavailable")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    frame, region = core.select_region(qr_image())
    result = core.decode_qr(frame, region)
    assert result["status"] == "execution_error"
    assert result["error"]["code"] == "decoder_unavailable"


def test_invalid_symbol_is_decode_error_not_execution_error(monkeypatch):
    point = SimpleNamespace(x=1, y=1)
    pos = SimpleNamespace(top_left=point, top_right=point, bottom_left=point, bottom_right=point)
    invalid = SimpleNamespace(position=pos, valid=False, bytes=b"", format="QR Code", text="",
                              error=SimpleNamespace(type="Checksum", message="injected bad checksum"))
    monkeypatch.setattr(zxingcpp, "read_barcodes", lambda *a, **kw: [invalid])
    frame, region = core.select_region(qr_image())
    result = core.decode_qr(frame, region)
    assert result["status"] == "decode_error"
    assert result["error"]["code"] == "symbol_decode_error"
    assert result["symbols"][0]["error"]["type"] == "Checksum"


def test_memory_exhaustion_is_not_swallowed(monkeypatch):
    def exhausted(*a, **kw):
        raise MemoryError()
    monkeypatch.setattr(zxingcpp, "read_barcodes", exhausted)
    frame, region = core.select_region(qr_image())
    with pytest.raises(MemoryError):
        core.decode_qr(frame, region)


def test_truth_utf8_whitespace_and_source_required(tmp_path):
    source = tmp_path / "answer.txt"
    source.write_bytes("标签 A \n".encode("utf-8"))
    expected, info = cli.read_expected(source, "label creation record")
    assert expected == "标签 A \n".encode("utf-8")
    assert info["text"] == "标签 A \n"
    with pytest.raises(core.LabelAnalysisError) as caught:
        cli.read_expected(source, None)
    assert caught.value.code == "invalid_truth"
    source.write_bytes(b"\xff")
    with pytest.raises(core.LabelAnalysisError) as caught:
        cli.read_expected(source, "independent record")
    assert caught.value.code == "invalid_expected_encoding"


def test_truth_limit_missing_and_orphan_source(tmp_path, monkeypatch):
    with pytest.raises(core.LabelAnalysisError) as caught:
        cli.read_expected(tmp_path / "missing.txt", "record")
    assert caught.value.code == "expected_read_failed"
    with pytest.raises(core.LabelAnalysisError) as caught:
        cli.read_expected(None, "record")
    assert caught.value.code == "invalid_truth"
    path = tmp_path / "large.txt"
    path.write_bytes(b"abcd")
    monkeypatch.setattr(cli, "MAX_EXPECTED_BYTES", 3)
    with pytest.raises(core.LabelAnalysisError) as caught:
        cli.read_expected(path, "record")
    assert caught.value.code == "expected_limit_exceeded"


def test_cli_new_results_preserve_old_reports_and_ids(tmp_path, capsys):
    source, first, second = tmp_path / "label.png", tmp_path / "one.json", tmp_path / "two.json"
    save_bgr(source, qr_image())
    assert cli.main([str(source), "--output", str(first)]) == 0
    original = first.read_bytes()
    assert cli.main([str(source), "--output", str(second)]) == 0
    assert json.loads(original)["analysis_id"] != json.loads(second.read_bytes())["analysis_id"]
    assert cli.main([str(source), "--output", str(first)]) == 2
    assert first.read_bytes() == original
    assert "[output_exists]" in capsys.readouterr().err


@pytest.mark.parametrize("contents,code", [(b"not an image", "corrupt_image")])
def test_bad_image_propagates_stable_error(tmp_path, capsys, contents, code):
    source, output = tmp_path / "bad.png", tmp_path / "result.json"
    source.write_bytes(contents)
    assert cli.main([str(source), "--output", str(output)]) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"[{code}]" in captured.err


def test_invalid_roi_does_not_call_decoder_or_create_result(tmp_path, monkeypatch, capsys):
    source, output = tmp_path / "label.png", tmp_path / "result.json"
    save_bgr(source, qr_image())
    monkeypatch.setattr(cli, "decode_qr", lambda *a: pytest.fail("invalid ROI must fail before decode"))
    assert cli.main([str(source), "--roi", "-1", "0", "10", "10", "--output", str(output)]) == 2
    assert not output.exists()
    assert "[invalid_roi]" in capsys.readouterr().err


def test_non_qr_code_is_out_of_scope():
    barcode = zxingcpp.create_barcode("1234567890", zxingcpp.BarcodeFormat.Code128)
    frame = cv2.cvtColor(np.asarray(barcode.to_image(scale=3)), cv2.COLOR_GRAY2BGR)
    _, region = core.select_region(frame)
    assert core.decode_qr(frame, region)["status"] == "not_decoded"


def test_utf8_payload_matches_raw_bytes():
    payload = "标签-阶段二"
    frame = qr_image(payload)
    _, region = core.select_region(frame)
    result = core.decode_qr(frame, region)
    assert result["status"] == "decoded"
    assert core.check_expected(result, payload.encode("utf-8"))["status"] == "correct"


def test_roi_is_exact_slice_without_padding():
    frame = np.arange(40*32*3, dtype=np.uint8).reshape(32, 40, 3)
    selected, region = core.select_region(frame, (10, 8, 30, 24))
    np.testing.assert_array_equal(selected, frame[8:32, 10:40])
    assert selected.shape == (24, 30, 3)
    assert region["width"] * region["height"] == 720


@pytest.mark.parametrize("exception,code", [(PermissionError("denied"), "output_access_denied"),
                                          (OSError("disk failure"), "output_write_failed")])
def test_label_output_error_does_not_print_success(tmp_path, monkeypatch, capsys, exception, code):
    source, output = tmp_path / "label.png", tmp_path / "out.json"
    save_bgr(source, qr_image())
    original = cli.Path.open
    def denied(path, *a, **kw):
        if path == output:
            raise exception
        return original(path, *a, **kw)
    monkeypatch.setattr(cli.Path, "open", denied)
    assert cli.main([str(source), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"[{code}]" in captured.err


def decoded_result(payload=b"answer"):
    return {"status": "decoded", "symbols": [
        {"valid": True, "payload_base64": b64encode(payload).decode("ascii")} ]}


@pytest.mark.parametrize("statuses,expected", [
    (["decode_error", "decoded"], "decoded"),
    (["not_decoded", "decoded"], "decoded"),
    (["decoded", "execution_error"], "execution_error"),
    (["decoded", "ambiguous"], "ambiguous"),
    (["decode_error", "not_decoded"], "decode_error"),
    (["not_decoded", "not_decoded"], "not_decoded"),
])
def test_retry_summary_preserves_unresolved_failures(statuses, expected):
    decodes = [decoded_result() if status == "decoded" else {"status": status, "symbols": []}
               for status in statuses]
    summary = core.summarize_decodes(decodes)
    assert summary["status"] == expected
    assert summary["selected_attempt_index"] == (1 if expected == "decoded" else None)
    assert summary["failed_attempt_indices"] == [i for i, s in enumerate(statuses)
                                                if s in {"decode_error", "execution_error"}]


def test_retry_conflicts_cannot_be_resolved_using_truth():
    summary = core.summarize_decodes([decoded_result(b"A"), decoded_result(b"B")])
    assert summary["status"] == "conflict"
    assert summary["symbols"] == []
    assert summary["selected_attempt_index"] is None
    assert core.check_expected(summary, b"B")["status"] == "conflict"
    agreed = core.summarize_decodes([decoded_result(b"A"), decoded_result(b"A")])
    assert agreed["status"] == "decoded"
    assert agreed["selected_attempt_index"] == 0


def test_downscale_reaches_native_decoder_and_records_config(monkeypatch):
    original = zxingcpp.read_barcodes
    flags = []
    def observed(*args, **kwargs):
        flags.append(kwargs["try_downscale"])
        return original(*args, **kwargs)
    monkeypatch.setattr(zxingcpp, "read_barcodes", observed)
    frame, region = core.select_region(qr_image())
    for enabled in (False, True):
        result = core.decode_qr(frame, region, try_downscale=enabled)
        assert result["status"] == "decoded"
        assert result["config"]["try_downscale"] is enabled
        assert result["duration_seconds"] >= 0
    assert flags == [False, True]
    assert core.DECODER_CONFIG["try_downscale"] is False


@pytest.mark.parametrize("value", [1, "true", None])
def test_invalid_retry_flag_is_rejected(value):
    frame, region = core.select_region(qr_image())
    with pytest.raises(core.LabelAnalysisError, match="布尔值"):
        core.decode_qr(frame, region, try_downscale=value)
    with pytest.raises(core.LabelAnalysisError, match="布尔值"):
        cli.analyze_label("not-read.png", try_downscale=value)


@pytest.mark.parametrize("truth,expected_status", [(b"answer", "correct"), (b"wrong", "incorrect")])
def test_cli_retry_keeps_baseline_error_and_checks_truth_after_decode(tmp_path, monkeypatch, capsys,
                                                                   truth, expected_status):
    source, expected = tmp_path / "label.png", tmp_path / "truth.txt"
    save_bgr(source, qr_image())
    expected.write_bytes(truth)
    before = source.read_bytes()
    def decoder(frame, region, *, try_downscale=False):
        return decoded_result() if try_downscale else {"status": "decode_error", "symbols": []}
    monkeypatch.setattr(cli, "decode_qr", decoder)
    assert cli.main([str(source), "--try-downscale", "--expected-file", str(expected),
                     "--truth-source", "independent encoder input"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == 2
    assert [a["decode"]["status"] for a in report["attempts"]] == ["decode_error", "decoded"]
    assert report["decode_summaries"][0]["truth_check"]["status"] == expected_status
    assert report["decode_summaries"][0]["decode"]["selected_attempt_index"] == 1
    assert any(w["code"] == "decode_attempt_errors" for w in report["warnings"])
    assert source.read_bytes() == before


def test_retry_roi_indices_metrics_and_config_hash(tmp_path, monkeypatch):
    source = tmp_path / "label.png"
    frame = qr_image()
    save_bgr(source, frame)
    real_metrics = images.calculate_image_metrics
    metric_calls = []
    def metrics(array):
        metric_calls.append(array.shape)
        return real_metrics(array)
    monkeypatch.setattr(images, "calculate_image_metrics", metrics)
    result = cli.analyze_label(source, (0, 0, frame.shape[1], frame.shape[0]), try_downscale=True)
    assert len(metric_calls) == 2
    assert len(result["attempts"]) == 4
    assert [s["attempt_indices"] for s in result["decode_summaries"]] == [[0, 1], [2, 3]]
    assert [s["decode"]["selected_attempt_index"] for s in result["decode_summaries"]] == [0, 2]
    assert all(s["truth_check"]["status"] == "not_provided" for s in result["decode_summaries"])
    assert [a["decode"]["config"]["try_downscale"] for a in result["attempts"]] == [False, True, False, True]
    baseline = cli.analyze_label(source, (0, 0, frame.shape[1], frame.shape[0]))
    assert result["config_sha256"] != baseline["config_sha256"]
    assert len(baseline["attempts"]) == 2
    assert result["config_sha256"] == sha256(json.dumps(result["analysis_config"], sort_keys=True).encode()).hexdigest()


def test_retry_execution_failure_still_returns_nonzero(tmp_path, monkeypatch, capsys):
    source = tmp_path / "label.png"
    save_bgr(source, qr_image())
    def decoder(frame, region, *, try_downscale=False):
        return {"status": "execution_error", "symbols": []} if try_downscale else decoded_result()
    monkeypatch.setattr(cli, "decode_qr", decoder)
    assert cli.main([str(source), "--try-downscale"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["decode_summaries"][0]["decode"]["status"] == "execution_error"
    assert report["status"] == "completed_with_errors"
