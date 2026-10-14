# Phase 4.4：定时采集与间隔留证

- 日期：2026-10-14
- 状态：**已通过 Codex 验收与 DeepSeek 独立复核，README 收尾已完成**（2026-10-14；本节验证均在版本交付提交前执行，远程 CI 未运行）
- 第二轮：Codex 验收发现 3 个代码问题与 1 处文档误述，已修复并复验，见第 5 节
- 代码基线：HEAD = `afdca8f`（工作区含 Phase 4.1/4.2/4.3 的未提交成果，全部保留）
- 新增：`src/capture_task.py`、`src/run_capture.py`、`tests/test_capture_task.py`、
  `tests/test_run_capture.py`；本文件
- 修改（仅追加本次功能说明与受影响实测数字）：`README.md`、
  `docs/stage-34-project-capability-matrix.md`

> 说明：本文件第 1–2 节是**规格正文与验收条件**，在实现前写入，**不因实现结果放宽**。
> 实施记录与测试结果另列于第 3 节起。

---

## 1. 规格正文（实现前冻结）

新增无预览的定时采集入口：

```
.\.venv\Scripts\python.exe -X utf8 src\run_capture.py --camera-index 0 --duration 30 --interval 5 --output-dir data\reports\timed-capture\trial-001
```

### 1.1 参数

- `camera-index`：默认 0，非负整数，范围不超过有符号 32 位整数。
- `duration`：默认 30，整数秒，范围 1～3600。
- `interval`：默认 5，整数秒，范围 1～3600。
- `output-dir`：必填的新目录，已有空目录或同名文件也拒绝使用。
- 理论采样点数 `ceil(duration / interval)` 不得超过 120。
- `interval` 大于 `duration` 允许执行，此时只有一个理论采样点。
- API 参数也必须校验，布尔值不能作为整数接受。

3600 秒和 120 个采样点是**首版运行保护策略**，不是相机或质量阈值。

### 1.2 对象职责

`src/capture_task.py`：

- `CaptureConfig`：保存并校验配置，可使用 frozen dataclass。
- `CaptureRunner`：管理一次任务、设备生命周期、采样和结果。
- 提供可注入的摄像头工厂及单调时钟，供测试使用。
- 单个执行器仅执行一次任务，重复调用明确拒绝。
- 不引入通用插件、继承体系或复杂状态框架。

`src/run_capture.py`：

- 解析参数、调用执行器、输出必要提示、映射退出码。
- 支持从项目根直接运行。

首版真实设备支持当前 Windows 环境的 DirectShow。使用配置的设备编号打开摄像头，
**不调用固定设备 0、包含探测读帧的旧 `open_camera()`**。不重试、不切换后端、不自动重连。

### 1.3 严格采样规则

1. 摄像头成功打开后取得单调时钟起点 `t0`。
2. `elapsed = 当前单调时间 - t0`。
3. 每次 `read()` 前检查截止时间，已到时则不再读取。
4. `read()` 返回后重新取得 `elapsed`。
5. 读取失败或无效图像优先作为错误处理，不能因已经超时而掩盖失败。
6. 有效图像必须为非空 uint8 NumPy 数组，形状为 H×W×3，H、W 均大于 0。
7. 有效帧号按有效 `read()` 返回顺序从 1 递增。
8. 有效帧在 `elapsed >= duration` 时返回：计入有效帧数，但不保存为样本。
9. 截止前返回的有效帧所属区间为 `slot_index = floor(elapsed / interval)`。
10. 当前区间尚未采样时，选中这一帧；同一区间最多一个样本。
11. 跨过的旧区间不补采，不使用同一帧补多个样本。
12. 样本在截止前取得，但处理和保存跨过截止时间时，允许完成该样本；之后停止采集。
13. 正常到时结束至少需要一个完整样本，否则以 `no_samples` 失败。
14. 采集、测量和保存顺序执行，不累计原始帧数组。

以下预期直接写入测试，**不调用被测调度函数计算**：

| 编号 | 条件 | 预期 |
| --- | --- | --- |
| A | duration=6，interval=2；有效帧在 0.2、1.0、2.1、4.1、6.1 秒返回 | 保存第 1、3、4 帧，区间 0、1、2；`read_attempts=5`，`valid_frames=5`，`sample_attempts=3`，`samples_completed=3` |
| B | duration=6，interval=2；有效帧在 0.2、5.1、6.1 秒返回 | 保存第 1、2 帧，区间 0、2；不补区间 1 |
| C | duration=3，interval=5；有效帧在 0.2、1.0、3.1 秒返回 | 只保存第 1 帧 |
| D | duration=3，首个有效帧在 3.1 秒返回 | 不保存，`no_samples` 失败 |

另测首次有效帧已经进入后续区间、恰好位于区间边界和截止边界，以及保存耗时跨区间的情况。

本功能**不保证严格到时退出**。同步读取、测量及保存可能阻塞。记录实际时长，
不把请求时长冒充实测时长，不声明硬实时。

