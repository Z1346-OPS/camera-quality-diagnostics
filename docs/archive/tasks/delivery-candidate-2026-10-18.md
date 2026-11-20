# 交付候选说明（2026-10-18）

> 位置：`docs/tasks/delivery-candidate-2026-10-18.md`
> 本文是一次**交付整理记录**，不是功能任务，也不宣布正式发布。
> 文档序号规则不适用于 `docs/tasks/`；本文件遵守该目录的最小任务格式。

## 1. 前提核验

- 已存在：`README.md` 已有能力说明与测试/CI 入口；`docs/stage-34-project-capability-matrix.md` 第 0 节已有历史测试与 CI 数字；`docs/tasks/capture-review-walkthrough.md` 已提供完全合成的采集复核演示；`docs/stage-37-read-failure-guard.md` 已记录本轮未提交修正的验证；`docs/tasks/real-use-acceptance-2026-10-16.md` 已记录 2026-10-16 实机验收。
- 已覆盖：`README.md`「测试与验证体系」把用例数量指向能力矩阵；`docs/tasks/capture-review-walkthrough.md:7` 起的三类合成演示不依赖本机实拍文件；`docs/stage-37-read-failure-guard.md:85` 起记录完整 pytest `493 passed`。
- 已忽略：`.gitignore:27` 忽略 `data/reports/`，`.gitignore:30` 忽略 `/photo/`。
- 结论：**确认缺失的是交付候选身份、支持范围与公开/本地证据的集中入口**；本轮不进入功能实现，不修改业务源码、测试、依赖、CI 或样例。

## 2. 目标

让审核者能从仓库内的文档回答三个问题：当前交付候选由哪些已提交与未提交改动组成；哪些能力有证据、哪些没有；哪里可以完全离线复现。

## 3. 不改变（回归边界）

- 不修改 `src/`、`tests/`、`requirements.txt`、`.github/workflows/`、`data/samples/`、`data/manifests/`、`tools/`。
- 不修改 `docs/stage-37-read-failure-guard.md`、`docs/tasks/real-use-acceptance-2026-10-16.md`、`docs/tasks/capture-review-walkthrough.md` 的历史内容。
- 不重写历史报告、不修改历史测试数字、不刷新评测期望。
- 不提交、不暂存、不推送、不打标签、不创建分支、不发布。

## 4. 验收条件

1. `git rev-parse HEAD` 仍为 `81b86e6d6b2b264890d2229e12856b7ef15b19ea`。
2. `git status --porcelain` 只出现本文第 5 节列出的文件，不出现 `data/reports/`、`photo/`、`.venv/`。
3. 本轮开始与结束时，`src/capture_task.py`、`tests/test_capture_task.py`、`requirements.txt`、`.github/workflows/tests.yml`、`data/manifests/evaluation-synthetic-expectations.json` 的 SHA-256 逐字节相同。
4. 本文与三份被更新文档中的相对链接都能解析到仓库内文件；指向 `data/reports/` 或 `photo/` 的路径必须明确标注为**仅本机**。
5. 新增材料不包含真实图片、QR 载荷、完整运行目录、凭据或私人材料。
6. 本文不声称「已发布」「已通过远程 CI」「Linux 实机已验证」或「摄像头问题已解决」。

## 5. 交付候选身份

### 5.1 已提交基线

| 项 | 值 |
| --- | --- |
| 分支 | `main` |
| HEAD | `81b86e6d6b2b264890d2229e12856b7ef15b19ea`（`docs(capture): add reproducible capture review walkthrough`，2026-10-15） |
| 提交数 | 79（截至 2026-10-18） |
| 已跟踪文件 | 209 |
| 该提交包含的最新修正 | **不包含** 2026-10-17 的取帧失败传播修正；该修正仍只在工作区 |

`81b86e6` 相对最后一次有 CI 记录的 `2629e57`，只改动了 `README.md`、`docs/tasks/capture-review-walkthrough.md` 与三份文档（`docs/stage-34-*`、`docs/tasks/phase-4.5-*`），**未改 `src/`、`tests/`、依赖或 CI**。

### 5.2 候选相对基线的改动

