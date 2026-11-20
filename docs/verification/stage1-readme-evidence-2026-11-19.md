# 首页证据：示例运行与逐样本结果（2026-11-19）

本文件为首页 README 中的示例和结果提供可核对的出处。所有路径均为仓库内受跟踪的文件；本机生成的报告位于被 `.gitignore` 忽略的 `data/reports/`，因此这里只记录其摘要值。

## 1. 运行环境

| 项 | 值 |
| --- | --- |
| 代码版本 | `0904038064e5fe102fc101b2c794418abd5121d1`（`main`），工作区仅有文档改动 |
| 平台 | Windows 11，PowerShell |
| 运行时 | Python 3.12.10、OpenCV 5.0.0、NumPy 2.5.3、Pillow 12.3.0、zxing-cpp 3.1.1 |
| 日期 | 2026-11-19 |

报告中 `provenance.git.working_tree_dirty=true`，原因是运行时 README 与 `docs/` 有未提交的文档改动；`src/` 未改动。

## 2. 两次示例运行

输入图片 [`data/samples/stage2-known-qr.png`](../../data/samples/stage2-known-qr.png)，SHA-256 `465430eb…57198`（264×264，灰度 PNG）。

| 运行 | 命令要点 | 退出码 | `status` | `truth_check.status` | 输出报告 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| A：提供独立答案 | `--expected-file data\samples\stage2-known-qr.expected.txt --truth-source '固定合成样例'` | 0 | `completed` | `correct`（尝试与区域汇总均是） | `7ec15a31…84af9` |
| B：不提供答案 | 不加 `--expected-file` | 0 | `completed` | `not_provided`（尝试与区域汇总均是） | `527afcfc…a9861` |

两次都读出同一个有效码，载荷为 `STAGE2-SMOKE-001`。答案文件 [`stage2-known-qr.expected.txt`](../../data/samples/stage2-known-qr.expected.txt) 的 SHA-256 为 `a014ba8a…681781`，与报告 `known_truth.sha256` 一致。

运行 B 说明：没有独立答案时，工具只报告"读出"，**不**判定为正确。

## 3. 自动化测试（本地）

在 §1 环境执行 `.\.venv\Scripts\python.exe -X utf8 -m pytest -q -rs`，退出码 0，结果行：

```text
509 passed, 4 skipped in 28.07s
```

4 项跳过都来自 `tests/test_review_capture.py`（L476 一项、L504 参数化三项），原因是 `[WinError 1314] 客户端没有所需的特权`：本机不能创建真实符号链接。跳过不计为通过。

这与 2026-10-20 的 Windows 记录 `508 passed、4 skipped`（绑定 `6dba7c7`）相差 1 项：之后的提交 `aa77a72` 新增了 `test_png_replacement_after_read_cannot_mix_hash_and_pixels`。CI 的 `512 passed` 同样只绑定 `6dba7c7`。

## 4. 固定合成 QR 回归：数字出处

