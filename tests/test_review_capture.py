"""采集任务复核入口测试：只用临时目录中的合成 PNG 与 CSV。

反例只修改本文件在 `tmp_path` 下构造的夹具，不触碰任何既有资产。
"""

import csv
import hashlib
import json
import platform
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest

from src.analysis_config import BRIGHT_THRESHOLD, DARK_THRESHOLD
from src.frame_evidence import save_frame_evidence
from src.report import append_color_record, append_quality_record
from src.review_capture import CaptureTaskReviewer, main
from src.verify_frame_metrics import compare_frame_metrics


# 4×5 常量 100 的 BGR 图，五项指标人工推导：
# 灰度恒为 100 → 亮度 100.0；无 ≤30 或 ≥225 的像素；拉普拉斯方差与标准差均为 0。
CONSTANT_VALUES = (100.0, 0.0, 0.0, 0.0, 0.0)
EXPECTED_METRICS = {
    "brightness": ["100.0", "100.0"],
    "dark_ratio": ["0.0", "0.0"],
    "bright_ratio": ["0.0", "0.0"],
    "sharpness": ["0.0", "0.0"],
    "contrast": ["0.0", "0.0"],
}
QUALITY_CSV = "camera_quality_runs.csv"
COLOR_CSV = "camera_colors_runs.csv"
TASK_JSON = "capture_task.json"


def png_path(task_dir, run_id, frame_count):
    return task_dir / f"camera_frame_{run_id}_{frame_count}.png"


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_png(task_dir, run_id, frame_count, value=100, compression=None):
    frame = np.full((4, 5, 3), value, dtype=np.uint8)
    if compression is None:
        return save_frame_evidence(frame, run_id, frame_count, png_path(task_dir, run_id, frame_count))
    ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, compression])
    assert ok
    target = png_path(task_dir, run_id, frame_count)
    target.write_bytes(encoded.tobytes())
    return target


def current_context():
    src = Path(__file__).resolve().parents[1] / "src"
    runtime = {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
    }
    digests = {
        name: sha256_of(src / name) for name in ("metrics.py", "analysis_config.py")
    }
    return {"dark_threshold": DARK_THRESHOLD, "bright_threshold": BRIGHT_THRESHOLD}, {
        "runtime": runtime, "source_sha256": digests,
    }


def sample_entry(task_dir, run_id, frame_count, **overrides):
    entry = {
        "frame_count": frame_count,
        "image_file": f"camera_frame_{run_id}_{frame_count}.png",
        "image_sha256": sha256_of(png_path(task_dir, run_id, frame_count)),
        "quality_status": "written",
        "color_status": "written",
        "image_status": "written",
    }
    entry.update(overrides)
    return entry


def build_task(task_dir, run_id, samples, *, status="completed", samples_completed=None,
               planned=2, metric_config=None, provenance=None):
    if samples_completed is None:
        samples_completed = len(samples)
    task = {
        "schema_version": 1,
        "report_type": "camera_timed_capture",
        "run_id": run_id,
        "status": status,
        "stop_reason": "duration_reached" if status == "completed" else "read_failed",
        "counts": {"planned_sample_slots": planned, "samples_completed": samples_completed},
        "samples": samples,
    }
    if metric_config is not None:
        task["metric_config"] = metric_config
    if provenance is not None:
        task["provenance"] = provenance
    (task_dir / TASK_JSON).write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
    return task


def make_task(tmp_path, frame_counts=(1,), *, name="task", values=CONSTANT_VALUES,
              csv_values=None, status="completed", samples_completed=None, planned=2,
              metric_config=None, provenance=None):
    """构造一个自洽的任务目录：CSV 值默认等于常量 100 图的重算值。"""
    task_dir = tmp_path / name
    task_dir.mkdir()
    run_id = uuid4().hex
    quality = task_dir / QUALITY_CSV
    color = task_dir / COLOR_CSV
    samples = []
    for index, frame_count in enumerate(frame_counts):
        write_png(task_dir, run_id, frame_count)
        row = (csv_values[index] if csv_values is not None else values)
        append_quality_record(frame_count, *row, quality, run_id=run_id)
        append_color_record(frame_count, 100, 100, 100, color,
                            scene_label="unspecified", run_id=run_id)
        samples.append(sample_entry(task_dir, run_id, frame_count))
    if metric_config is None or provenance is None:
        default_config, default_provenance = current_context()
        metric_config = default_config if metric_config is None else metric_config
        provenance = default_provenance if provenance is None else provenance
    build_task(task_dir, run_id, samples, status=status, samples_completed=samples_completed,
               planned=planned, metric_config=metric_config, provenance=provenance)
    return task_dir, run_id, samples


