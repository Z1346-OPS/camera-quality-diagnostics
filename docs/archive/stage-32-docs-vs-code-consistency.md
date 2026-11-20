# 文档 32：文档与实现一致性核对（2026-10-12）

> 本文档的编号 `32` 是**文档序号**，不代表业务阶段（见 `AGENTS.md` 的文档编号规范）。
> 这是该规范生效后新增的第一份文档。
>
> **后续状态（2026-10-12 晚些时候）**：合成回归数据集与 CI 期望闸门见
> [文档 33](stage-33-synthetic-regression-dataset.md)。本文中「只有 1 个 `development` 样本、
> 没有 `test` 样本」「测试 283 项」等描述是**该次审计当时**的事实，已不是当前状态。

- 被核对基线：commit `c8029a8`（核对开始时工作区干净）
- 核对方式：**只读**。读声明性文档 → 读 `src/` 与 `tests/` → 对可实测项实跑 → 三方交叉验证
- 本文档只做核对：**不提出新架构，不修改任何代码**

## 0. 审计范围与方法

### 审计对象

| 类别 | 范围 |
| --- | --- |
| 声明性文档 | `README.md`、`AGENTS.md`、`docs/project-direction-update-2026-10-10.md`、`docs/project-direction-and-migration-plan.md`、`docs/label-reading-project-design.md` |
| 代码 | `src/` 24 个模块 |
| 测试 | `tests/` 20 个文件、283 项 |
| 产物 | `data/reports/` 41 个报告、`photo/evaluation-development-001.json`、`docs/tasks/README.md` |

### 方法与可信度

每条结论至少来自两个独立来源：

1. **源码**：函数/常量/字段名是否真实存在（给出 `文件:行`）；
2. **测试**：是否有对应用例覆盖（用例名与数量）；
3. **产物**：真实报告里的字段值、哈希、耗时是否与文档一致——产物是程序写出的，不能由文档反推。

正文中标 ★ 的条目由第二方独立复验（`grep` 源码或实跑命令），其余为审计轮核对结果。

## 1. 文档可信度与证据状态分层

### 四状态定义（本文档统一使用）

| 状态 | 含义 | 判定依据 |
| --- | --- | --- |
| ✅ 已实现 | 代码存在，且有测试或产物证据 | 源码 + 测试/产物 |
| ⚠️ 已实现但文档缺失 | 代码存在，但声明性文档完全没写 | 源码存在 + `README`/`AGENTS.md` 中 0 次提及 |
| ⏳ 规划中未实现 | 文档明确说未实现，代码也确实没有 | 文档声明与代码缺失一致 |
| ❓ 无法确认 | 缺少可核对的证据 | 无产物、无历史快照，或需人工确认 |

补充一个只用于文档自身的类别：**Document-only**——只有文档声明、无法用代码或产物验证的说法（如计划、边界声明）。这类不算过期，也不能当能力引用。

### 分层结果

| 文档 | 证据状态 | 使用建议 |
| --- | --- | --- |
| `docs/stage-2-roi-qr-baseline.md` | Confirmed ★ | 可直接引用（`analysis_id`/尺寸/耗时逐项实测吻合） |
| `docs/stage-1-local-input-verification.md` | Confirmed | 可直接引用 |
| `docs/tasks/README.md` | Confirmed ★ | 引用的行号与基线 commit 实测存在 |
| `docs/project-direction-update-2026-10-10.md` | Confirmed ★ | 「当前实际状态与证据边界」章节可直接引用 |
| `README.md`（能力清单部分） | 部分过期 ❌ | 涉及条码识别、像素上限、测试数量的表述**不可引用** |
| `AGENTS.md`（项目定位的「已实现」清单） | 部分过期 ❌ | 清单漏记了 2026-10-09 之后的能力 |
| `docs/label-reading-project-design.md` | 过期 ❌ | 阶段 2 基线表已被实现甩过一整个阶段 |
| `docs/project-direction-and-migration-plan.md` | 过期 ❌（历史文件） | 只能当 2026-10-01 的历史记录 |

