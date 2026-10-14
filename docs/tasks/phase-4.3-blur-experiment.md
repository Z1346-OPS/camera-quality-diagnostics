# Phase 4.3：最小受控模糊实验

- 日期：2026-10-13
- 状态：**已实施、已测试、正式矩阵已执行 20/20 条件**。未 commit / 未 push。
- 复用对象：Phase 4.2 的 `analyze_quality_and_qr(...)`（`src/quality_qr_analysis.py`，未修改）
- 新增：`tools/run_blur_experiment.py`、`tests/test_blur_experiment.py`；本文件
- 代码基线：HEAD = `afdca8f43b66dcb8eca2b6280aebefd6215e4f03`

回答的问题只有一句：**同一张 QR 基图施加不同强度的高斯模糊后，质量测量如何变化，
基线解码、内部降采样搜索及最终汇总分别出现什么结果？**

首版只做固定矩阵实验，不建设通用实验平台。

---

## 1. 固定协议（不可调参）

| 项 | 值 |
| --- | --- |
| 基图 | 既有 clean 灰度 PNG，来自两份合成清单：`dev-01`(264×264, 模块 8 px)、`dev-02`(198×198, 模块 6 px)、`test-01`(264×264, 模块 8 px)、`test-02`(198×198, 模块 6 px) |
| 独立答案 | 直接取清单的 `expected_file` / `expected_sha256` / `truth_source`；**不由解码输出生成或替代** |
| sigma | `0, 1, 3, 5, 8`（图像像素） |
| 规模 | 4 张基图 × 5 个 sigma = **20 个正式条件**；σ=0 直接引用原图，新增 **16 张退化 PNG** |
| 生成 | `cv2.GaussianBlur(gray, ksize=(0,0), sigmaX=sigmaY=sigma, borderType=BORDER_REFLECT_101)`；**每个版本从原图独立生成，禁止串联叠加**；尺寸不变、灰度 PNG、压缩参数固定为 6 |
| 分析 | 每条件调用一次 `analyze_quality_and_qr(path, roi=None, expected_file=清单答案, truth_source=清单来源, try_downscale=True)` |
| 执行 | **开发组与验证组分别执行、分别报告**；验证组已在历史回归中出现，**不称盲测或未见数据验证** |

正常情况下每条件恰 **1 条质量测量、2 条解码尝试**（共 20 条测量、40 条尝试）。
**尝试数不是独立样本数**，多 profile 不重复计为样本。每条序列只在本基图内部比较。

## 2. 实际命令

```powershell
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

# 新增测试
.\.venv\Scripts\python.exe -m pytest -q tests\test_blur_experiment.py

# 完整回归 + 评测闸门（不加 --refresh）
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py

# 正式矩阵（两组分别执行；每轮新建 <run-id> 目录，已存在即拒绝覆盖）
.\.venv\Scripts\python.exe -X utf8 tools\run_blur_experiment.py --group development
.\.venv\Scripts\python.exe -X utf8 tools\run_blur_experiment.py --group test
```

预试在临时目录执行 `--group development --output-root <临时目录> --run-id trial-development`，
用于验证流程；**预试记录不混入正式统计**。预试未发现协议需要修改，因此未调参。

## 3. 验证结果（2026-10-13 实测）

环境：项目 `.venv`，Python 3.12.10 / OpenCV 5.0.0 / NumPy 2.5.3 / Pillow 12.3.0 / zxing-cpp 3.1.1。

下表保留首次执行记录；两项修复后的复验见 §3.1。