def review(task_dir):
    return CaptureTaskReviewer(task_dir).review()


def cli(task_dir):
    return main([str(task_dir)])


def snapshot(task_dir):
    return sorted(
        (entry.name, sha256_of(entry))
        for entry in Path(task_dir).iterdir() if entry.is_file()
    )


def rewrite_csv(path, transform):
    """按行重写 CSV（保留表头顺序与 utf-8-sig），transform(row) 返回是否保留。"""
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = [row for row in reader if transform(row)]
    with Path(path).open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def drop_quality_frame(task_dir, frame_count):
    rewrite_csv(task_dir / QUALITY_CSV, lambda row: row["frame_count"] != str(frame_count))


def set_quality_value(task_dir, frame_count, field, value):
    def transform(row):
        if row["frame_count"] == str(frame_count):
            row[field] = value
        return True
    rewrite_csv(task_dir / QUALITY_CSV, transform)


# ---------- R01：合成常量图，五项预期人工给定 ----------

def test_r01_constant_frame_matches_hand_derived_expectations(tmp_path, capsys):
    task_dir, run_id, _ = make_task(tmp_path, (1,))
    result = review(task_dir)
    assert result["verification_status"] == "consistent"
    assert result["comparison_basis"] == "current_algorithm_one_decimal"
    assert result["counts"] == {"reported_samples": 1, "csv_pairs": 1, "verified_frames": 1}
    assert result["issues"] == []
    assert result["warnings"] == []
    assert result["frames"] == [{
        "frame_count": 1,
        "image_sha256_match": True,
        "metrics": EXPECTED_METRICS,
    }]
    assert cli(task_dir) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == run_id


# ---------- R02：逐帧五项字符串对与改动前接口一致 ----------

def test_r02_frame_metrics_match_existing_interface(tmp_path):
    task_dir, run_id, _ = make_task(tmp_path, (1, 3))
    result = review(task_dir)
    for frame in result["frames"]:
        frame_count = frame["frame_count"]
        direct = compare_frame_metrics(
            run_id, frame_count, task_dir,
            task_dir / QUALITY_CSV, task_dir / COLOR_CSV,
        )
        assert frame["metrics"] == {name: [saved, recomputed] for name, (saved, recomputed) in direct.items()}
    assert result["counts"]["verified_frames"] == 2


# ---------- R03：无损重编码，像素相同、摘要不同 ----------

def test_r03_lossless_reencode_keeps_metrics_but_flags_hash(tmp_path):
    task_dir, run_id, _ = make_task(tmp_path, (1,))
    image = png_path(task_dir, run_id, 1)
    original = image.read_bytes()
    before = cv2.imdecode(np.frombuffer(original, np.uint8), cv2.IMREAD_UNCHANGED)
    write_png(task_dir, run_id, 1, compression=0)  # 无压缩存储，字节必然不同
    reencoded = image.read_bytes()
    after = cv2.imdecode(np.frombuffer(reencoded, np.uint8), cv2.IMREAD_UNCHANGED)
    assert reencoded != original          # 文件摘要不同
    assert np.array_equal(before, after)  # 像素相同

    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    assert result["counts"]["verified_frames"] == 0
    assert result["frames"][0]["image_sha256_match"] is False
    assert result["frames"][0]["metrics"] == EXPECTED_METRICS  # 指标仍一致
    assert [issue["code"] for issue in result["issues"]] == ["image_hash_mismatch"]
    assert cli(task_dir) == 1


# ---------- R04：缺图、空图、坏图、改一项 CSV，另一帧仍检查 ----------

