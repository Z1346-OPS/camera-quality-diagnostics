# camera-quality-diagnostics

基于 Python/OpenCV 的**图像质量测量、摄像头采集留证与 QR 自动化回归工具**，用固定样本、独立答案和精确期望闸门验证识读链路的行为与失败边界。

[![tests](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/workflows/tests.yml/badge.svg)](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/workflows/tests.yml)

**结果入口：** [有证据的结果](#有证据的结果)（QR 回归：baseline 与内部降采样搜索的配对比较） · [缺陷案例 F01](#缺陷案例-f01失败的取帧被计为成功) · [验证边界](#验证边界) · [逐样本证据](docs/verification/stage1-readme-evidence-2026-11-19.md) · [亮点说明](docs/highlights.md)（oracle、故障注入、证据完整性、如实报告）

## 可运行示例：无需摄像头

使用 Python 3.12，在克隆后的项目根目录执行。

### Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Path '.\data\reports' -Force | Out-Null

# A：提供独立答案
.\.venv\Scripts\python.exe -X utf8 src\analyze_label.py data\samples\stage2-known-qr.png --expected-file data\samples\stage2-known-qr.expected.txt --truth-source '固定合成样例' --output data\reports\qr-first-run-001.json

# B：不提供答案
.\.venv\Scripts\python.exe -X utf8 src\analyze_label.py data\samples\stage2-known-qr.png --output data\reports\qr-first-run-002.json
```

### Linux / Bash

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data/reports
.venv/bin/python -X utf8 src/analyze_label.py data/samples/stage2-known-qr.png --expected-file data/samples/stage2-known-qr.expected.txt --truth-source '固定合成样例' --output data/reports/qr-first-run-001.json
.venv/bin/python -X utf8 src/analyze_label.py data/samples/stage2-known-qr.png --output data/reports/qr-first-run-002.json
```

| 运行 | 预期退出码 | 预期 `truth_check.status` | 含义 |
| --- | --- | --- | --- |
| A | 0 | `correct` | 只有一个有效码，且载荷与独立答案逐字节相同 |
| B | 0 | `not_provided` | 只报告读出，没有答案就不判定为正确 |

以上预期值已在 Windows 11 的项目 `.venv`（Python 3.12.10）中实测，代码版本 `0904038`，样本为单张合成图 `stage2-known-qr.png`，见[首页证据](docs/verification/stage1-readme-evidence-2026-11-19.md#2-两次示例运行)。Linux 命令没有在本机实测。报告拒绝覆盖已有文件，再次运行请更换输出文件名。

完整回归与精确评测闸门：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -rs
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
```

Linux 将解释器替换为 `.venv/bin/python`。

## 有证据的结果

**比较的是什么：** 同一批固定合成 QR 样本，先用 **baseline**（zxing-cpp 单次解码，关闭内部降采样）读取，再用 **启用内部降采样搜索**的方式读取（在 baseline 之外，再做一次开启 zxing-cpp 内部降采样的尝试，两次结果汇总）。每张图都用独立答案逐字节判定是否 `correct`。

| 结果 | 数字 | 样本范围 | 绑定版本与环境 | 证据 |
| --- | --- | --- | --- | --- |
| 固定合成 QR 回归 | 每组 baseline 正确读取 **18/23**，启用内部降采样搜索后 **21/23**；每组改进 3、退化 0 | `synthetic-qr-v1` 的 development 组、test 组，各 23 张程序生成的固定样本 | CI：提交 [`6dba7c7`](https://github.com/Z1346-OPS/camera-quality-diagnostics/commit/6dba7c799754e90ef687d48fa99dca61445e58f5)，Ubuntu 24.04.5，Python 3.12.15；本地复核：代码版本 `0904038`，Windows 11，Python 3.12.10，2026-11-19 | [逐样本证据](docs/verification/stage1-readme-evidence-2026-11-19.md#6-逐样本改进的-6-张)、[入库期望](data/manifests/evaluation-synthetic-expectations.json)、[CI 日志摘录](docs/verification/ci-6dba7c7.json) |
| 自动化测试 | CI **512 passed**；Windows 本地 **509 passed、4 skipped**（4 项真实符号链接用例因 WinError 1314 权限不足跳过，不计为通过） | 默认收集的 `tests/` 全部产品测试 | CI：`6dba7c7`，Ubuntu 24.04.5，Python 3.12.15，[Actions #14](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/runs/39424609746)；本地：代码版本 `0904038`，Windows 11，Python 3.12.10，2026-11-19 | [公开验收汇总](docs/verification/acceptance-summary-2026-10-27.md)、[首页证据](docs/verification/stage1-readme-evidence-2026-11-19.md#3-自动化测试本地) |
| 历史 Windows 实采 | **3 轮 × 6 张 = 18 张**留证图片，摘要与指标核对一致 | 单台设备，正常照明，640×480，每轮 30 秒、每 5 秒留证 | 2026-10-16，当时基线 `81b86e6`，Windows，DirectShow；不是最终修正后的新实机验收 | [公开验收汇总](docs/verification/acceptance-summary-2026-10-27.md#历史-windows-实采验收) |

关于合成 QR 回归的读法：

- 两组共 46 张，都是程序生成的固定样本。失败样本保留在分母里。
- 改进的 6 张是两组 `noise-large` 退化族的第 21–23 号样本：baseline `not_decoded`，启用降采样搜索后 `correct`。
- **test 组参加过历史回归，不是未见数据的盲测**，数字不代表实拍场景的识读率。
- 闸门按样本 ID 比对图片与答案的 SHA-256，再逐区域核对结果。即使两个样本成败互换、总数不变，也会报出具体样本。见[亮点说明 · Oracle 设计](docs/highlights.md#1-oracle-设计)。

## 缺陷案例 F01：失败的取帧被计为成功

| 项 | 内容 |
| --- | --- |
| 触发条件 | 底层 `grab()` 成功、`retrieve()` 返回 False，但输出数组非空。DirectShow 会在取像素之前预分配数组，而 `cv2.VideoCapture.read()` 只按数组是否为空判断成功 |
| 错误结果 | 修复前，这次失败被当作有效帧，任务报告 `completed` 并保存了样本 |
| 修复位置 | [`src/capture_task.py`](src/capture_task.py) 中的 `_GrabRetrieveCamera.read`。默认工厂 `_default_camera_factory` 用它包装设备，分别检查 `grab()` 和 `retrieve()` 的真实返回值，任一失败返回 `(False, None)`，转入既有的 `read_failed` 流程。随提交 [`6dba7c7`](https://github.com/Z1346-OPS/camera-quality-diagnostics/commit/6dba7c799754e90ef687d48fa99dca61445e58f5) 进入仓库 |
| 能抓住它的测试 | [`tests/test_capture_task.py`](tests/test_capture_task.py) 中的 `test_default_factory_retrieve_failure_is_read_failed`：经真实默认工厂驱动假设备，断言 `failed` / `read_failed`、有效帧 0、样本 0，并且没有调用底层 `read()`。辅助用例：`test_grab_retrieve_adapter_rejects_nonempty_array_on_retrieve_failure` |
| 修复前后 | 先写测试、后修复。修复前，核心用例在旧代码上行为失败（`DID NOT RAISE CaptureTaskError`）；修复后，该组 12 个目标用例全部通过。记录时间 2026-10-17，环境为 Windows 11、Python 3.12.10、OpenCV 5.0.0、pytest 9.1.1，代码为基线 `81b86e6` 加上尚未提交的修复；这份修复中的适配器代码与 `6dba7c7` 一致。数字组成见[首页证据](docs/verification/stage1-readme-evidence-2026-11-19.md#5-缺陷案例-f01-的修复前后记录) |
| 结论边界 | 只修复了这条状态传播缺陷，**不等于**确认了历史近黑画面的根因 |

详见[亮点说明 · 故障注入与可控环境](docs/highlights.md#2-故障注入与可控环境)。同一轮修正中的报告独占发布见[亮点说明 · 证据完整性](docs/highlights.md#3-证据完整性)；PNG 透明色处理等其余修正见开发日志中的[发布修正记录](docs/archive/stage-39-release-review-fixes.md)。撤销这处修复的补丁和失败输出见[测试策略 · F01 回放](docs/testing-strategy.md#f01失败的取帧被计为成功)。

## 验证边界

- **合成数据**：结果只描述固定样本；实拍 QR 没有独立答案时，只记录读出或未读出。
- **图像指标**：用于测量与复核，尚未标定工业合格阈值。脏污、条纹、噪点、偏色等故障不做自动识别。
- **平台**：Windows 指定设备有实采记录。Linux 定时采集入口已选择 V4L2，通过平台模拟测试和 Ubuntu CI，Linux 摄像头实机仍待验证。其他交互采集入口不在 Linux 适配范围内。
- **运行条件**：报告发布要求文件系统支持硬链接；采集流程采用同步 I/O。
- **未确认事项**：历史异常画面的根因仍未确认。

## 目录与文档

| 路径 | 内容 |
| --- | --- |
| `src/` | 图片/QR 分析、定时采集、报告与离线复核 |
| `tests/` | 指标、输入边界、异常传播、资源释放和输出保护测试 |
| `tools/` | 合成样本生成、精确期望闸门与受控模糊实验 |
| `data/samples/`、`data/manifests/` | 入库合成数据与评测清单 |
| `data/experiments/` | 固定模糊实验的计划、结果和退化样本 |
| `docs/` | 公开文档（见下）；`docs/archive/` 为开发日志 |
| `.github/workflows/tests.yml` | Ubuntu / Python 3.12 自动回归 |

- [亮点说明](docs/highlights.md)：oracle 设计、故障注入、证据完整性、如实报告，各附证据
- [测试策略与缺陷回放](docs/testing-strategy.md)：风险与测试的对照表；撤销 F01、F03、F07 的修复后，指定测试如何失败，附可复现补丁
- [架构与退出码契约](docs/architecture.md)
- [公开验收汇总与 CI 证据](docs/verification/acceptance-summary-2026-10-27.md)
- [首页证据：示例运行与逐样本结果](docs/verification/stage1-readme-evidence-2026-11-19.md)
- [离线采集复核演示](docs/capture-review-walkthrough.md)：复现正常、缺失和篡改输入的处理流程
- [开发日志归档](docs/archive/README.md)：按时间保留的原始记录，不代表当前能力

`photo/`、`data/reports/` 和 `.venv/` 保留在本地；公开验收汇总不包含私人画面或二维码载荷。

## 未来方向

后续拟探索二维码读取失败后的原因分析与恢复建议。