| 内容 | 出处 |
| --- | --- |
| 入库精确期望（汇总与逐样本） | [`data/manifests/evaluation-synthetic-expectations.json`](../../data/manifests/evaluation-synthetic-expectations.json)；development 汇总 [L5–L41](../../data/manifests/evaluation-synthetic-expectations.json#L5-L41)，test 汇总 [L277–L313](../../data/manifests/evaluation-synthetic-expectations.json#L277-L313) |
| 样本清单 | [`evaluation-synthetic-development.json`](../../data/manifests/evaluation-synthetic-development.json)、[`evaluation-synthetic-test.json`](../../data/manifests/evaluation-synthetic-test.json) |
| CI 原始日志摘录（提交 `6dba7c7`，Actions #14，Ubuntu 24.04.5，Python 3.12.15） | [`ci-6dba7c7.json`](ci-6dba7c7.json) |
| 数据集设计与闸门反向测试 | [亮点说明 · Oracle 设计](../highlights.md#1-oracle-设计)；原始记录 [`archive/stage-33-synthetic-regression-dataset.md`](../archive/stage-33-synthetic-regression-dataset.md) |

提交 `ea2a1be` 把期望文件升级为 schema v2，新增了逐样本记录；两组的汇总计数与 `6dba7c7` 时相同。

本次在 `0904038` 上本地执行 `tools\check_evaluation_expectations.py`（未加 `--refresh`），退出码 0，原始输出：

```text
=== development ===
  样本 23   status=completed_with_errors
  baseline               正确 18/23   correct=18  decode_error=1  not_decoded=4
  with_downscale_search  正确 21/23   correct=21  decode_error=1  not_decoded=1
  paired_change: improved=3 degraded=0 分母=23
  ✅ 与入库期望完全一致

=== test ===
  样本 23   status=completed
  baseline               正确 18/23   ambiguous=1  correct=18  not_decoded=4
  with_downscale_search  正确 21/23   ambiguous=1  correct=21  not_decoded=1
  paired_change: improved=3 degraded=0 分母=23
  ✅ 与入库期望完全一致

闸门通过：数据集行为与入库期望一致。
```

两组的非正确样本含义不同：

- development 有 1 个样本发生候选码解码错误（`decode_error`），所以批量评测状态是 `completed_with_errors`，评测 CLI `src/evaluate_labels.py` 返回 2。
- test 有 1 个样本结果歧义（`ambiguous`），这是识读结论，不是错误，所以评测状态是 `completed`，评测 CLI 返回 0。

本机直接运行评测 CLI 复核过：development 退出码 2，test 退出码 0。

两组都保留 23 个样本作分母。闸门 `tools/check_evaluation_expectations.py` 接受退出码 0 和 2，但不依据退出码判断结果，而是读取生成的 JSON 报告，逐项对照冻结期望。两组实际结果都与期望一致，所以闸门返回 0。

退出码 2 还有另一个用途：程序级失败。`src/evaluate_labels.py` 第 28–32 行在 `EvaluationError`、`OSError`、`MemoryError` 时打印 `评测失败 [...]` 并返回 2，这时不会写出报告 JSON。闸门靠"是否生成报告 JSON"区分这两种退出码 2：没有报告就判为评测进程异常并失败（见 `tools/check_evaluation_expectations.py` 中的 `run_evaluation`）。

## 5. 缺陷案例 F01 的修复前后记录

README 中 F01 的"修复前失败、修复后 12 个目标用例通过"来自 2026-10-17 的本地验证记录，摘要见[亮点说明 · 故障注入与可控环境](../highlights.md#2-故障注入与可控环境)，数字的原始记录为 [`archive/stage-37-read-failure-guard.md`](../archive/stage-37-read-failure-guard.md) §4–§5。原始输出在本机被忽略的目录 `data/reports/read-failure-guard-20261017-101037-9d36a959/` 中，未入库。

| 项 | 值 |
| --- | --- |
| 代码 | 基线 `81b86e6` 加上尚未提交的修复（`src/capture_task.py`、`tests/test_capture_task.py`）。修复后来随 `6dba7c7` 提交；2026-11-19 复核：把当时保存的差异应用到 `81b86e6` 后，`_GrabRetrieveCamera` 与 `6dba7c7` 中的实现一致，其余差异只来自同一提交里的 V4L2 后端选择和报告发布改动 |
| 环境 | Windows 11（10.0.26100）、Python 3.12.10、OpenCV 5.0.0、NumPy 2.5.3、pytest 9.1.1 |
| 命令 | `pytest tests/test_capture_task.py -k "grab_retrieve or default_factory" -q -rA` |
| 修复前 | `6 failed, 6 passed, 90 deselected`，`EXIT=1` |
| 修复后 | `12 passed, 90 deselected`，`EXIT=0` |

修复前的 6 个失败不都是行为失败：

- 4 个是 `AttributeError`：旧代码里还没有 `_GrabRetrieveCamera` 类，直接测试适配器的用例无法运行。
- 核心用例 `test_default_factory_retrieve_failure_is_read_failed` 是行为失败（`Failed: DID NOT RAISE CaptureTaskError`）：旧代码把失败的取帧当成功帧处理。
- `test_default_factory_normal_frame_pixels_and_review_unchanged` 是断言失败（`assert 4 == 0`，旧代码调用了底层 `read()`）。

因此 README 只引用"核心用例行为失败"这一结论，不把 6 个失败都当作缺陷证据。

## 6. 逐样本：改进的 6 张

两组改进的都是 `noise-large` 退化族的 21–23 号样本，结果都是 baseline `not_decoded` → 降采样搜索 `correct`。两组都没有退化样本。

| 样本 ID | 图片 | 期望记录 |
| --- | --- | --- |
| `synthetic-qr-v1-development-21` | [dev-21-noise-large-noise25-q50-A.png](../../data/samples/synthetic-qr-v1/development/dev-21-noise-large-noise25-q50-A.png) | [L243](../../data/manifests/evaluation-synthetic-expectations.json#L243) |
| `synthetic-qr-v1-development-22` | [dev-22-noise-large-noise22-q60-B.png](../../data/samples/synthetic-qr-v1/development/dev-22-noise-large-noise22-q60-B.png) | [L253](../../data/manifests/evaluation-synthetic-expectations.json#L253) |
| `synthetic-qr-v1-development-23` | [dev-23-noise-large-persp-noise25-q50-C.png](../../data/samples/synthetic-qr-v1/development/dev-23-noise-large-persp-noise25-q50-C.png) | [L263](../../data/manifests/evaluation-synthetic-expectations.json#L263) |
| `synthetic-qr-v1-test-21` | [test-21-noise-large-noise25-q50-A.png](../../data/samples/synthetic-qr-v1/test/test-21-noise-large-noise25-q50-A.png) | [L515](../../data/manifests/evaluation-synthetic-expectations.json#L515) |
| `synthetic-qr-v1-test-22` | [test-22-noise-large-noise22-q60-B.png](../../data/samples/synthetic-qr-v1/test/test-22-noise-large-noise22-q60-B.png) | [L525](../../data/manifests/evaluation-synthetic-expectations.json#L525) |
| `synthetic-qr-v1-test-23` | [test-23-noise-large-persp-noise25-q50-C.png](../../data/samples/synthetic-qr-v1/test/test-23-noise-large-persp-noise25-q50-C.png) | [L535](../../data/manifests/evaluation-synthetic-expectations.json#L535) |

每条期望记录同时固定了图片与答案的 SHA-256。闸门先按样本 ID 核对这两个摘要，再逐区域比较结果。

## 7. 结论边界

- 这些数字只描述这 46 张固定合成样本，不是识读率，也不能外推到实拍场景。
- `test` 组参加过历史回归，不是未见数据的盲测。
- 示例运行的结论只适用于 §1 所列的环境。