def test_r04_missing_empty_broken_png_and_changed_csv(tmp_path):
    task_dir, run_id, _ = make_task(tmp_path, (1, 2, 3, 4))
    png_path(task_dir, run_id, 1).unlink()                      # 缺失
    png_path(task_dir, run_id, 2).write_bytes(b"")              # 空文件
    png_path(task_dir, run_id, 3).write_bytes(b"not a png")     # 坏文件
    set_quality_value(task_dir, 4, "brightness", "99.0")       # 帧 4 改一项 CSV 值

    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    by_frame = {frame["frame_count"]: frame for frame in result["frames"]}
    codes = {}
    for issue in result["issues"]:
        codes.setdefault(issue["frame_count"], set()).add(issue["code"])

    assert by_frame[1]["image_sha256_match"] is None and by_frame[1]["metrics"] is None
    assert codes[1] == {"frame_unverifiable"}
    assert by_frame[2]["metrics"] is None and codes[2] == {"image_hash_mismatch", "frame_unverifiable"}
    assert by_frame[3]["metrics"] is None and codes[3] == {"image_hash_mismatch", "frame_unverifiable"}
    assert by_frame[4]["metrics"]["brightness"] == ["99.0", "100.0"]
    assert codes[4] == {"metric_mismatch"}
    assert result["counts"]["verified_frames"] == 0
    assert cli(task_dir) == 1


# ---------- R05：CSV 键集合必须与任务声明完全一致 ----------

def test_r05_csv_key_set_must_equal_declared_set(tmp_path):
    # 两份 CSV 同时删去一个声明帧
    task_dir, run_id, _ = make_task(tmp_path, (1, 2), name="drop")
    drop_quality_frame(task_dir, 2)
    rewrite_csv(task_dir / COLOR_CSV, lambda row: row["frame_count"] != "2")
    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    assert [issue["code"] for issue in result["issues"]] == ["csv_keys_mismatch"]
    assert result["frames"] == [] and result["counts"]["verified_frames"] == 0
    assert cli(task_dir) == 1

    # 两份 CSV 同时混入其他批次
    task_dir, run_id, _ = make_task(tmp_path, (1,), name="mixed")
    other = uuid4().hex
    append_quality_record(5, 100.0, 0.0, 0.0, 0.0, 0.0,
                          task_dir / QUALITY_CSV, run_id=other)
    append_color_record(5, 100, 100, 100, task_dir / COLOR_CSV,
                        scene_label="unspecified", run_id=other)
    result = review(task_dir)
    assert [issue["code"] for issue in result["issues"]] == ["csv_keys_mismatch"]
    assert cli(task_dir) == 1

    # 单侧增加记录（两份 CSV 互相配对也无法掩盖）
    task_dir, run_id, _ = make_task(tmp_path, (1,), name="single")
    append_quality_record(2, 100.0, 0.0, 0.0, 0.0, 0.0,
                          task_dir / QUALITY_CSV, run_id=run_id)
    result = review(task_dir)
    assert [issue["code"] for issue in result["issues"]] == ["csv_keys_mismatch"]
    assert cli(task_dir) == 1


# ---------- R06：任务声明一致性 ----------

def test_r06_declared_counts_and_states(tmp_path):
    # 完整数与 samples 数矛盾
    task_dir, _, _ = make_task(tmp_path, (1,), name="count", samples_completed=3)
    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    assert [issue["code"] for issue in result["issues"]] == ["task_sample_count_mismatch"]
    assert cli(task_dir) == 1

    # 保存状态非 written
    task_dir, run_id, samples = make_task(tmp_path, (1,), name="state")
    samples[0]["image_status"] = "failed"
    build_task(task_dir, run_id, samples)
    result = review(task_dir)
    assert [issue["code"] for issue in result["issues"]] == ["task_sample_state_mismatch"]
    assert cli(task_dir) == 1

    # 理论 6 点但只有 2 个合法完整样本：允许一致，不要求补齐理论点数
    task_dir, _, _ = make_task(tmp_path, (1, 2), name="planned", planned=6)
    result = review(task_dir)
    assert result["verification_status"] == "consistent"
    assert result["issues"] == []
    assert result["counts"]["reported_samples"] == 2
    assert cli(task_dir) == 0