一句话：**代码研究报告类文档可以直接信；概览与设计类文档只能当历史背景。**

## 2. 过期清单（12 条）

本章列的是**文档同步滞后项**（代码先发展、文档没跟上），不是「错误文档清单」。每行都给出实测依据与应改成的内容。

| # | 位置 | 现在写的 | 实测 | 应改为 |
| --- | --- | --- | --- | --- |
| 1 | `README.md:5` | 「手机服务、数据库和条码识别尚未实现」 | `src/label_analysis.py:52` `import zxingcpp`、`:59` `zxingcpp.read_barcodes(..., QRCode)`；`requirements.txt:20` `zxing-cpp==3.1.1` ★ | 「手机服务与数据库尚未实现；QR 解码与独立答案核对已实现」 |
| 2 | `README.md:20` | 「真实纸质 QR 的已知答案验收仍待用户操作」 | `data/reports/qr-A7-downscale-001.json`：源图 `photo/A7.jpg` 实拍，预设答案 `STAGE2-SMOKE-001`，`truth_check.status=correct`（`exact_payload_bytes`）★ | 「已完成 1 次自造样本打印件的实拍 + 预设答案逐字节核对（开发材料）；独立测试集尚未建立」 |
| 3 | `README.md:33` | 状态只列 5 种 | 实测 `summaries` 输出 9 种 outcomes；分析层另有 `conflict`，评测层另有 `decoded_unverified`/`input_error` ★ | 补齐，并区分「分析层状态」与「评测层状态」 |
| 4 | `AGENTS.md`（项目定位·已实现清单） | 列出 7 项能力 | 代码另有 `--try-downscale`、`label_evaluation.py`、`evaluate_labels.py` ★ | 补入降采样搜索与批量评测 |
| 5 | `AGENTS.md`（目录约定） | 「`tests/` 与 `src/` 模块同名对应」 | 反例：`test_color_summary.py` ↔ `src/summarize_colors.py`；`test_label_analysis.py` 兼测 `analyze_label.py`；`test_environment.py` ↔ `main.py`；无 `test_analyze_label.py` ★ | 「大体按模块对应，个别文件集中覆盖多个入口」并举反例 |
| 6 | `label-reading-project-design.md:24` | 「人工 ROI、基线 QR 读码、已知答案核对 — 尚未实现」 | 模块、测试与 `zxing-cpp` 依赖均在 | 标注为 2026-10-02 起已实现 |
| 7 | `label-reading-project-design.md:25` | 「固定增强分支、冲突规则、重拍对照、独立评测 — 尚未实现」 | `conflict` 已实现；独立评测已实现；Gamma/CLAHE 与重拍对照确实缺 | 拆为「已实现：冲突规则、独立评测」+「未实现：Gamma/CLAHE、重拍对照」 |
| 8 | `label-reading-project-design.md:28` | 「25 MiB、1200 万像素」 | `src/analyze_image.py:34-35`：`MAX_FILE_BYTES = 25*1024*1024`、`MAX_PIXELS = 16_000_000` ★ | 「1600 万像素」 |
| 9 | `label-reading-project-design.md:15` | 「仓库内未发现项目级 `AGENTS.md`」；「162 passed in 6.73s」 | 项目根 `AGENTS.md` 存在；测试数现为 283（同一文件 `:3` 又写 228，两个数互相矛盾） ★ | 标注为历史记录；或改为「2026-10-12 起已有项目级 `AGENTS.md`；测试 283 项」 |
| 10 | `label-reading-project-design.md:3` | 「最新完整回归 228 项通过」 | 本轮实跑 `283 passed` ★ | 标注为当时数值 |
| 11 | `label-reading-project-design.md:71` | 「`.gitignore` 只覆盖旧报告类型」 | `.gitignore` 已整目录忽略 `data/reports/`，并忽略 `/photo/` | 「已整目录忽略 `data/reports/`」 |
| 12 | `label-reading-project-design.md:82`、`stage-2-roi-qr-baseline.md:111` | 「阶段 3 才建设独立评测」 | 清单、分组检查、独立评测均已实现 ★ | 标注阶段 3 的评测部分已完成 |

