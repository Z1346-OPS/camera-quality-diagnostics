# camera-quality-diagnostics

基于 Python/OpenCV 的**图像质量测量、摄像头采集留证与 QR 自动化回归工具**。用于记录测量结果、核对采集证据，并复现识读链路的边界与失败恢复行为。

[![tests](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/workflows/tests.yml/badge.svg)](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/workflows/tests.yml)

## 已交付与验证

| 验证项 | 结果与范围 |
| --- | --- |
| 已验证代码基线 | [`6dba7c7`](https://github.com/Z1346-OPS/camera-quality-diagnostics/commit/6dba7c799754e90ef687d48fa99dca61445e58f5)，修正已提交并推送 |
| Ubuntu CI | [Actions #14](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/runs/39424609746)：**512 passed in 7.13s**；精确评测闸门单独执行并通过 |
| 固定合成 QR 回归 | development/test 各 **23 张**；每组正确读取数 **18/23 → 21/23**，配对比较 improved=3、degraded=0 |
| 历史 Windows 实采 | 2026-10-16，DirectShow，**3 轮 × 6 张 = 18 张**，摘要与指标核对一致；对应当时基线 `81b86e6` |

以上结果分别绑定代码版本与环境。最终修正包含取帧失败传播、Linux V4L2 后端选择、PNG 透明色处理和报告独占发布。[公开验收汇总](docs/verification/acceptance-summary-2026-10-27.md)附版本、CI 日志摘录与实采口径；历史候选记录已归档。

## 主要能力

- **采集与留证**：定时间隔采样，保存质量/颜色 CSV、原始帧 PNG 与任务 JSON；通过 `run_id`、帧号和 SHA-256 关联。
- **质量测量与复核**：亮度、曝光比例、清晰度、对比度与颜色统计；离线重算并核对报告和图片。
- **QR 识读验证**：整图、人工 ROI、内部降采样搜索；用独立答案逐字节核验，按冻结清单批量评测。
- **自动化回归**：pytest 参数化、假设备、可控时钟和故障注入；GitHub Actions 检查测试及固定数据集的精确期望。

## 快速运行：无需摄像头

使用 Python 3.12，在克隆后的项目根目录执行。安装依赖后，先运行一个已知答案样例。

### Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Path '.\data\reports' -Force | Out-Null
.\.venv\Scripts\python.exe -X utf8 src\analyze_label.py data\samples\stage2-known-qr.png --expected-file data\samples\stage2-known-qr.expected.txt --truth-source '固定合成样例' --output data\reports\qr-first-run-001.json
```

### Linux / Bash

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data/reports
.venv/bin/python -X utf8 src/analyze_label.py data/samples/stage2-known-qr.png --expected-file data/samples/stage2-known-qr.expected.txt --truth-source '固定合成样例' --output data/reports/qr-first-run-001.json
```

预期退出码为 0、`status=completed`，尝试与区域汇总中的 `truth_check.status=correct`。报告拒绝覆盖，再次运行请更换输出文件名。

完整回归与精确评测闸门：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
```

Linux 将解释器替换为 `.venv/bin/python`。还可运行[离线采集复核演示](docs/tasks/capture-review-walkthrough.md)，复现正常、缺失和篡改输入的处理流程。

## 三个工程设计

- **失败标志传播**：默认摄像头适配器显式检查 `grab()` / `retrieve()`；底层返回失败时，即使数组非空也不计为成功帧。见[读取边界防护](docs/stage-37-read-failure-guard.md)。
- **报告独占发布**：临时文件完整关闭后，用同目录硬链接发布；同名目标出现时拒绝覆盖，发布失败保留原始采集错误。见[发布修正](docs/stage-39-release-review-fixes.md)。
- **精确评测闸门**：先检查允许的退出状态与报告存在性，再精确比较稳定业务字段；区分预期解码失败与程序异常。见[数据集与闸门](docs/stage-33-synthetic-regression-dataset.md)。

## 验证范围

Windows 指定设备已有实采记录；Linux 的定时采集入口已选择 V4L2，并通过平台模拟测试及 Ubuntu CI，Linux 摄像头实机仍待验证。其他交互采集入口不属于此次 Linux 适配范围。

图像指标用于测量与复核，尚未标定工业合格阈值。合成数据结果只描述固定样本，实拍 QR 没有独立答案时仅记录读出状态。历史异常画面的根因仍未确认。报告发布要求文件系统支持硬链接，采集流程采用同步 I/O。

## 目录与文档

| 路径 | 内容 |
| --- | --- |
| `src/` | 图片/QR 分析、定时采集、报告与离线复核 |
| `tests/` | 指标、输入边界、异常传播、资源释放和输出保护测试 |
| `tools/` | 合成样本生成、精确期望闸门与受控模糊实验 |
| `data/samples/`、`data/manifests/` | 入库合成数据与评测清单 |
| `data/experiments/` | 固定模糊实验的计划、结果和退化样本 |
| `docs/` | 验收汇总、设计说明、使用指南与历史阶段记录 |
| `.github/workflows/tests.yml` | Ubuntu / Python 3.12 自动回归 |

- [公开验收汇总与 CI 证据](docs/verification/acceptance-summary-2026-10-27.md)
- [项目能力矩阵](docs/stage-34-project-capability-matrix.md)
- [详细使用与历史阶段指南](docs/project-guide.md)
- [简历项目描述与数字口径](docs/resume-project-summary.md)

`photo/`、`data/reports/` 和 `.venv/` 保留在本地；公开验收汇总不包含私人画面或二维码载荷。