### 1.4 测量与输出

只对选中帧测量，复用既有函数：`brightness`、`dark_ratio`、`bright_ratio`、`sharpness`、
`contrast`、B/G/R 通道均值。使用现有 `analysis_config` 阈值及 CSV 精度，不改算法或默认值。
颜色记录 `scene_label` 固定为 `unspecified`。

所有保存接口都显式传入本次路径，**不写历史公共 CSV**。

单个新任务目录包含：

- `camera_quality_runs.csv`
- `camera_colors_runs.csv`
- `camera_frame_<run_id>_<frame_count>.png`
- `capture_task.json`

`run_id` 由程序生成，为 32 位小写十六进制 UUID，不接受 CLI 输入。
PNG 沿用已有命名，放在任务目录根下，兼容既有复核函数。
不生成旧会话 JSON，不调用 `save_session_metadata()`，避免写入 `camera_test_runtime` 来源。

一次采样：先计算指标 → 保存质量 CSV → 保存颜色 CSV → 保存 PNG → 计算成功 PNG 的 SHA-256。
任一步失败立即停止，不继续后续采样。已有成功内容保留，不回滚、不删除、不追加伪成功记录。

**禁止**调用 `imshow`、`putText`、`waitKey` 等预览或叠字接口，不修改输入数组。
实际命令输出放在新报告目录；测试输出放在临时目录。
不得将输出放入原图、合成样本、既有实验、冻结证据或源码目录。

### 1.5 任务报告契约

`capture_task.json` 使用 UTF-8 和严格 JSON，不允许 NaN/Infinity。

固定顶层字段：`schema_version`（1）、`report_type`（`camera_timed_capture`）、`run_id`、
`status`（`completed` / `failed` / `interrupted`）、`stop_reason`、
`config`（`camera_index`、`duration_seconds`、`interval_seconds`）、
`camera`（`requested_backend`=`CAP_DSHOW`、`actual_backend`、`first_frame_size`）、
`timings`（`started_at_utc`、`ended_at_utc`、`capture_elapsed_seconds`）、
`counts`（`planned_sample_slots`、`read_attempts`、`valid_frames`、`sample_attempts`、`samples_completed`）、
`metric_config`（`dark_threshold`、`bright_threshold`）、`samples`、
`primary_error`（null 或 `{stage, type, message}`）、`cleanup_errors`、
`provenance`（`implementation_version`=`timed-capture-1`、`runtime`、
`source_sha256`：本次两个源文件及 `metrics.py`、`analysis_config.py`、`report.py`、
`frame_evidence.py` 的摘要）。

来源摘要在打开设备前收集；收集失败明确报错，不带缺失来源继续采集。

设备元信息规则：`actual_backend` 取不到时写 null，不猜测；`getBackendName` 缺失或抛
`cv2.error` 时允许为 null；`first_frame_size` 记录第一个有效帧尺寸，没有有效帧为 null；
每个样本另记录自己的尺寸，不假设整个任务尺寸不变；不记录无法确认的曝光、对焦或照明状态。

计时规则：起点为成功打开后的 `t0`；终点为采集循环结束或因错误退出时；
`capture_elapsed_seconds` 包含采集和逐样本处理／保存，不包含打开设备、释放设备及最终报告发布；
尚未成功打开时，三个 timing 字段均为 null；UTC 时间用于留证，持续时间只使用单调时钟。

每个 `samples` 元素固定包含：`frame_count`、`slot_index`、`scheduled_elapsed_seconds`
（`slot_index × interval`）、`read_elapsed_seconds`、`width`、`height`、
`quality_status`、`color_status`、`image_status`、`image_file`（计划保存的相对文件名）、
`image_sha256`（成功保存且摘要取得后才有值，否则 null）。

三个保存状态取值：`not_attempted` / `written` / `failed`。
选中帧后即建立样本记录，计算指标失败也保留该记录；对应保存调用成功返回后才能标 `written`；
某步失败时该步标 `failed`，未执行步骤保持 `not_attempted`；
只有三步全部 `written` 且 PNG 摘要取得成功，才计入 `samples_completed`。

必须满足：
`read_attempts >= valid_frames >= sample_attempts >= samples_completed`；
`sample_attempts == len(samples)`；`samples_completed` 与完整样本记录逐项统计一致；
`sample_attempts` 不超过 `planned_sample_slots`。

### 1.6 异常、清理与发布

`stop_reason` 使用：`duration_reached`、`no_samples`、`open_failed`、`read_failed`、
`invalid_frame`、`measurement_failed`、`save_failed`、`interrupted`、`execution_error`、
`release_failed`。

