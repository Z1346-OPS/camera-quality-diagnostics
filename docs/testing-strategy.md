# 测试策略与缺陷回放

本页回答两个问题：每类风险由哪条测试负责；这些测试是否真的能抓住缺陷。第二个问题用**缺陷回放**回答：把已修复缺陷的修复撤销，确认至少有一条指定测试因该缺陷失败；恢复修复后再确认通过。

默认测试入口是 `pytest`，`pytest.ini` 设置 `testpaths = tests`，CI 在 Ubuntu 上额外运行冻结期望闸门（见 `.github/workflows/tests.yml`）。

## 1. 风险 → 测试对照

| 风险 | 测试类型 | 负责的测试（文件::函数） |
| --- | --- | --- |
| 读出内容被误记为“正确” | 单元测试 + 反例 | `tests/test_label_analysis.py::test_multiple_qr_is_ambiguous_even_when_one_matches`、`tests/test_label_analysis.py::test_retry_conflicts_cannot_be_resolved_using_truth`、`tests/test_quality_qr_analysis.py::test_no_truth_is_not_correct` |
| 数据集行为漂移，或“总数不变、成败互换” | 冻结期望回归（逐样本精确比对） | `tests/test_synthetic_dataset_expectations.py::test_synthetic_dataset_matches_expectations`，以及 CI 中的 `tools/check_evaluation_expectations.py` |
| 评测清单错误、分组泄漏、失败样本被移出分母 | 契约测试 | `tests/test_label_evaluation.py::test_group_leakage_checked_even_for_selected_split`、`tests/test_label_evaluation.py::test_bad_samples_remain_in_denominator_and_batch_continues`、`tests/test_label_evaluation.py::test_file_change_during_analysis_is_not_counted_as_correct` |
| 业务结果被包装成程序异常，或反过来 | CLI 退出码测试 | `tests/test_label_analysis.py::test_blank_is_not_decoded_not_execution_error`、`tests/test_label_analysis.py::test_decoder_exception_is_preserved_and_cli_nonzero`、`tests/test_label_evaluation.py::test_cli_sample_failure_is_structured_and_nonzero` |
| 取帧失败被计为成功（**F01**） | 测试替身 + 故障注入 | `tests/test_capture_task.py::test_default_factory_retrieve_failure_is_read_failed`、`tests/test_capture_task.py::test_grab_retrieve_adapter_rejects_nonempty_array_on_retrieve_failure` |
| 采集中断、异常被吞掉或被后续错误覆盖 | 故障注入 + 可控时钟 | `tests/test_capture_task.py::test_keyboard_interrupt_mid_capture`、`tests/test_capture_task.py::test_release_failure_does_not_replace_original_error`、`tests/test_capture_task.py::test_read_failure_returned_after_deadline_is_not_masked` |
| 报告覆盖已有文件（F02） | 竞争条件注入 | `tests/test_capture_task.py::test_publish_refuses_target_created_after_initial_check`、`tests/test_capture_task.py::test_publish_link_error_preserves_temp_without_fallback` |
| 平台后端选错 | 平台模拟 | `tests/test_capture_task.py::test_platform_default_factory_and_report` |
| 输入归一化改变测量对象：透明色（**F03**）、EXIF 方向 | 构造输入的单元测试 | `tests/test_analyze_image.py::test_png_transparent_color_is_composited_on_white`、`tests/test_analyze_image.py::test_png_transparent_color_preserves_opaque_pixels_and_orientation`、`tests/test_analyze_image.py::test_all_exif_orientations_move_pixels_correctly` |
| 坏文件、超限输入未被明确拒绝 | 边界值测试 | `tests/test_analyze_image.py::test_byte_limit_boundary`、`tests/test_analyze_image.py::test_pixel_limit_boundary`、`tests/test_analyze_image.py::test_truncated_valid_header_is_decode_error` |
| 复核时摘要与像素来自不同次读取（**F07**） | 读取时替换文件的注入测试 | `tests/test_review_capture.py::test_png_replacement_after_read_cannot_mix_hash_and_pixels` |
| 复核被篡改或缺失的证据蒙混过关 | 反例测试 | `tests/test_review_capture.py::test_r03_lossless_reencode_keeps_metrics_but_flags_hash`、`tests/test_review_capture.py::test_r04_missing_empty_broken_png_and_changed_csv`、`tests/test_review_capture.py::test_r08_symlinked_image_escaping_dir_is_rejected_before_read` |
| 指标计算错误 | 手算期望的单元测试 | `tests/test_metrics.py::test_bgr_means_preserve_opencv_channel_order`、`tests/test_metrics.py::test_sharpness_decreases_after_blurring`、`tests/test_review_capture.py::test_r01_constant_frame_matches_hand_derived_expectations` |
| 原图或冻结证据被改写 | 前后 SHA-256 对比 | `tests/test_blur_experiment.py::test_original_assets_and_frozen_evidence_unchanged` |
| 运行环境不是项目 `.venv` | 环境测试 | `tests/test_environment.py::test_running_in_virtual_environment` |

## 2. 缺陷回放

每个缺陷的“撤销修复”改动保存在 `docs/defect-replay/` 下，只改 `src/`，不改测试。在仓库根目录、项目 `.venv` 中复现：

```powershell
git apply docs/defect-replay/F01-undo-fix.patch
.\.venv\Scripts\python.exe -m pytest -q tests/test_capture_task.py   # 预期失败
git apply -R docs/defect-replay/F01-undo-fix.patch
.\.venv\Scripts\python.exe -m pytest -q tests/test_capture_task.py   # 预期全部通过
```

