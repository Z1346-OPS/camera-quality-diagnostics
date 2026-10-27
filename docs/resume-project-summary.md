# 简历项目描述与数字口径

核对日期：2026-10-27。对应[代码基线 6dba7c7](https://github.com/Z1346-OPS/camera-quality-diagnostics/commit/6dba7c799754e90ef687d48fa99dca61445e58f5)与[公开验收汇总](verification/acceptance-summary-2026-10-27.md)。本文只提供本项目的替换段落，不包含个人简历或联系方式。

## 可直接替换的项目段落

**图像质量测量与 QR 自动化回归工具｜Python、OpenCV、pytest、GitHub Actions**

- 搭建摄像头采集、图像质量测量与留证复核流程，通过 `run_id`、帧号及 SHA-256 关联 CSV、JSON 和原始帧；在 Windows/DirectShow 下完成 **3 轮、共 18 张图片**的指标与摘要核对。
- 构建整图、人工 ROI 与内部降采样搜索的 QR 识读验证链路，使用独立答案逐字节核验；在**两组各 23 张固定合成样本**上，正确读取数均由 **18 增至 21**，配对比较 improved=3、degraded=0。
- 利用 pytest 参数化、假设备与可控时钟覆盖输入边界、采集异常、资源释放及输出保护；修正 `grab/retrieve` 失败标志传播，完成 DirectShow/V4L2 后端选择适配。
- 接入 GitHub Actions 自动回归与精确期望值闸门，提交 `6dba7c7` 在 **Ubuntu CI 上 512 项测试全部通过**，两组评测结果与入库期望一致。

项目时间、职责和 AI 辅助分工应沿用本人确认的信息；上述成果不自动等同于全部代码独立完成。Linux 后端适配不写成 Linux 摄像头实机验证；历史实拍验收与最终代码 CI 各有对应版本。

## 统一替换规则

| 原表述或易混数字 | 本轮统一表述 | 依据 |
| --- | --- | --- |
| Ubuntu 虚拟机本地 501 项；最新测试 481/493/501 项 | 当前成果使用 **Ubuntu CI 512 项全部通过（6dba7c7 / Actions #14）**；原本地结果保留在历史记录，不重命名环境 | [CI 日志摘录](verification/ci-6dba7c7.json) |
| Windows 512 项全过 | **508 passed、4 skipped**，四项为真实符号链接权限限制 | [修正记录](stage-39-release-review-fixes.md) |
| 23 张 → 21 张；整体识别率提升 | **每组固定 23 张，正确读取 18/23 → 21/23；两组共 46 张，配对比较无退化** | [数据集记录](stage-33-synthetic-regression-dataset.md) |
| 3 轮、18 张但环境不明 | **2026-10-16，Windows/DirectShow，3×30 秒，每 5 秒留证，3×6=18 张** | [实采验收](tasks/real-use-acceptance-2026-10-16.md) |
| 适配 DirectShow/V4L2 | 保留，并明确是**后端选择适配**；Linux 自动化通过，未作 Linux 摄像头实机验收 | [Linux 适配](stage-38-linux-capture-backend.md) |
| 解决绿屏、确认黑帧根因 | **排查异常画面，修正取帧失败标志传播并补回归测试**；根因仍未确认 | [读取防护](stage-37-read-failure-guard.md) |
| 真实图片识读正确率 14/18 | **18 张中 14 张单一读出，未提供独立答案** | [实采验收](tasks/real-use-acceptance-2026-10-16.md) |

501→512 来自测试版本增量，不将其笼统归因为环境差异；508+4 与 512 则分别是 Windows 与 Ubuntu CI 的结果。测试数指 pytest 收集执行的用例项，含参数化实例。

## 简历文件应用状态

本轮已对齐上述项目段落与公开仓库的版本、环境和数字。现有简历 PDF/Word 未能读取出内容，本地文档编辑也受执行环境限制，因此**未修改原 PDF/Word 文件**。后续编辑简历时替换本项目及技能栏中相关的旧数字，保留其他经历、排版、照片与本人已确认的分工。