| 文件 | 状态 | 改动 | 验证/说明 |
| --- | --- | --- | --- |
| `src/capture_task.py` | 已修改、未提交 | +50 / −2：新增 `_GrabRetrieveCamera`，默认工厂改为显式检查 `grab()`/`retrieve()` | 见 `docs/stage-37-read-failure-guard.md` |
| `tests/test_capture_task.py` | 已修改、未提交 | +309：T13 段 12 个回归用例 | 同上 |
| `README.md` | 已修改、未提交 | 内容 +7 行（取帧失败传播说明），另有本轮整理增量；另含整文件 CRLF→LF 行尾变化 | 行尾变化是既有用户改动，本轮保留 |
| `docs/stage-37-read-failure-guard.md` | 未跟踪、新增 | 取帧失败传播的设计、测试与验证记录 | 待纳入版本 |
| `docs/tasks/real-use-acceptance-2026-10-16.md` | 未跟踪、新增 | 2026-10-16 实机与干净环境验收记录 | 待纳入版本；证据链接仅本机 |
| `README.md`、`AGENTS.md`、`docs/stage-34-project-capability-matrix.md` | 本轮修改 | README 顶部增加候选入口并标注两处本机证据；AGENTS.md 去掉过时的 285 项指引、更新文档序号上限；能力矩阵增加 2026-10-18 当前状态说明并标明历史数字日期 | 纯文档 |
| `docs/tasks/delivery-candidate-2026-10-18.md` | 本轮新增 | 本文 | 纯文档 |

### 5.3 尚未提交的改动

上述 `src/capture_task.py`、`tests/test_capture_task.py`、`README.md`、两份既有未跟踪文档、本轮三份文档更新与本文，**全部尚未提交**。因此不能把当前 HEAD 单独称为「包含最新修正的版本」。

### 5.4 对应这些源码的验证记录

| 记录 | 对应代码 | 结论 |
| --- | --- | --- |
| `data/reports/read-failure-guard-20261017-101037-9d36a959/` | 当前工作区（含未提交修正） | 本机记录：完整 pytest `493 passed in 23.07s`；评测闸门 exit 0；3 轮 × 30 秒实机正常路径通过 |
| `docs/tasks/real-use-acceptance-2026-10-16.md` | `81b86e6` + 当时仅有 README 行尾改动 | 本机记录：`477 passed、4 skipped`；18 张正式采集图片核对一致；**不含** 2026-10-17 修正 |
| Ubuntu CI 运行 `38686814154` | 提交 `2629e57` | 远程记录：`481 passed`、无跳过；**不覆盖**未提交修正 |

上表三行是**三种不同来源**，不能互相替代：493 是修正后的本地历史记录，481 是旧提交的远程 CI 记录，本轮未新增任何测试或 CI 结果。

### 5.5 正式发布前仍需的步骤

1. 由审核者确认本文第 11 节文件清单与既有两个未跟踪文档是否纳入版本。
2. 决定 `README.md` 的整文件 CRLF→LF 是否作为有意的行尾规范化一并提交；若不愿引入大 diff，应在提交前单独处理。
3. 将候选文件提交到 `main`（英文 conventional commit），推送后等待该**具体提交**的 GitHub Actions 结果。
4. 只有该提交的 CI 通过后，才能讨论打标签或发布；本轮不执行其中任何一步。

## 6. 支持范围

| 范围 | 当前可声称的内容 | 不可声称的内容 |
| --- | --- | --- |
| Windows 本机指定设备 | 采集、留图、CSV/JSON 关联与离线复核已有实际运行记录（`trial-003`/`trial-004`、2026-10-16 的 18 张、2026-10-17 的 18 张） | 不适用于其他电脑、其他相机型号或长期稳定性 |
| 图片分析与 QR 分析输出 | 输出亮度、对比度、清晰度等测量值与解码/识读状态 | 不等于工业合格判定、故障诊断或根因分析 |
| QR 内容正确性 | 未提供独立答案时为 `not_provided`；已提供答案且单一读出时，逐字节一致为 `correct`，不一致为 `incorrect`；未读出、歧义或解码错误等情况保留对应状态 | 实拍 14/18 单一读出**不是正确率**，也不能证明内容正确 |
| 历史近黑画面 | 已修正「取帧失败但数组非空被误计为成功」的传播缺陷 | 根因未确认，不能描述为彻底解决历史问题 |
| 默认定时采集后端 | Windows DirectShow（`CAP_DSHOW`） | 不承诺其他后端或其他平台行为相同 |
| Linux | 历史 Ubuntu CI 自动化测试证据（481 passed，旧提交） | CI 通过不等于 Linux 真实摄像头采集可用 |
| 当前交付候选的 Linux 实际采集 | 本轮未验证 | 不承诺全平台支持 |