- 正常到时且至少一个完整样本、没有执行／释放错误：`completed`。
- 首个导致任务退出的异常作为 `primary_error`。
- 首个异常为 `KeyboardInterrupt`：`interrupted`。
- 其他失败：`failed`。
- API 对逻辑失败抛 `CaptureTaskError`；对底层异常保留原异常类型。
- API 只有正常完成且报告成功发布才返回报告。
- 运行中出现 `MemoryError` 等未预期异常，不转成质量问题、不吞掉。
- 摄像头对象一旦取得，无论打开检查、读取、保存或中断怎样结束，都尝试释放。
- 已有 `primary_error` 时，释放失败加入 `cleanup_errors`，不替换原异常。
- 没有原错误但释放失败，任务改为 `failed`、`release_failed`。
- 尽力发布最终报告；不能因报告发布失败覆盖原始执行异常。
- 同时出现执行和报告错误时，两者都必须在终端或异常附注中明确暴露。

CLI：

- 正常完成且报告发布成功：0。
- 参数错误及 `CaptureTaskError`、`OSError`、`ValueError`、`cv2.error`：2，并明确提示。
- `KeyboardInterrupt`：130。
- 其他未预期异常保留回溯和非零退出。
- 不允许「打印错误但返回 0」。

正式报告先写同目录的新临时文件，完整关闭后再发布。正式目标已存在必须拒绝，
不允许无条件覆盖。中途写入失败不得留下半截的正式 `capture_task.json`；
残留临时文件明确视为未完成产物。本阶段单个任务独占新目录，不允许并发共享任务目录。

---

## 2. 验收条件（外部可核验）

1. **T01 参数**：正常值、默认值、零、负数、非整数、布尔值、超限；
   理论点数恰好 120 和超过 120；`interval` 大于 `duration`。
2. **T02 启动保护**：非法配置、已有目录／文件、受保护输出路径在打开摄像头前拒绝；
   已有内容摘要不变。
3. **T03 调度**：执行 1.3 节 A～D 及边界场景；检查帧号、区间、计数、保存次数，无重复补采。
4. **T04 数据**：每个模拟帧具有不同的已知像素；保存 PNG 与被选中帧逐像素相同，
   输入数组不变；预览、叠字和按键函数一旦被调用就让测试失败。
5. **T05 指标**：使用均匀已知图验证均值与零方差；使用现有独立指标测试作为算法基础；
   成功任务使用既有五项复核函数核对所有样本。
6. **T06 读取故障**：打开失败、`read` 返回失败、None、空数组、错误 dtype／通道；
   首个及中途读取失败；截止后返回失败仍不得伪装正常结束。
7. **T07 保存故障**：分别注入质量 CSV、颜色 CSV、PNG 编码／写入／摘要读取失败；
   核对已成功文件保留、后续步骤未执行、计数不伪报完整。
8. **T08 部分失败与旧复核**：质量 CSV 成功、颜色 CSV 失败时，现有复核工具应拒绝不完整批次，
   不修改或放宽旧工具。若要核对此前完整样本，在测试临时副本中提取完整配对记录后复核，
   不改变实际任务产物。
9. **T09 中断与异常**：模拟 `KeyboardInterrupt`、`MemoryError`、`cv2.error` 和其他执行异常；
   验证状态、原始异常、终止采样及释放。不实际耗尽内存、填满磁盘或强行挂死设备。
10. **T10 清理与报告**：释放失败、原错误与释放错误同时发生；临时报告写入失败、
    正式目标冲突、发布失败；验证原错误不被覆盖、不返回成功、不发布截断 JSON。
11. **T11 格式与计数**：严格 JSON、字段与取值、相对图片名、摘要、计数等式；
    设备信息未知时为 null；重复调用同一执行器拒绝。
12. **T12 CLI**：直接入口 `--help`；非法参数 exit 2；正常、已定义失败、中断的退出行为。
    CLI 流程测试必须注入模拟设备，不依赖 CI 上的真实摄像头。

必要测试命令（不加 `--refresh`，不预填测试数量，不跳过或弱化旧测试）：

```
.\.venv\Scripts\python.exe -m pytest -q tests\test_capture_task.py tests\test_run_capture.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
```

对关键修复优先给出能够触发原问题的反例；不为做反例破坏项目原文件。

### 2.1 实机验收

自动化测试通过后：在新目录执行 30 秒、5 秒间隔采集；核对所有完整样本的 PNG、CSV、摘要及
五项指标；使用另一新目录再次执行 10 秒、5 秒间隔采集，验证设备能再次打开；
记录实际采样数量、时间和异常，不强求恰好取得理论样本数；
实机结果不能表述为硬实时、工业稳定性或识读准确率结论。

摄像头不可用或被占用：如实记录实机验收未完成，不关闭其他程序，不改系统权限，
不用模拟测试冒充实机通过。

---

## 3. 基线与保护检查（实施前）

