# 架构

本页说明模块分工、数据流、报告字段和退出码契约，以及已实现与未实现的边界。各项内容均对照当前 `src/` 代码整理；行为细节以代码为准。四个亮点的说明见[亮点说明](highlights.md)。

## 模块

| 链路 | 入口（CLI） | 实现 | 职责 |
| --- | --- | --- | --- |
| 本地图片质量 | `src/analyze_image.py` | `metrics.py`、`analysis_config.py` | 读入一张 JPEG/PNG，不改原图字节，输出亮度、曝光比例、清晰度、对比度、颜色均值等测量值 |
| QR 识读 | `src/analyze_label.py` | `label_analysis.py` | 对整图或人工 ROI 解码，可选内部降采样搜索；有独立答案时逐字节核对 |
| QR 批量评测 | `src/evaluate_labels.py` | `label_evaluation.py` | 按清单批量评测，比较 baseline 与降采样搜索，输出逐样本结果和配对变化 |
| 冻结期望闸门 | `tools/check_evaluation_expectations.py` | — | 运行真实评测 CLI，把报告与 `data/manifests/evaluation-synthetic-expectations.json` 精确比对 |
| 定时采集 | `src/run_capture.py` | `capture_task.py`、`frame_evidence.py`、`report.py` | 按时长和间隔采集，保存留证 PNG、质量与颜色 CSV、任务报告 |
| 采集复核 | `src/review_capture.py` | `verify_frame_metrics.py` | 只读复核一个采集任务目录：CSV 配对、PNG 摘要、从 PNG 重算指标 |
| 质量与 QR 关联 | — | `src/quality_qr_analysis.py` 的 Python 函数 `analyze_quality_and_qr()`（没有命令行入口），使用 `quality_analysis.py` | 把同一张图、同一区域的质量测量与 QR 报告关联，只输出测量事实，不给出质量结论 |

`src/` 下还有早期的交互采集与只读汇总脚本，如 `camera_test.py`、`main.py`、`check_reports.py`、`summarize_*.py`，它们不在上述主链路中。`tools/` 是生成与校验脚本，`src/` 不依赖它。

## 数据流

```text
QR 识读与回归
  data/samples/*.png + 独立答案 ──► analyze_label ──► 报告 JSON（decode + truth_check）
  data/manifests/*.json ──► evaluate_labels ──► 评测报告 JSON ──► check_evaluation_expectations ──► 通过 / 失败
                                                          ▲
                                     evaluation-synthetic-expectations.json（逐样本冻结期望）

定时采集与复核
  摄像头（或注入的假设备 + 时钟）──► run_capture
      ├─► camera_quality_runs.csv / camera_colors_runs.csv（run_id + 帧号配对）
      ├─► 留证 PNG
      └─► capture_task.json（独占发布：临时文件 + os.link）
                 │
                 ▼
  review_capture ──► 复核 JSON（consistent / inconsistent / not_reviewed）
      读一次 PNG：同一份字节既算 SHA-256，又重算指标，与 CSV 和任务记录比对
```

## 报告字段（要点）

| 报告 | 关键字段 |
| --- | --- |
| QR 识读（`report_type: label_baseline`，`schema_version: 2`） | `status`（`completed` / `completed_with_errors`）；每个区域的 `attempts[].decode`；汇总 `decode.status`（`decoded`、`not_decoded`、`ambiguous`、`conflict`、`decode_error`、`execution_error`）；`truth_check.status`（`not_provided`、`correct`、`incorrect`，或沿用解码状态）；`provenance`（源码 SHA-256、运行库版本） |
| QR 批量评测（`report_type: label_evaluation`） | `status`；`results[]` 中每个样本的 `comparisons[]`，按区域分别给出 `baseline` 和 `with_downscale_search`；`summaries`（outcome 计数、正确率分母、`paired_change`）；`evaluation_policy.selection_uses_truth: false` |
| 定时采集（`report_type: camera_timed_capture`） | `run_id`；`status`（`completed`、`failed`、`interrupted`）与 `stop_reason`；`counts`（读取次数、有效帧、完整样本）；`samples[]`（帧号、时间槽、尺寸、质量/颜色/图片的保存状态、`image_file` 与 `image_sha256`；指标数值写在两份 CSV 中）；`primary_error` / `cleanup_errors`；`provenance.source_sha256` |
| 采集复核 | `verification_status`；`frames[]` 中的 `image_sha256_match`，以及 `metrics` 的“保存值 / 重算值”对；`issues[]`（如 `image_hash_mismatch`、`metric_mismatch`、`frame_unverifiable`、`csv_keys_mismatch`）；`warnings[]` |

`truth_check` 的规则：没有独立答案时为 `not_provided`。只有解码汇总为单一有效码（`decoded`），且载荷与答案逐字节相同，才为 `correct`。见 `src/label_analysis.py` 的 `check_expected()`。

写入磁盘的报告以独占方式新建，目标已存在时报错；`src/review_capture.py` 的复核 CLI 把 JSON 输出到 stdout，不写文件。

## 退出码

| CLI | 0 | 1 | 2 | 其他 |
| --- | --- | --- | --- | --- |
| `analyze_image.py` | 分析完成 | — | 输入或输出错误，比如目标文件已存在；不写出报告 | — |
| `analyze_label.py` | `completed`，包括未读出、歧义、答案不匹配这些业务结果 | — | ① `completed_with_errors`：有解码尝试 `decode_error` 或 `execution_error`，报告已写出；② 程序级失败，报告未写出 | — |
| `evaluate_labels.py` | `completed` | — | ① `completed_with_errors`：有样本出现解码错误，报告已写出；② 程序级失败（`EvaluationError`、`OSError`、`MemoryError`），报告未写出 | — |
| `review_capture.py` | `consistent` | `inconsistent` | `not_reviewed`（任务未完成），或输入无法读取 | — |
| `run_capture.py` | 任务完成 | — | 参数错误、采集失败或任务未正常完成；失败任务仍会尽力发布 `status: failed` 的报告 | 130：键盘中断 |

**退出码 2 的两种含义靠“是否生成报告 JSON”区分。** 闸门 `tools/check_evaluation_expectations.py` 的 `run_evaluation()` 接受评测 CLI 的退出码 0 和 2，然后检查输出文件：没有生成报告 JSON 就判为评测进程异常并失败；生成了报告，就逐项对照冻结期望。未读出、歧义、答案不匹配都是业务结果，不会被当作程序异常。

## 已实现与未实现

| 已实现 | 尚未实现 |
| --- | --- |
| 摄像头采集与定时留证；亮度、曝光比例、清晰度、对比度、颜色通道均值；读帧失败事件记录 | 脏污、条纹、噪点、偏色等故障的自动识别 |
| 按批次保存 CSV/JSON；留证 PNG 与指标重算复核 | 场景阈值标定、标签可读性的合格判定 |
| 本地 JPEG/PNG 质量分析；QR 解码（整图、人工 ROI、内部降采样搜索） | 手机上传、数据库、服务化 |
| 按清单批量评测；固定答案逐字节校验；精确冻结期望闸门 | 离线 HTML 报告导出、批量图片质量分析入口、结构化设备与拍摄条件字段 |

平台边界：

- Windows 指定设备有实采记录。
- Linux 定时采集入口选择 V4L2，通过了平台模拟测试和 Ubuntu CI，但 Linux 摄像头实机仍待验证。
- 报告发布要求文件系统支持硬链接。

详见 [README 验证边界](../README.md#验证边界)和[公开验收汇总](verification/acceptance-summary-2026-10-27.md#支持范围)。
