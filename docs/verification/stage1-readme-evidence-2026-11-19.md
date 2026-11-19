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
| 数据集设计与闸门反向测试 | [`stage-33-synthetic-regression-dataset.md`](../stage-33-synthetic-regression-dataset.md) |

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

`decode_error`（development）和 `ambiguous`（test）属于业务结果，不是程序异常，仍计入分母 23。

## 5. 逐样本：改进的 6 张

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

## 6. 结论边界

- 这些数字只描述这 46 张固定合成样本，不是识读率，也不能外推到实拍场景。
- `test` 组参加过历史回归，不是未见数据的盲测。
- 示例运行的结论只适用于 §1 所列的环境。