## 7. 公开复现材料与本地证据

| 材料 | 是否随普通克隆提供 | 说明 |
| --- | --- | --- |
| `docs/tasks/capture-review-walkthrough.md` | 是（已跟踪） | 完全合成的采集复核演示，是公开复现主入口 |
| `data/samples/stage2-known-qr.png` 与 `.expected.txt` | 是（已跟踪） | 内容预先确定的合成 QR 样例 |
| `data/samples/synthetic-qr-v1/` 与 `data/manifests/` | 是（已跟踪） | 合成退化数据集与精确期望值 |
| `tools/check_evaluation_expectations.py` | 是（已跟踪） | 离线评测闸门 |
| `data/reports/qr-A7-downscale-001.json` | **否**（被忽略） | 本机报告；`photo/A7.jpg` 同样仅本机 |
| `data/reports/timed-capture/trial-003`、`trial-004` | **否**（被忽略） | 本机实机产物 |
| `data/reports/acceptance-20261016-135457-6277a5b2/` | **否**（被忽略） | `real-use-acceptance-2026-10-16.md` 的全部证据链接与图片均指向此处，普通克隆中不可访问 |
| `data/reports/read-failure-guard-20261017-101037-9d36a959/` | **否**（被忽略） | `stage-37-read-failure-guard.md` 第 7 节的相关记录仅本机 |
| `data/reports/black-frame-check-*`、`black-frame-live-diagnosis-*` | **否**（被忽略） | 历史诊断材料，仅本机 |

结论：

- 历史文档内容保持原样；缺失链接已在此表集中说明，不通过提交真实图片或整个 `data/reports/` 来「修复」。
- 「本机存在」不等于「仓库包含」。
- 合成演示**不是**真实摄像头验证，不能替代实机证据。

## 8. 可复现入口

### 8.1 环境

记录环境为 Python 3.12.10、项目内 `.venv`，依赖见 `requirements.txt`（含 `opencv-python==5.0.0.93`、`numpy==2.5.3`、`pytest==9.1.1`、`zxing-cpp==3.1.1`）。

Windows PowerShell（在**自己的**项目根目录执行）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS 形态为 `.venv/bin/python`，但当前候选的 Linux 实机采集未验证。以上是文档说明；本轮未创建环境、未安装依赖。

### 8.2 三类离线演示

| 演示 | 位置 | 输出位置 | 是否访问摄像头 |
| --- | --- | --- | --- |
| 正常 / 缺图 / 指标差异 | `docs/tasks/capture-review-walkthrough.md` 第 1 节 | 脚本打印的 `tempfile.mkdtemp(prefix="capture-review-demo-")` 目录；每次运行都是新目录 | 否 |
| 合成 QR 已知答案 | `README.md`「阶段 2：本地 QR 基线与人工 ROI」第一条命令 | `--output` 指定的**新 JSON** | 否 |
| 合成数据集评测闸门 | `README.md`「合成回归数据集与 CI 期望闸门」中的 `tools/check_evaluation_expectations.py` | 不写报告文件，与入库期望比对 | 否 |
| 真实采集后复核 | `docs/tasks/capture-review-walkthrough.md` 第 3 节 / `src/review_capture.py` | 采集写新任务目录；复核只打印 stdout | 采集访问；复核不访问 |

### 8.3 预期退出状态

- `src/review_capture.py`：`0` 一致；`1` 检查后不一致；`2` 非 completed 或输入错误。`1`/`2` 可以是**预期业务结果**，不一定是程序崩溃。
- `src/analyze_label.py` / `src/evaluate_labels.py`：正常完成为 `0`；`completed_with_errors`（如候选解码失败）为 `2`；参数/输入错误为 `2`。未读出、歧义、答案不匹配本身不会使状态变为 `completed_with_errors`，仅有这些业务结果时仍为 `completed`、退出码 `0`；解码／执行错误，或批量评测中的样本处理失败等情况，才会使汇总状态变为 `completed_with_errors`。
- `src/run_capture.py`：完成 `0`；已定义的参数/采集失败 `2`；`KeyboardInterrupt` `130`。
- `tools/check_evaluation_expectations.py`：一致 `0`；与期望不一致 `1`。

### 8.4 输出只新建与重复运行