| 检查 | 结果 |
| --- | --- |
| 会话 cwd | `D:\Projects\Python\camera-quality-diagnostics`（项目根） |
| HEAD | `afdca8f`（`docs(agents): point number source at the capability matrix`） |
| `git status` | 既有未提交改动全部保留：`README.md`、`docs/stage-34-project-capability-matrix.md` 已修改；`data/experiments/`、`docs/observations/`、`docs/stage-35/36-*.md`、`docs/tasks/evidence/`、`docs/tasks/phase-4.1/4.2/4.3-*.md`、`src/quality_analysis.py`、`src/quality_qr_analysis.py`、`tests/test_blur_experiment.py`、`tests/test_quality_analysis.py`、`tests/test_quality_qr_analysis.py`、`tools/run_blur_experiment.py` 为未跟踪文件 |
| 基线 pytest | `343 passed in 23.01s`，exit 0（本轮实际执行，非历史记录） |
| 基线评测闸门 | 两个 split 均「与入库期望完全一致」，exit 0，未 `--refresh` |
| 环境 | 项目 `.venv`（Python 3.12.10），未安装新依赖 |

保护对象摘要（SHA-256 前 16 位，实施前）：

```
aacc497766125024  src/metrics.py
fd04ccd4c4efa84a  src/analysis_config.py
8639c22e21a9d287  src/report.py
8fc04c08b2b1293f  src/frame_evidence.py
28e8efc6a16cc8c3  src/camera_test.py
733c5e6aa006675d  src/check_reports.py
ab0b3e05bd8e2b08  src/verify_frame_metrics.py
47aaa0f528a17b7e  src/verify_run_metrics.py
5ad8ef2b06ee3e43  data/manifests/evaluation-synthetic-expectations.json
```

---

## 4. 实施记录（执行者填）

### 4.1 实际修改文件

新增：

```
src/capture_task.py            （CaptureConfig / CaptureRunner / 报告发布）
src/run_capture.py             （CLI 入口与退出码映射）
tests/test_capture_task.py     （84 项，T01–T11）
tests/test_run_capture.py      （19 项，T12）
docs/tasks/phase-4.4-timed-capture.md  （本文件）
```

修改（只增加本次功能说明及受影响实测数字）：

```
README.md                                  （新增「定时采集与间隔留证（业务阶段 4.4）」小节、
                                            运行命令、目录结构两行；测试数 343→446、24→26 文件）
docs/stage-34-project-capability-matrix.md （§0 测试行与源模块行、2026-10-14 说明；
                                            §1 新增能力行 11；§4「已具备」测试数 446）
```

未修改：`src/metrics.py`、`src/analysis_config.py`、`src/report.py`、`src/frame_evidence.py`、
`src/camera_test.py`、`src/check_reports.py`、`src/verify_frame_metrics.py`、
`src/verify_run_metrics.py`、`data/manifests/*`、`tests/` 下既有测试、`data/samples/`、
`photo/`、`docs/tasks/evidence/`。未 commit / 未 push / 未切分支 / 未 `--refresh`。

### 4.2 T01–T12 覆盖位置与结果

全部 103 项通过。文件名统一为 `tests/test_capture_task.py`（除 T12）。