| 检查 | 实际结果 |
| --- | --- |
| 新增测试 | **15 passed**（3.44 s） |
| 完整回归 | **341 passed**（Phase 4.2 的 326 + 本轮 15） |
| 评测闸门 | 两个 split 均「与入库期望完全一致」，退出码 0，**未刷新期望** |
| 正式矩阵 | development 10/10、test 10/10，合计 **20/20**，`status = completed` |
| 独立复核（20 条件） | 逐条件与独立 `analyze_quality` / `analyze_label` 调用一致；图片与答案摘要与实际文件一致；`problems: 0` |
| 生成反例 | 把生成改为串联模糊（先 σ/2 再 σ/2）后，独立复算对照用例失败；已恢复为原字节（SHA-256 `05f7d02a…` 复核一致） |
| 原资产保护 | 4 张基图、4 份答案、Phase 4.2 冻结证据（`protected-sha256.txt`、oracle、提取脚本）摘要全部未变；`git diff HEAD -- src tests tools .github requirements.txt` 为空 |

### 3.1 两项修复与复验（2026-10-13）

1. 分析返回后，将报告中实际使用的图片与答案 SHA-256 分别与条件计划核对。
   不一致即抛出 `BlurExperimentError`，沿用已有中断报告机制，错误条件不追加到结果。
   新增图片、答案两个回归用例：仅修改临时副本，并在分析后恢复原字节，验证事后文件恢复也不能掩盖不一致。
2. 修正 §4 及 README 的真值数量：共 **11** 个 `correct`；`test-02` 在 σ=3 为 `decode_error`。

| 复验 | 实际结果 |
| --- | --- |
| 新增回归用例 | 修复前 2 failed；修复后 2 passed |
| 实验测试 | **17 passed**（4.82 s） |
| 完整回归 | **343 passed**（25.10 s） |
| 评测闸门 | 退出码 0，两个 split 与入库期望完全一致，未刷新期望 |
| 命令行冒烟 | 临时目录中 development、test 各 10/10 completed；全部实际图片与答案摘要匹配计划；临时产物已清理 |

两轮正式实验的 22 个文件保留原字节，未重跑或覆盖；原报告记录的生成实现摘要仍对应首次运行版本。
本次只修改实验脚本、对应测试、本任务记录、README 与能力矩阵，未修改既有 QR 或质量分析逻辑。

## 4. 观察到的结果

清晰度（拉普拉斯方差）随 sigma 急剧单调下降；亮度基本不变；对比度（灰度标准差）单调下降；
块间均值极差小幅下降。解码结果随 sigma 退化，但 **σ=5 的失败形态因基图而异**。

| 基图 | 指标 | σ=0 | σ=1 | σ=3 | σ=5 | σ=8 |
| --- | --- | --- | --- | --- | --- | --- |
| dev-01 (264², m8) | 清晰度 | 7314.57 | 427.82 | 24.68 | 4.17 | 2.51 |
| dev-02 (198², m6) | 清晰度 | 10310.06 | 592.34 | 27.43 | 2.91 | 2.34 |
| test-01 (264², m8) | 清晰度 | 7553.41 | 438.14 | 24.39 | 4.09 | 2.43 |
| test-02 (198², m6) | 清晰度 | 10336.59 | 590.78 | 26.39 | 3.02 | 2.32 |
| dev-01 | 对比度 | 105.70 | 97.01 | 79.45 | 69.04 | 62.29 |
| dev-02 | 对比度 | 105.38 | 93.48 | 72.35 | 64.19 | 58.98 |
| test-01 | 对比度 | 104.08 | 95.10 | 77.25 | 66.76 | 59.94 |
| test-02 | 对比度 | 104.41 | 92.50 | 71.50 | 62.89 | 57.03 |
| dev-01 | 亮度 | 198.80 | 198.80 | 198.80 | 198.80 | 198.80 |
| dev-02 | 亮度 | 199.27 | 199.27 | 199.27 | 199.26 | 199.27 |
| test-01 | 亮度 | 201.14 | 201.14 | 201.15 | 201.14 | 201.14 |
| test-02 | 亮度 | 200.67 | 200.68 | 200.68 | 200.67 | 200.67 |
| dev-01 | 块间均值极差 | 127.38 | 127.37 | 126.11 | 124.40 | 123.05 |
| dev-02 | 块间均值极差 | 144.45 | 144.25 | 140.04 | 134.82 | 131.40 |
| test-01 | 块间均值极差 | 122.70 | 122.69 | 121.66 | 119.88 | 117.99 |
| test-02 | 块间均值极差 | 126.69 | 126.69 | 124.60 | 122.39 | 119.86 |