- `--output` 指向已存在文件会被拒绝；重复分析必须换新文件名。
- 采集任务目录必须是不存在的新目录。
- 合成演示每次创建新的系统临时目录；演示脚本把复核 stdout 另存为 `*.review.json`。
- 模糊实验每轮新建 `data/experiments/phase-4.3-blur-v1/<run-id>`。

### 8.5 固定 D 盘路径

`docs/tasks/capture-review-walkthrough.md` 中的 `Set-Location 'D:\Projects\Python\camera-quality-diagnostics'` 与 `README.md` 早期示例中的 D 盘路径都是**开发者本机路径**。其他使用者应进入自己的项目根目录；演示不要求拥有作者本机的 `photo/` 实拍文件或历史 `data/reports/` 目录。

### 8.6 助手可接收的材料

项目**没有实现**面向助手的导入接口或配置文件。按现有入口已核实的可产出材料类型是：

- `src/analyze_image.py` 的图片分析 JSON；
- `src/analyze_label.py` 的 QR 解码 JSON（含 `attempts` 与 `truth_check`）；
- `src/evaluate_labels.py` 的批量评测 JSON；
- 定时采集任务目录中的 `capture_task.json`、两份 CSV 与留证 PNG；
- `src/review_capture.py` 打印到 stdout 的复核 JSON。

这些真实运行产物均不入库；仓库只提供合成样例与合成演示。本轮不修改助手，也不承诺尚未实现的导入方式。

## 9. 本轮验证

本轮只做文档与静态核对，未运行 pytest、未执行离线演示、未运行摄像头。

| 检查 | 方法 | 结果 |
| --- | --- | --- |
| Git 状态与 HEAD | `git status --porcelain`、`git rev-parse HEAD` | 修改前后均见第 5 节；HEAD 未变 |
| 与 2026-10-17 资产快照的对应 | 对 209 个已跟踪文件 + 2 个既有未跟踪文档逐个计算 SHA-256，与 `assets-after.json` 比对 | 211/211 匹配，0 缺失、0 不一致（本轮修改前） |
| 关键文件未变 | 修改前后 SHA-256 | `src/capture_task.py`、`tests/test_capture_task.py`、`requirements.txt`、CI、评测期望均未变 |
| 公开入口存在性 | 检查脚本、合成样例、清单是否已跟踪 | 均存在且已跟踪 |
| 链接 | 解析本轮涉及文档的相对链接 | 仓库内链接均可解析；`data/reports/` 链接已在第 7 节标为本机 |
| 换行符 | 字节级统计并核对 `git ls-files --eol` | 仅修改目标文档；未把行尾变化扩散到其他文件 |
| 敏感材料 | 检查新增文本与 Git 状态 | 未新增真实图片、QR 载荷、完整运行目录或凭据 |

## 10. 未完成与风险

- **未重跑测试**：493 是 2026-10-17 的本地历史记录；本轮没有新的 pytest 结果。
- **未做干净环境复现**：本轮未创建 `.venv`、未安装依赖、未执行合成演示；演示入口为**静态核对，未重新执行**。
- **未过远程 CI**：未提交修正没有对应的远程运行；481 只对应旧提交 `2629e57`。
- **Linux 实机未验证**：历史 Ubuntu CI 只证明自动化测试在 Linux 通过。
- **本地证据链接在普通克隆中不可访问**：已集中说明，未通过提交图片解决。
- **历史近黑画面根因未确认**：取帧失败传播修正不等于根因修复。
- **README 整文件行尾差异**：是否作为正常化提交需用户决定。

以上均不阻止形成交付候选，但其中「未提交、未过 CI」阻止正式发布。

## 11. 待纳入版本的文件清单

修改：

- `src/capture_task.py`
- `tests/test_capture_task.py`
- `README.md`
- `AGENTS.md`
- `docs/stage-34-project-capability-matrix.md`

新增：

- `docs/stage-37-read-failure-guard.md`
- `docs/tasks/real-use-acceptance-2026-10-16.md`
- `docs/tasks/delivery-candidate-2026-10-18.md`

不纳入：

- `data/reports/`、`photo/`、`.venv/`、任何真实图片或载荷。

本清单只供审核，未执行 `git add`。

## 12. 结论

**交付候选整理完成，等待 Codex 审核。** 尚未提交、未推送、未发布，也未在 Linux 实机或干净环境中重新验证。