| 编号 | 覆盖用例（位置） | 结果 |
| --- | --- | --- |
| T01 参数 | `test_config_defaults`、`test_config_accepts_upper_bounds`、`test_config_rejects_invalid_values`（14 组，含布尔/浮点/字符串/越界）、`test_config_requires_output_dir`、`test_planned_slots_boundary_120`（恰好 120 与 121）、`test_interval_greater_than_duration_allows_single_slot` | 通过 |
| T02 启动保护 | `test_config_rejects_existing_directory`、`test_config_rejects_existing_file_and_keeps_content`、`test_existing_output_directory_content_unchanged`、`test_config_rejects_protected_output_paths`（8 条受保护路径）、`test_rejected_config_never_reaches_camera_factory` | 通过 |
| T03 调度 | `test_schedule_example_a/b/c/d`（硬编码预期，不调用被测调度）、`test_first_frame_in_later_slot_does_not_backfill`、`test_frame_exactly_on_interval_boundary`、`test_frame_exactly_at_deadline_is_counted_but_not_saved`、`test_duplicate_frames_in_same_slot_produce_one_sample`、`test_sample_completes_when_saving_crosses_deadline`、`test_capture_elapsed_is_measured_not_requested` | 通过 |
| T04 数据 | `test_saved_png_matches_selected_frame_and_input_unchanged`、`test_no_preview_or_key_functions_are_called`（`imshow`/`putText`/`waitKey`/`namedWindow`/`getWindowProperty`/`destroyAllWindows` 一律替换为抛错桩） | 通过 |
| T05 指标 | `test_uniform_frame_gives_known_mean_and_zero_variance`（均值 100.0、四项零方差）、`test_successful_task_passes_existing_five_metric_verification`（对全部样本调用既有 `reconcile_reports` + `compare_frame_metrics`）、`test_metrics_match_metric_module_on_saved_png` | 通过 |
| T06 读取故障 | `test_open_failure_writes_report_without_timings`、`test_camera_factory_returning_none_is_open_failure`、`test_first_read_failure`（7 组：None/空数组/0×0/灰度/四通道/float32/uint16）、`test_mid_capture_read_failure_keeps_saved_sample`、`test_read_failure_returned_after_deadline_is_not_masked` | 通过 |
| T07 保存故障 | `test_quality_save_failure_stops_later_steps`、`test_color_save_failure_keeps_quality_csv`、`test_png_encode_failure_keeps_csvs`、`test_png_write_failure_marks_image_failed`、`test_png_digest_failure_is_not_counted_complete` | 通过 |
| T08 部分失败与旧复核 | `test_partial_failure_and_legacy_tools_reject_incomplete_batch`（第 2 帧颜色 CSV 失败 → `reconcile_reports` 报出仅质量单侧记录、`verify_run_metrics` 退出码 2；随后在**临时副本**中提取完整配对记录复核，实际产物字节未变） | 通过 |
| T09 中断与异常 | `test_keyboard_interrupt_mid_capture`、`test_keyboard_interrupt_during_save_is_interrupted`、`test_unexpected_exception_propagates_unchanged`（`MemoryError`）、`test_cv2_error_from_camera_is_preserved`、`test_sampling_stops_after_exception` | 通过 |
| T10 清理与报告 | `test_release_failure_alone_makes_task_failed`、`test_release_failure_does_not_replace_original_error`、`test_publish_refuses_existing_target`、`test_temp_write_failure_leaves_no_partial_report`、`test_publish_failure_does_not_override_execution_error`（核对 `__notes__`）、`test_publish_failure_on_successful_capture_raises`、`test_json_serialization_rejects_non_finite` | 通过 |
| T11 格式与计数 | `test_report_is_strict_json_with_fixed_fields_and_counts`、`test_task_directory_contains_only_expected_files`、`test_device_metadata_null_when_unknown`、`test_no_valid_frame_keeps_first_frame_size_null`、`test_per_sample_size_is_recorded_independently`、`test_runner_rejects_repeated_run`、`test_saves_always_use_explicit_task_paths`、`test_public_reports_are_not_touched`、`test_requested_camera_index_is_used` | 通过 |
| T12 CLI | `tests/test_run_capture.py`：`test_cli_help_exits_zero`、`test_cli_argparse_errors_exit_2`（6 组）、`test_cli_range_validation_returns_2`（7 组）、`test_cli_rejects_existing_output_dir_before_opening_camera`、`test_cli_success_returns_0`、`test_cli_defined_failure_returns_2`、`test_cli_interrupt_returns_130`、`test_cli_unexpected_exception_keeps_traceback`（全部注入模拟设备） | 通过 |

### 4.3 关键修复与反例

| 缺陷 | 触发它的反例 | 处理 |
| --- | --- | --- |
| 抛异常的 `read()` 未计入 `read_attempts`（只统计了「返回成功」的读取） | `test_keyboard_interrupt_mid_capture` 断言 `read_attempts == 2` 时实际为 1 | 把计数移到 `camera.read()` **之前**；`test_cv2_error_from_camera_is_preserved` 追加 `read_attempts == 1`、`valid_frames == 0` 断言 |

### 4.4 实际命令、退出码与测试数量