解码结果（**baseline 与 internal_downscale_search 在全部 20 个条件中完全一致**，
`decode_summaries` 汇总也与两者相同）：

| 基图 | σ=0 | σ=1 | σ=3 | σ=5 | σ=8 |
| --- | --- | --- | --- | --- | --- |
| dev-01 | decoded | decoded | decoded | **ambiguous** | **not_decoded** |
| dev-02 | decoded | decoded | decoded | **not_decoded** | **not_decoded** |
| test-01 | decoded | decoded | decoded | **decode_error** | **not_decoded** |
| test-02 | decoded | decoded | **decode_error** | **not_decoded** | **not_decoded** |

真值核对：共 **11** 个条件为 `correct`。σ=0/1/3 的 12 个条件中，11 个为 `correct`，
`test-02` 在 σ=3 时为 `decode_error`。全矩阵其余 9 个条件的真值状态与解码状态同值
（`ambiguous` 1、`decode_error` 2、`not_decoded` 6）。**没有 `incorrect`、`not_provided`、
`conflict` 或 `execution_error`**；20 条质量测量全部成功，**没有 `quality_error`**。

各状态数量（仅代表本实验 20 个条件与 4 张基图，**不能外推**）：

| 层 | decoded | ambiguous | decode_error | not_decoded |
| --- | --- | --- | --- | --- |
| baseline attempt | 11 | 1 | 2 | 6 |
| internal_downscale_search attempt | 11 | 1 | 2 | 6 |
| decode_summaries 汇总 | 11 | 1 | 2 | 6 |

### 4.1 不符合预想的结果（如实记录）

1. **内部降采样搜索对模糊没有产生任何恢复**：20 个条件里两条 profile 的状态逐一相同，
   与合成数据集 `noise-large` 族（基线失败、降采样救回）的行为不同。
   本实验**不能**说明降采样搜索对模糊普遍无效，只能说在本矩阵中没有出现恢复。
2. **相同模块宽度、相同尺寸的基图在 σ=5 上给出不同结果**（dev-01 `ambiguous` vs
   test-01 `decode_error`），载荷不同。因此「模块宽度 + 尺寸」不足以预测模糊后的失败形态。
3. 清晰度与对比度在本矩阵内随 sigma 单调下降，但**协议不要求单调**，也不据此设定任何阈值。

## 5. 限制（必须随结论一起读）

- 只做固定矩阵的**模糊**实验：不含其他退化类型、多因素组合、ROI 实验，也不生成新基图。
- 不输出准确率、通用阈值、故障原因或跨场景有效性结论；上表的数量只描述这 20 个条件。
- 每张基图只在本基图内部比较，不跨基图归因。
- 耗时沿用 Phase 4.2 的定义，本实验不新增性能统计体系。
- 全部结论限于本机、项目 `.venv` 与本次运行；未做跨机器或依赖升级验证。
- 验证组（`test` split）已在历史回归中出现，**不是盲测**。

## 6. 实验产物

```
data/experiments/phase-4.3-blur-v1/development-20261013T081607Z/
data/experiments/phase-4.3-blur-v1/test-20261013T081735Z/
```

每轮含：`experiment-plan.json`（协议、基图与答案摘要、每条件 sigma 与生成参数、退化图摘要、
生成实现与运行环境）、`degraded/*.png`（各 8 张，共 16 张）、`results.json`
（条件元数据 + **完整的 Phase 4.2 关联报告**，未重新解释或改写其内部字段）、`report.md`
（逐基图、逐 sigma；baseline 与 downsample 两条 attempt 分列，汇总列取自 `decode_summaries`）。

`data/experiments/` 未被 `.gitignore` 排除，这些产物当前为未跟踪文件，未提交。
