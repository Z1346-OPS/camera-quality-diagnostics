# 交付候选历史说明（2026-10-20）

> 2026-10-27 补记：下文是提交前的候选快照。列出的修改与新增文件已随 `6dba7c799754e90ef687d48fa99dca61445e58f5` 提交并推送；[Actions #14](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/runs/39424609746) 为 512 passed、两组精确闸门通过。当前交付状态见[公开验收汇总](../verification/acceptance-summary-2026-10-27.md)。正文中的“未提交”“待纳入”仅描述当时状态。

## 目标与身份

本候选承接 `delivery-candidate-2026-10-18.md`、`stage-38-linux-capture-backend.md` 与本次审查修正。10 月 18 日说明和本文均保留为历史快照，当前范围见页首补记。

- 分支 `main`；HEAD 仍为 `81b86e6d6b2b264890d2229e12856b7ef15b19ea`。
- 当前候选 = 上述 HEAD + 下面列出的未提交文件。不能将该 HEAD 单独称为包含最新修正的版本。
- 本轮仅修改和验证工作区，没有暂存、提交、推送、打标签或正式发布。

## 候选文件清单

已修改：

- `src/analyze_image.py`：RGB/L PNG 透明色按既定白底策略处理。
- `src/capture_task.py`：既有 grab/retrieve 失败传播、Linux V4L2 后端适配，以及本轮独占硬链接发布报告。
- `tests/test_analyze_image.py`：6 项透明色回归。
- `tests/test_capture_task.py`：既有 12 项读取防护、8 项平台/结果组合，以及本轮 5 项发布回归。
- `tests/test_quality_qr_analysis.py`：独立读取当前源码摘要，并验证缺失/篡改摘要必须失败；业务 oracle 不改。
- `README.md`、`AGENTS.md`、`docs/stage-34-project-capability-matrix.md`：当前入口、支持范围、复现说明和验证数字。

新增、待纳入版本：

- `pytest.ini`
- `docs/stage-37-read-failure-guard.md`
- `docs/stage-38-linux-capture-backend.md`
- `docs/stage-39-release-review-fixes.md`
- `docs/tasks/real-use-acceptance-2026-10-16.md`
- `docs/tasks/delivery-candidate-2026-10-18.md`
- `docs/tasks/release-review-2026-10-20.md`
- `docs/tasks/delivery-candidate-2026-10-20.md`

不纳入本次提交：`data/reports/`、`photo/`、`.venv/`、任何本轮临时副本/备份或真实图片载荷。入库合成样例、历史实验产物及评测期望保持原字节。

## 验收依据

最新数字的统一入口为 `docs/stage-34-project-capability-matrix.md` 第 0 节。本次最终 Windows 结果为 **508 passed、4 skipped**，精确评测闸门与依赖检查通过。四项跳过是 Windows 创建真实符号链接权限不足，不计作本机通过。

新源码副本中已完成 QR 已知答案导出、同名拒绝覆盖、图片分析和合成采集/复核 CLI 冒烟，复用已有 `.venv`；没有重新安装依赖。失败过程和修正依据见 `docs/stage-39-release-review-fixes.md`，原审查见 `docs/tasks/release-review-2026-10-20.md`。

历史 `2629e57` 的 Ubuntu CI 481 passed 不覆盖当前源码；历史 493 和本次修正前 497+4 也不是修正后的结果。10 月 16/17 日的实机记录只属于各自当时源码，不是本轮新实机验收。

## 支持范围与已知限制

| 范围 | 当前说明 |
| --- | --- |
| 图片分析、QR 整图/ROI/降采样、清单评测 | 已有自动化与合成回归；只提供测量/识读和独立真值核验，不提供工业故障诊断或合格阈值 |
| Windows 定时采集 | 请求 DirectShow；既有指定设备实机记录 + 当前自动化防护/发布验证，未承诺其他型号或长期稳定性 |
| Linux 定时采集 | 代码请求 V4L2，平台选择与失败传播有模拟测试；当前版本没有 Linux 实机结果，不宣称 Linux 真实采集验收完成 |
| 报告发布 | 输出文件系统须支持硬链接；本机 NTFS 已验证；不支持时明确失败并保留临时文件，不以覆盖写降级 |
| 首次 JSON 导出 | README 先创建报告父目录，重复运行更换文件名；JSON CLI 不自动创建父目录 |
| 真实 QR 正确性 | 无独立已知答案时仅报告读出/未读出，truth 为 not_provided；历史 14/18 不是正确率 |
| 历史近黑画面 | 取帧失败传播缺陷已有防护；历史现象根因仍未确认 |

## 当时的提交与结项计划（已完成提交及 CI 核验）

1. 审阅上述文件及最终 diff，只纳入应交付的文件，保持源码修正与测试成对提交。
2. 用英文 conventional commit 记录修正，例如 `fix(analysis): handle PNG transparent colors`、`fix(capture): publish reports without replacing existing files`、`chore(test): scope default collection to product tests`，必要的文档与测试随对应提交纳入。
3. 推送后检查**最终具体提交**的 Actions 全套和精确闸门；本轮没有该远程验证，不提前宣称通过。
4. 该提交 CI 通过后，再记录最终提交/版本及支持边界，按练习项目范围结项；后续服务化、诊断或标定需求另开任务。

Windows 默认临时目录若因沙箱权限失败，可参照 `docs/stage-39-release-review-fixes.md` 使用新 basetemp；不需要修改系统权限或跳过产品测试。