F03、F07 换成对应的补丁和测试文件即可。下列结果是 2026-11-20 在 Windows 11、Python 3.12.10 上，以提交 `d4e7b79` 为基础实测的。

### F01：失败的取帧被计为成功

- **缺陷**：底层 `grab()` 成功、`retrieve()` 返回 False，但输出数组非空。OpenCV 的 `VideoCapture.read()` 在 `grab()` 成功后不看 `retrieve()` 的返回值，只按输出是否为空判定成功（`grab()` 失败时会清空输出），所以修复前的默认路径把这次失败当成了有效帧。
- **修复**：`src/capture_task.py` 的默认工厂 `_default_camera_factory` 用 `_GrabRetrieveCamera` 包装设备，分别检查两个返回值。
- **撤销**：[`F01-undo-fix.patch`](defect-replay/F01-undo-fix.patch) 让默认工厂不再接入 `_GrabRetrieveCamera`，直接返回底层设备，恢复修复前的读取路径；适配器类本身和后端选择保留。
- **结果**：`tests/test_capture_task.py` 中 8 failed、107 passed。
  - **3 项复现了误判成功**：核心用例 `test_default_factory_retrieve_failure_is_read_failed` 和两项 `retrieve_failed` 平台用例，均为 `DID NOT RAISE`，即取帧失败的任务没有报错，而是跑完了。
  - **另 5 项是结构断言**：`normal`、`grab_failed` 用例在 `backend.read_calls == 0` 处失败，说明默认路径又调用了底层 `read()`；这 5 项的业务结果本身没有错。

```text
>       with pytest.raises(CaptureTaskError) as excinfo:
E       Failed: DID NOT RAISE CaptureTaskError
FAILED tests/test_capture_task.py::test_default_factory_retrieve_failure_is_read_failed
```

### F03：PNG 透明色没有按白底处理

- **缺陷**：RGB 或 L 模式的 PNG 可以用 tRNS 指定一种透明色。修复前只对调色板（P）模式识别这种透明，RGB/L 的透明像素按原色参与测量，改变了测量输入。
- **修复**：`src/analyze_image.py` 的 `load_normalized_image` 对所有带 `transparency` 信息的图像走白底合成。
- **撤销**：[`F03-undo-fix.patch`](defect-replay/F03-undo-fix.patch) 恢复为只对 P 模式识别 tRNS 透明色；RGBA/LA 的 alpha 处理不受影响。
- **结果**：`tests/test_analyze_image.py` 中 6 failed、45 passed，失败的正是两组透明色用例的全部 6 个参数组合。透明像素读成了原色 0，而不是白底 255：

```text
>       assert result["metrics"]["brightness"] == 255.0
E       assert 0.0 == 255.0
E        [0, 1, 0]: 0 (ACTUAL), 255 (DESIRED)
```

### F07：复核时摘要与像素重算用了不同次读取

- **缺陷**：离线复核先读一次 PNG 算 SHA-256，再由 `compare_frame_metrics()` 重新读文件算指标。两次读取之间文件被替换，摘要会来自旧文件，指标会来自新文件。
- **修复**：`src/review_capture.py` 只读一次，用同一份字节算摘要，并通过 `png_bytes=` 交给重算。
- **撤销**：[`F07-undo-fix.patch`](defect-replay/F07-undo-fix.patch) 去掉 `png_bytes=` 参数，让重算再次读文件。
- **结果**：`tests/test_review_capture.py` 中 1 failed、23 passed、4 skipped（跳过的是符号链接用例，见下节）。测试中，质量 CSV 记录的亮度是 200，任务 JSON 里记的是原 PNG 的 SHA-256，原图实际亮度是 100，第一次读取后文件被换成亮度 200 的图。撤销修复后，摘要与原记录一致，重算又读到了替换后的图，两者拼在一起，复核错误地给出了“一致”：

```text
>       assert result["verification_status"] == "inconsistent"
E       AssertionError: assert 'consistent' == 'inconsistent'
FAILED tests/test_review_capture.py::test_png_replacement_after_read_cannot_mix_hash_and_pixels
```

恢复修复后，上述三个测试文件合计 190 passed、4 skipped。

## 3. 未测内容及原因

- **Windows 上 4 项符号链接用例跳过**：`tests/test_review_capture.py` 中的 `test_r08_symlinked_image_escaping_dir_is_rejected_before_read`（1 项）和 `test_r08_symlinked_fixed_input_escaping_dir_is_rejected_before_read`（3 项）需要创建真实符号链接，Windows 普通用户权限下报 `WinError 1314`，测试以 `skip` 记录，不计为通过。它们在 Ubuntu CI 上运行。同类风险在 Windows 上另有 `test_r08_injected_resolution_outside_dir_is_rejected` 覆盖路径解析逻辑，但不等于真实符号链接。
- **Linux 摄像头没有实机验证**：Linux 下选择 V4L2 只经过平台模拟测试和 Ubuntu CI，没有接真实 Linux 摄像头。
- **真实 OpenCV 设备的取帧失败**：F01 的回归测试用假设备模拟 DirectShow 的行为，没有在真实设备上稳定复现 `retrieve()` 失败的场景；修复也不等于确认历史近黑画面的根因。
- **不支持硬链接的文件系统**：报告发布在这种环境下的报错只通过注入 `os.link` 失败来测试，没有在真实的此类文件系统上运行。
- **`tools/` 下的联合测试**：`tools/test_investigator_contract.py` 不在 `testpaths` 内，默认 `pytest` 和 CI 都不运行它。
- **实拍 QR 的识读率**：实拍批次没有独立答案，只记录单一读出、歧义和解码错误的数量（见[验收汇总](verification/acceptance-summary-2026-10-27.md)），不判定正确，也不代表实际场景的识读率。