| 命令 | 结果 |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q tests\test_capture_task.py tests\test_run_capture.py` | **103 passed**（84 + 19），exit 0 |
| `.\.venv\Scripts\python.exe -m pytest -q` | **446 passed in 21.11s**，exit 0（基线 343 + 本轮 103） |
| `.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py` | 两个 split 均「与入库期望完全一致」，exit 0，**未 `--refresh`** |
| `src\run_capture.py --help` | exit 0 |
| `src\run_capture.py --duration 0 --output-dir …` | `参数错误: duration 必须在 1～3600 之间`，exit 2 |
| `src\run_capture.py --output-dir <已存在目录>` | `参数错误: 输出目录已存在，拒绝使用`，exit 2，未创建任何目录 |

### 4.5 实机运行结果与新产物位置

环境：本机内置摄像头（设备 0），项目 `.venv`（Python 3.12.10 / OpenCV 5.0.0 / NumPy 2.5.3），
后端实际为 `DSHOW`，帧尺寸 640×480。

| 运行 | 目录 | 请求 | `capture_elapsed_seconds` | 计划/实际样本 | 读取次数 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `data/reports/timed-capture/trial-001` | 30 秒 / 5 秒 | 30.016 | 6 / 6 | 892 | `completed` / `duration_reached`，退出码 0 |
| 2 | `data/reports/timed-capture/trial-002` | 10 秒 / 5 秒 | 10.016 | 2 / 2 | 293 | `completed` / `duration_reached`，退出码 0 |

- 运行 1 的 6 个样本（帧号 1/142/292/442/592/742，区间 0–5）：`verify_run_metrics`
  逐帧复核 **6 帧一致、0 数值不同、0 无法复核**，退出码 0；PNG 的 SHA-256 与报告逐项相同。
- 运行 2 验证设备可**再次打开**：2 个样本（帧号 1/143）逐帧复核一致，退出码 0。
- 两次进程总耗时分别约 31.8 秒与 11.6 秒，差值来自打开与释放设备；报告只记录采集段实际时长。
- 实际采样数量与理论值一致，但**这不构成**硬实时、工业稳定性或识读准确率结论。

### 4.6 未完成项、限制与范围外发现

- **未完成**：第一轮自测阶段为「无」。**该结论已被后续 Codex 验收推翻**：三个独立反例失败
  （CLI 丢失报告发布附加错误、仅释放失败时底层异常被转换成 `CaptureTaskError`、
  发布阶段中断覆盖先前执行错误），另有一处能力矩阵误述。修复与复验见第 5 节；
  第一轮自测记录按原样保留，不删除、不改写。
- 本功能的**固有限制**（已写入 README 与能力矩阵）：不保证严格到时退出；同步读取、
  测量与保存可能阻塞；只支持本机单设备的 DirectShow；不重试、不切换后端、不自动重连；
  不并发、不断点续跑；不生成质量评分或故障判定。
- **范围外发现（未修改）**：`docs/stage-34-*.md` 第 0 节「入库文件 155 个」与当前
  `git ls-files`（156 个，其中 `docs` 为 43）存在既有偏差；该数字不受本次改动影响，
  按任务约束**不修正**。
- 实机运行中相机自动曝光与画面内容变化，各样本亮度/清晰度差异明显；本任务不做归因。

### 4.7 既有资产与文件范围检查

- `git diff --stat` 仅 `README.md`、`docs/stage-34-project-capability-matrix.md`（均在批准范围内）。
- `git status` 的未跟踪文件与实施前一致，仅新增本次 5 个文件；Phase 4.1/4.2/4.3 的
  未提交成果与未跟踪文件全部保留。
- 保护对象 SHA-256（前 16 位）实施前后**完全一致**：`metrics.py` `aacc497766125024`、
  `analysis_config.py` `fd04ccd4c4efa84a`、`report.py` `8639c22e21a9d287`、
  `frame_evidence.py` `8fc04c08b2b1293f`、`camera_test.py` `28e8efc6a16cc8c3`、
  `check_reports.py` `733c5e6aa006675d`、`verify_frame_metrics.py` `ab0b3e05bd8e2b08`、
  `verify_run_metrics.py` `47aaa0f528a17b7e`、
  `data/manifests/evaluation-synthetic-expectations.json` `5ad8ef2b06ee3e43`。
- 输出只落在新任务目录：`data/reports/timed-capture/trial-001`、`trial-002`
  （`data/reports/` 本就被 `.gitignore` 忽略）；测试输出在 pytest 临时目录；
  未向原图、合成样本、既有实验、冻结证据或源码目录写入任何内容；无 `*.tmp` 残留。
- 未新增依赖、未改动数据集、未刷新评测期望。

## 5. Codex 验收反例修复与复验（2026-10-14，第二轮）

第一轮交付后由 Codex 独立验收。原有 103 项新增测试、446 项全量、评测闸门均通过，
但 Codex 的三个独立反例失败，另有一处文档误述。本节记录修复与复验；第 1–4 节保留第一轮历史。

### 5.1 三个代码问题：位置与处理

**问题 1 —— CLI 丢失报告发布的附加错误。**
`src/capture_task.py` 原本只把发布错误写成 `__notes__` 里的自由文本，`src/run_capture.py`
只打印 `str(error)`，用户看不到发布失败。处理：

- `capture_task.py` 新增 `_secondary_note(kind, stage, error)`，附加错误文本固定包含
  **阶段、异常类型与信息**（如 `报告发布失败 阶段=report 类型=OSError 信息=…`）。
- `run_capture.py` 新增 `_print_failure(prefix, error)`：打印主错误后逐条打印
  `附加错误: <note>` 到 stderr；`KeyboardInterrupt`、`CaptureTaskError`、
  `OSError/ValueError/cv2.error` 三个分支都改用它，退出码保持不变。

**问题 2 —— 仅释放失败时底层异常类型被转换。**
`_release_camera` 原本只返回 `{"type","message"}` 字典，丢弃异常对象，`run()` 收尾再抛
新的 `CaptureTaskError`。处理：

- `_release_camera` 改为返回 `(cleanup_errors 条目, 首个释放异常对象)`，**保留异常对象**。
- `run()` 收尾改为「首个错误优先」：`primary_exception = 执行错误 or 释放错误`。
  没有更早执行错误时，**直接重新抛出原始释放异常对象**（`MemoryError`、`OSError`、
  `cv2.error` 均保留类型与对象，回溯保留）。
- 已有执行错误时仍以执行错误为主，释放错误作为附加清理错误写入 `__notes__`（可见但不替换）。
- 释放异常为 `KeyboardInterrupt` 时按中断处理：`status=interrupted`、`stop_reason=interrupted`，
  **不转成普通逻辑失败**。
- `primary_error` 字段：仅释放失败时仍保持 `null`，错误记录在 `cleanup_errors`
  （本轮未要求改为非空；修复的是异常传播，不是字段）。

**问题 3 —— 发布阶段的中断覆盖先前执行错误。**
`run()` 原本只 `except Exception` 捕获发布错误，`KeyboardInterrupt` 会逃逸并覆盖原异常。处理：

- 发布阶段改为 `except BaseException`：发布阶段的 `Exception` 或 `KeyboardInterrupt`
  都只作为附加错误记录，**不替换**先前的执行错误；附加错误在 `__notes__` 与 CLI stderr 中可见。
- 没有先前执行错误时，发布错误（含 `KeyboardInterrupt`）**正常传播**，不被吞掉、不返回成功。

### 5.2 文档误述修正

`docs/stage-34-project-capability-matrix.md` 第 11 行原写「**非阻塞**采样流程」，与实现不符
（采用同步读取、测量与保存）。已改为「**定时**采样流程」，并在「不可声称」列明确写出
「采用**同步**读取、测量与保存，可能阻塞，**不保证严格到时退出**」。README 同节亦已写明该限制。

### 5.3 三个独立反例：修复前后结果

Codex 反例文件（只读使用，未修改）：
`C:\Users\zex\.codex\visualizations\2026\10\12\01a12ed0-11d7-7d13-be87-0c4bd858475b\phase44_review\test_independent_contract.py`

运行方式（显式指定 rootdir / confcutdir / basetemp，`-B -p no:cacheprovider`，不向项目写缓存）：

```
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider ^
  --rootdir=<review-dir> --confcutdir=<review-dir> --basetemp=<review-dir>\independent-temp ^
  <review-dir>\test_independent_contract.py