## 3. 遗漏清单（6 条）

代码已有、但声明性文档完全没写的能力。影响等级用于后续排优先级。

| # | 代码已有 | 文档状态 | 影响 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | `analyze_label.py --try-downscale`、双 profile attempts、`decode_summaries` | `README.md` 与 `AGENTS.md` 中 `downscale` **0 次** ★ | **High** | 这是 A7 排障闭环的核心机制，也是最能体现「失败定位」的能力 |
| 2 | `evaluate_labels.py`、`label_evaluation.py` 评测入口 | 两文档中 `evaluate_labels`/`label_evaluation` **0 次** ★ | **High** | 简历主打能力，且本轮已完成端到端实测（见 §5.1） |
| 3 | 清单 schema 契约（8 必填 + 4 可选）、分组泄漏检查、正确率分母口径 | 无任何文档 | Medium | 决定评测结果是否可复核 |
| 4 | 状态与溯源标识：`conflict`、`decoded_unverified`、`input_error`、`local-label-analysis-2`、`local-label-evaluation-1` | 两文档中 `conflict` **0 次** ★ | Low | 影响结论解释，不影响结论成立 |
| 5 | 唯一评测清单 `photo/evaluation-development-001.json` 的位置与用途 | 无记录，且 `/photo/` 被 `.gitignore` 忽略 → **清单不入库** | **High** | 别人克隆仓库后无法复现评测，属可复现性缺口 |
| 6 | 2026-10-09 那轮开发（降采样 + 评测）本身 | `docs/` 无对应记录 | **High**（流程） | 违反 `AGENTS.md` 修改流程第 4 条「行为变更同步更新 `docs/` 与 `README.md`」——规则没有进入工作流 |

## 4. 无法确认（5 条）

| # | 待确认项 | 为什么无法确认 |
| --- | --- | --- |
| 1 | a11 的降采样读出 | 仓库内无 a11 报告或文档；`data/reports/` 的 11 份 `qr-*.json` 源图均为 A2–A7 |
| 2 | A7「预先固定答案」的独立性 | 清单里的 `truth_source` 是用户声明的文本，程序只标记 `user_asserted_independent`；机器无法证明答案在解码前已固定。本轮实跑的 `evaluation_policy.independence` 也自述 `capture_history_and_truth_require_human_verification` |
| 3 | 旧报告格式差异的成因 | 10 份旧 `qr-*.json` 无 `decode_summaries`/`profile` 字段，只有 A7 的两份是新结构；无法确认生成版本与时点 |
| 4 | `stage-2-roi-qr-baseline.md` 记录的「`data/reports` 原有 31/35 个文件哈希不变」 | 现为 41 个文件（无子目录，实测），无历史快照可比 |
| 5 | 硬件/摄像头类声明（采集链路、设备型号） | 本轮未打开设备 |

> 原审计轮的第 6 条待确认项「`evaluate_labels.py` 用现有清单能否跑通」已由本轮实测证实，移出本清单（见 §5.1）。

## 5. 本轮新增实测

### 5.1 评测入口端到端闭环（把一条 ❓ 变成事实）

```powershell
# 结果写到仓库外，保证不污染项目
.\.venv\Scripts\python.exe -X utf8 .\src\evaluate_labels.py `
  .\photo\evaluation-development-001.json --split development --output <仓库外路径>