@pytest.mark.parametrize("csv_mismatch", [False, True])
def test_r06_reported_samples_keeps_declared_count(tmp_path, csv_mismatch):
    """声明 3 帧而 samples 只有 1 项时，reported_samples 必须保留声明值 3。"""
    task_dir, run_id, _ = make_task(
        tmp_path, (1,), name=f"reported-{csv_mismatch}", samples_completed=3
    )
    if csv_mismatch:                  # 走 CSV 集合不一致的提前返回分支
        other = uuid4().hex

        def retag(row):
            row["run_id"] = other
            return True

        rewrite_csv(task_dir / QUALITY_CSV, retag)
        rewrite_csv(task_dir / COLOR_CSV, retag)

    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    assert result["counts"]["reported_samples"] == 3
    if csv_mismatch:
        assert result["frames"] == []
        assert [issue["code"] for issue in result["issues"]] == [
            "task_sample_count_mismatch", "csv_keys_mismatch",
        ]
    else:
        assert [issue["code"] for issue in result["issues"]] == ["task_sample_count_mismatch"]


# ---------- R07：非 completed 任务不复核 ----------

@pytest.mark.parametrize("status", ["failed", "interrupted"])
def test_r07_non_completed_task_is_not_reviewed(tmp_path, capsys, status):
    task_dir, run_id, samples = make_task(tmp_path, (1,), status=status)
    before = snapshot(task_dir)
    result = review(task_dir)
    assert result["verification_status"] == "not_reviewed"
    assert result["task_status"] == status
    assert result["run_id"] == run_id
    assert result["counts"] is None and result["frames"] == []
    assert [issue["code"] for issue in result["issues"]] == ["task_not_completed"]
    assert cli(task_dir) == 2
    assert json.loads(capsys.readouterr().out)["verification_status"] == "not_reviewed"
    assert snapshot(task_dir) == before  # 不重算、不恢复、不改原状态


# ---------- R08：输入错误一律退出 2 且无成功 JSON ----------

def test_r08_missing_files_and_bad_json(tmp_path, capsys):
    task_dir, _, _ = make_task(tmp_path, (1,), name="nojson")
    (task_dir / TASK_JSON).unlink()
    assert cli(task_dir) == 2
    assert capsys.readouterr().out == ""

    task_dir, _, _ = make_task(tmp_path, (1,), name="nocsv")
    (task_dir / QUALITY_CSV).unlink()
    assert cli(task_dir) == 2
    assert capsys.readouterr().out == ""

    task_dir, _, _ = make_task(tmp_path, (1,), name="badjson")
    (task_dir / TASK_JSON).write_text("{ not json", encoding="utf-8")
    assert cli(task_dir) == 2
    assert capsys.readouterr().out == ""

    task_dir, _, _ = make_task(tmp_path, (1,), name="nan")
    (task_dir / TASK_JSON).write_text('{"schema_version": NaN}', encoding="utf-8")
    assert cli(task_dir) == 2
    assert capsys.readouterr().out == ""