```

| 反例 | 修复前 | 修复后 |
| --- | --- | --- |
| `test_cli_exposes_secondary_report_failure` | **FAILED**（CLI 丢弃发布失败，stderr 无标记） | **passed** |
| `test_release_only_preserves_memory_error` | **FAILED**（得到 `CaptureTaskError`，非原始 `MemoryError`） | **passed** |
| `test_publication_interrupt_does_not_replace_read_error` | **FAILED**（得到 `KeyboardInterrupt`，原 `OSError` 被覆盖） | **passed** |

修复前实测 `3 failed in 0.28s`；修复后实测 `3 passed in 0.21s`。

### 5.4 补充到项目测试文件的必要回归

按同一独立预期补充（不改预期迁就实现），共新增 8 项：

- `tests/test_capture_task.py`：
  - `test_release_failure_alone_preserves_original_exception`（`MemoryError` / `OSError` / `cv2.error` 三组，断言 `observed is release_error` 与报告状态）
  - `test_release_keyboard_interrupt_is_not_a_logical_failure`
  - `test_publication_interrupt_does_not_replace_earlier_error`
  - `test_publication_error_alone_propagates`（`OSError` / `KeyboardInterrupt` 两组）
- `tests/test_run_capture.py`：
  - `test_cli_exposes_secondary_report_failure`（检查 CLI 实际 stderr 含阶段与类型）
  - `test_cli_interrupt_exposes_secondary_report_failure`

**原有用例调整说明**：`test_release_failure_alone_makes_task_failed` 原先断言
「释放失败应抛 `CaptureTaskError`」，与「保留底层异常」的规格冲突。该用例**保留未删**，
改写为 `test_release_failure_alone_preserves_original_exception`：断言**原始异常对象与类型**
（`observed is release_error`）以及报告状态（`status=failed`、`stop_reason=release_failed`、
`primary_error=null`、`cleanup_errors` 一条、`samples_completed=1`）。检查强度未降低。

### 5.5 测试、全量回归与闸门（修复后实测）

| 命令 | 结果 |
| --- | --- |
| Codex 三个独立反例 | **3 passed**（修复前 3 failed） |
| `pytest -q tests\test_capture_task.py tests\test_run_capture.py` | **111 passed**（原 103 + 本轮 8），exit 0 |
| `pytest -q` | **454 passed in 20.50s**，exit 0 |
| `check_evaluation_expectations.py` | 两个 split 与入库期望完全一致，exit 0，**未 `--refresh`** |

### 5.6 最终源码版本的实机复验

`trial-001`、`trial-002` 记录的是修复前源码摘要（`capture_task.py` = `b11059f6…`），
不能作为最终版本证据；两个历史目录**原样保留、未覆盖、未改写报告、未替换其中摘要**。
源码修复完成后，使用**两个新目录**重新验收：

| 运行 | 目录 | 请求 | `capture_elapsed_seconds` | 计划/实际样本 | 读取次数 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `data/reports/timed-capture/trial-003` | 30 秒 / 5 秒 | 30.0 | 6 / 6 | 892 | `completed`，退出码 0 |
| 2 | `data/reports/timed-capture/trial-004` | 10 秒 / 5 秒 | 10.0 | 2 / 2 | 293 | `completed`，设备可再次打开，退出码 0 |

- 五项指标复核：`verify_run_metrics` 对 trial-003 报 **6 帧一致、0 数值不同、0 无法复核**，
  对 trial-004 报 **2 帧一致**，均退出码 0。
- PNG 摘要：两个目录全部样本的 SHA-256 与报告逐项一致。
- **报告记录的六个源码摘要与最终源码逐项一致**（实测）：

  ```
  capture_task.py   b1c45c29b72f…   run_capture.py    b34e30d38433…
  metrics.py        aacc49776612…   analysis_config.py fd04ccd4c4ef…
  report.py         8639c22e21a9…   frame_evidence.py  8fc04c08b2b1…
  ```

- 计数与采样记录符合原规格（`read_attempts ≥ valid_frames ≥ sample_attempts ≥ samples_completed`，
  `sample_attempts == len(samples)`，实际样本数等于理论值，但不据此声称硬实时或工业稳定性）。
- 本轮修复**只改了 `src/capture_task.py` 与 `src/run_capture.py`**，其余被记录源码未动；
  实机验收后未再修改任何被记录的源码文件。

### 5.7 保护对象与改动范围检查（第二轮）

- 修改仅在允许范围：`src/capture_task.py`、`src/run_capture.py`、
  `tests/test_capture_task.py`、`tests/test_run_capture.py`、
  `docs/tasks/phase-4.4-timed-capture.md`、`docs/stage-34-project-capability-matrix.md`、`README.md`。
- Phase 4.1–4.3 成果、正式实验产物（`data/experiments/`）、冻结证据（`docs/tasks/evidence/`）
  与既有测试未改动；`git diff` 仍只涉及 `README.md` 与能力矩阵两份已批准文档。
- 第一轮实机报告 `trial-001`、`trial-002` 未改写（`capture_task.py` 摘要仍为 `b11059f6…`）。
- 未新增临时脚本或调试代码；测试输出在 pytest 临时目录；任务目录无 `*.tmp` 残留。
- 未 commit / 未 push / 未切分支 / 未 `--refresh` / 未运行样本生成器。

## 6. 验证记录（验证者填）

### 6.1 Codex 独立复验

- 三个此前失败的独立反例复跑：**3 passed in 0.23s**。分别验证 CLI 附加发布错误可见、仅释放失败保留原始 `MemoryError` 对象、发布中断不替换更早的读取错误。
- Phase 4.4 专项测试：**111 passed in 1.36s**；全量回归：**454 passed in 29.76s**；评测闸门退出码 0，两组均与入库期望完全一致，未 `--refresh`。
- 对 `trial-003` 的 6 个样本与 `trial-004` 的 2 个样本逐帧重算五项指标，共 40 项比较全部一致；全部 PNG 摘要及两份报告中的六个源码摘要与最终源码一致。
- 168 项冻结资产逐项一致；289 个受核对项目文件在复验前后无变化。本轮未重新启动摄像头，实机部分为既有产物核验。

### 6.2 DeepSeek 独立复核及 Codex 证据确认

- DeepSeek 报告记录：仓库外独立套件 **107 passed**、项目专项 **111 passed**、全量 **454 passed in 26.44s**，评测闸门通过；未发现所检查范围内的程序缺陷。
- 独立测试覆盖多阶段错误优先级、区间及截止边界、跳过区间不补采、无效输入、部分保存、输出保护和报告发布失败。未用被测调度函数反向生成调度期望。
- Codex 阅读外部测试后实际复跑：**107 passed in 1.13s**；实机产物核验与补充探针的失败列表均为空。脚本打印零失败之外，另对失败列表显式断言，不仅依赖脚本退出码。
- Codex 复跑前后 289 个受核对项目文件完全一致；没有重新采集，没有修改历史报告。

### 6.3 文档收尾与最终验收

- README 的 CI 说明已去掉过期的固定数量 446，改为引用能力矩阵，并明确本地测试通过不代表对应提交的远程 CI 已通过。
- 此次文档收尾后 Codex 实跑：**454 passed in 32.74s**；评测闸门退出码 0，两组与入库期望一致；`git diff --check` 通过。289 个受核对文件中仅 README 的一段文字变化，源码、数据及历史报告未变。
- **结论：Phase 4.4 在已批准范围内验收通过。** 本节记录真实发生的验证，不修改第 1–2 节规格与验收条件，不重写第 4–5 节历史实施及失败记录；后续 Git 提交是当前版本交付，不是实施前规格冻结的补造。
- **限制：** 本机 Windows 与项目 `.venv`；未运行对应提交的远程 CI，未做跨机器或依赖升级验证；不声明零缺陷、硬实时、工业稳定性、质量合格或识读准确率。