```

| 项 | 实测值 |
| --- | --- |
| 退出码 / 状态 | `exit=0`、`status=completed` |
| 结果大小 / 耗时 | 20.1 KB / `duration_seconds = 0.617` |
| 基线 `decode_error` | `correct 0/1`，中位 0.0424 s |
| 降采样搜索 | `correct 1/1`，中位 0.0817 s |
| 配对变化 | `improved = 1`、`degraded = 0` |
| 候选选择口径 | `selection_uses_truth = false`（**候选选择不使用真值**） |
| 正确率分母口径 | `all_manifest_samples_with_truth_including_failures` |
| 溯源 | `implementation_version = local-label-evaluation-1`、`git commit = c8029a8`、`working_tree_dirty = false` |
| 仓库污染 | 运行前后 `git status --porcelain` 完全一致 ✅ |

结论：**「清单 → 执行 → 生成结果 → 结果可复核」闭环成立**。这条把简历口径从「写了评测脚本」提升为「评测流程可复现、口径可审计」。

### 5.2 六处状态误标的修正

审计初稿有 6 行把「**文档说未实现，代码确实也没有**」标成了 ✅ 已实现（离线 HTML 导出、结构化设备字段、独立实拍测试集、手机服务/数据库、采集与读码联动、批量图片分析）。这 6 行会读成「这些能力已经存在」，与事实相反。已逐条复核并统一改为 ⏳：

| 复核对象 | 证据 |
| --- | --- |
| 离线 HTML 导出 | `src/` 下 `html` 出现 **0** 次 |
| 结构化设备/拍摄条件 | 清单 schema `required = {id, image, sha256, label_id, batch_id, split, source_kind, source}`、`optional = {expected_file, expected_sha256, truth_source, roi}`；`device` 出现 **0** 次 |
| 独立实拍测试集 | 唯一清单只有 1 个样本（`A7-development`，`split=development`，`source_kind=phone_photo`） |
| 手机服务/数据库 | `src/` 下 0 处服务/数据库依赖 |
| 采集与读码联动 | `camera_test.py` 只导入 `analysis_config`/`metrics`/`report`/`frame_evidence`/`session_metadata` |
| 批量图片分析 | `src/` 无 `batch`/`bulk` 模块；`analyze_image.py` 只接受单个位置参数 `image` |

## 6. 结论

1. **代码能力高于文档描述。** 缺的不是功能，而是把已有能力写清楚。最该补的是 §3 的 High 项。
2. **规则已经存在，但没进入工作流。** §3 第 6 条是流程问题而非能力问题：2026-10-09 那轮开发没有任何 stage 记录。
3. **存在一个可复现性缺口。** 评测清单位于被 `.gitignore` 忽略的 `photo/`，克隆仓库后无法复现评测。是否需要把清单移入 `data/` 属独立议题，不在本轮改动范围。
4. **本轮不提出任何架构或升级方案。** 是否把项目从「标签读码排障工具」升级为更大的形态，应由方向文档决定，不由此核对文档决定。

### 证据边界（本文件不能用来声称的事）

- 不能据此文档声称任何**识读率**结论：目前只有 1 份 `development` 清单、1 个样本、没有 `test` 样本。
- 不能据此文档声称硬件/工业相机能力：本轮未打开任何设备。
- 标 ❓ 的 5 条在本文件范围内仍属未知，不要在后续文档里被引用为事实。

## 附录：关于逐项明细表

本轮**没有**附录原始 40 项逐行核对表。原因：原始表存在「统计汇总与逐项标注不一致」——汇总称 31 项已实现，而表内实际有 13 行标为过期、另有 6 行状态误标。直接固化会把矛盾写进项目文档，因此正文只保留可复核的结论（12 条同步滞后项 + 6 条遗漏 + 5 条无法确认），并在 §0 说明了每条结论的证据来源与复验方式。

后续如需要逐项明细，将基于源码、测试与产物**逐行重新复核**后单独生成，每行都带 `文件:行` 证据。

---

**本报告仅用于确认当前代码与文档的一致性；不代表未验证的能力已不存在，也不代表规划中的能力已经实现。**