def test_r08_field_type_and_version_errors(tmp_path):
    task_dir, run_id, samples = make_task(tmp_path, (1,), name="version")
    (task_dir / TASK_JSON).write_text(json.dumps({
        "schema_version": "1", "report_type": "camera_timed_capture",
        "run_id": run_id, "status": "completed", "samples": samples,
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        review(task_dir)

    task_dir, run_id, samples = make_task(tmp_path, (1,), name="frametype")
    samples[0]["frame_count"] = "1"
    build_task(task_dir, run_id, samples)
    with pytest.raises(ValueError):
        review(task_dir)


def test_r08_duplicate_frames_and_csv_keys(tmp_path):
    task_dir, run_id, samples = make_task(tmp_path, (1,), name="dupframe")
    samples.append(sample_entry(task_dir, run_id, 1))
    build_task(task_dir, run_id, samples)
    with pytest.raises(ValueError):
        review(task_dir)

    task_dir, run_id, _ = make_task(tmp_path, (1,), name="dupkey")
    append_quality_record(1, 100.0, 0.0, 0.0, 0.0, 0.0,
                          task_dir / QUALITY_CSV, run_id=run_id)
    append_color_record(1, 100, 100, 100, task_dir / COLOR_CSV,
                        scene_label="unspecified", run_id=run_id)
    with pytest.raises(ValueError):
        review(task_dir)


def test_r08_declared_image_name_must_be_canonical(tmp_path):
    task_dir, run_id, samples = make_task(tmp_path, (1,), name="namecheck")
    samples[0]["image_file"] = "../../outside.png"
    build_task(task_dir, run_id, samples)
    with pytest.raises(ValueError, match="image_file"):
        review(task_dir)          # 声明名不合法，读取前即拒绝


def test_r08_malformed_csv_is_value_error_and_cli_two(tmp_path, capsys):
    task_dir, _, _ = make_task(tmp_path, (1,), name="badcsv")
    path = task_dir / QUALITY_CSV
    header = path.read_text(encoding="utf-8-sig").splitlines()[0]
    path.write_text(header + '\n"unterminated', encoding="utf-8-sig")
    with pytest.raises(ValueError):   # csv.Error 不是 ValueError，必须由组合层转换
        review(task_dir)
    assert cli(task_dir) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CSV" in captured.err


def test_r08_symlinked_image_escaping_dir_is_rejected_before_read(tmp_path, monkeypatch):
    """声明仍是规范图片名，只把实际文件换成指向目录外的链接，以真正走到路径解析分支。"""
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"sentinel")

    task_dir, run_id, _ = make_task(tmp_path, (1,), name="escape")
    link = png_path(task_dir, run_id, 1)
    link.unlink()
    try:
        link.symlink_to(outside)
    except OSError as error:          # 环境不支持符号链接：如实跳过，不声称通过
        pytest.skip(f"本环境不支持创建符号链接: {error}")

    read_paths = []
    real_read_bytes = Path.read_bytes

    def recording_read_bytes(self, *args, **kwargs):
        read_paths.append(self)
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    with pytest.raises(ValueError, match="路径逃出"):
        review(task_dir)
    assert outside.resolve() not in [path.resolve() for path in read_paths]


@pytest.mark.parametrize("input_name", [TASK_JSON, QUALITY_CSV, COLOR_CSV])
def test_r08_symlinked_fixed_input_escaping_dir_is_rejected_before_read(
    tmp_path, monkeypatch, input_name,
):
    """固定 JSON/CSV 名称仍需拒绝真实符号链接逃逸，且不能先读取外部文件。"""
    task_dir, _, _ = make_task(tmp_path, (1,), name="fixed-input-escape")
    link = task_dir / input_name
    outside = tmp_path / f"outside-{input_name}"
    outside.write_bytes(link.read_bytes())  # 外部内容有效，避免格式错误掩盖路径缺陷。
    link.unlink()
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"本环境不支持创建符号链接: {error}")

    real_open = Path.open

    def reject_external_read(self, *args, **kwargs):
        if self.resolve() == outside.resolve():
            pytest.fail("拒绝路径逃逸之前读取了外部文件")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_external_read)
    with pytest.raises(ValueError, match="路径逃出"):
        review(task_dir)


def test_r08_injected_resolution_outside_dir_is_rejected(tmp_path, monkeypatch):
    """注入 `Path.resolve` 的流程探针；**不能**替代上面的真实符号链接测试。"""
    task_dir, run_id, _ = make_task(tmp_path, (1,), name="inject")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"sentinel")
    candidate = Path(task_dir).resolve() / f"camera_frame_{run_id}_1.png"
    target = Path.resolve(outside)
    real_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if self == candidate:
            return target
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="路径逃出"):
        review(task_dir)


def test_r08_missing_frame_does_not_hide_healthy_frame(tmp_path):
    task_dir, run_id, _ = make_task(tmp_path, (1, 2), name="partial")
    png_path(task_dir, run_id, 1).unlink()
    result = review(task_dir)
    assert result["verification_status"] == "inconsistent"
    assert result["counts"]["verified_frames"] == 1
    frames = {frame["frame_count"]: frame for frame in result["frames"]}
    assert frames[1]["image_sha256_match"] is None and frames[1]["metrics"] is None
    assert frames[2]["image_sha256_match"] is True
    assert frames[2]["metrics"] == EXPECTED_METRICS
    assert [issue["code"] for issue in result["issues"]] == ["frame_unverifiable"]
    assert cli(task_dir) == 1


# ---------- R09：口径不同只提示，不阻断、不误报故障 ----------

def test_r09_context_differences_are_warnings_only(tmp_path, capsys):
    task_dir, _, _ = make_task(tmp_path, (1,), name="context", metric_config={
        "dark_threshold": 10, "bright_threshold": 240,
    }, provenance={
        "runtime": {"python": "0.0.0", "opencv": "0.0.0", "numpy": "0.0.0"},
        "source_sha256": {"metrics.py": "0" * 64, "analysis_config.py": "1" * 64},
    })
    result = review(task_dir)
    assert result["verification_status"] == "consistent"   # 文件与指标照常完成
    assert result["issues"] == []
    assert result["counts"]["verified_frames"] == 1
    codes = [warning["code"] for warning in result["warnings"]]
    assert codes == ["measurement_context_differs"]
    detail = result["warnings"][0]["detail"]
    assert "metric_config.dark_threshold" in detail
    assert "runtime.opencv" in detail
    assert "source_sha256.metrics.py" in detail
    assert result["comparison_basis"] == "current_algorithm_one_decimal"
    assert cli(task_dir) == 0


def test_r09_missing_context_is_unavailable_warning(tmp_path):
    task_dir, _, _ = make_task(tmp_path, (1,), name="nocontext",
                               metric_config={}, provenance={})
    result = review(task_dir)
    assert result["verification_status"] == "consistent"
    assert [warning["code"] for warning in result["warnings"]] == ["measurement_context_unavailable"]


# ---------- R10：MemoryError 传播、重复调用不累加、输出 JSON ----------

def test_r10_memory_error_propagates(tmp_path, monkeypatch):
    task_dir, _, _ = make_task(tmp_path, (1,))

    def boom(*args, **kwargs):
        raise MemoryError("注入")

    monkeypatch.setattr("src.review_capture.compare_frame_metrics", boom)
    with pytest.raises(MemoryError):
        review(task_dir)


def test_r10_repeated_review_does_not_accumulate(tmp_path):
    task_dir, _, _ = make_task(tmp_path, (1,))
    reviewer = CaptureTaskReviewer(task_dir)
    first = reviewer.review()
    second = reviewer.review()
    assert first == second
    assert second["counts"] == {"reported_samples": 1, "csv_pairs": 1, "verified_frames": 1}


def test_r10_output_is_serializable_json(tmp_path, capsys):
    task_dir, _, _ = make_task(tmp_path, (1,))
    result = review(task_dir)
    assert json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False)) == result
    assert cli(task_dir) == 0
    assert json.loads(capsys.readouterr().out) == result


# ---------- R11：新旧入口独立调用；输入无增删改 ----------

def test_r11_new_entry_is_read_only_and_matches_old_interface(tmp_path):
    task_dir, run_id, _ = make_task(tmp_path, (1, 2, 3))
    before = snapshot(task_dir)

    result = review(task_dir)
    assert snapshot(task_dir) == before

    for frame in result["frames"]:
        direct = compare_frame_metrics(
            run_id, frame["frame_count"], task_dir,
            task_dir / QUALITY_CSV, task_dir / COLOR_CSV,
        )
        assert frame["metrics"] == {name: [saved, recomputed] for name, (saved, recomputed) in direct.items()}

    # 失败路径也不得改动输入
    png_path(task_dir, run_id, 2).unlink()
    failed = review(task_dir)
    assert failed["verification_status"] == "inconsistent"
    expected = [item for item in before if item[0] != f"camera_frame_{run_id}_2.png"]
    assert snapshot(task_dir) == expected  # 除测试自身删除的帧外，输入无增删改
