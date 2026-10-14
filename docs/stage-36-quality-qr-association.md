# 文档 36：QR 结果与图像质量测量的关联层

> 编号 `36` 是**文档序号**，不代表业务阶段（见 `AGENTS.md` 的文档编号规范）。
> 业务阶段 4.2（文档 36）：把 Phase 4.1 的质量测量与既有 QR 报告按**同一图、同一区域**关联起来。

- 日期：2026-10-13
- 关联任务规格：`docs/tasks/phase-4.2-quality-qr-association.md`（第 4 轮修订，用户审核通过后实施）
- 代码基线：HEAD = `afdca8f43b66dcb8eca2b6280aebefd6215e4f03`（实施期间未 commit/push）
- 新增模块：`src/quality_qr_analysis.py`；验收测试：`tests/test_quality_qr_analysis.py`（首次 24 项；两项修复后 27 项，对应 B01–B18 及修复回归）

## 1. 这个模块做什么

新增数组级之外的**外围组合函数**：

```python
from src.quality_qr_analysis import analyze_quality_and_qr

result = analyze_quality_and_qr(path, roi=None, expected_file=None,
                                truth_source=None, try_downscale=False)
```

对**同一张图、同一个区域**同时取得 QR 结果与 Phase 4.1 的质量测量，输出一条可追溯的结构化关联记录。
它**不重写**解码、**不重写**测量、**不改**既有报告字段：把既有 `analyze_label` 的完整输出作为子对象
`qr_report` **原样保留**，把 `analyze_quality` 的测量放在旁边，用读取一致性、区域对应与 profile 归并
把两者关联起来。

## 2. 输出结构

顶层字段（`schema_version` 首版为 `1`，`report_type` 为 `"quality_qr_association"`）：

| 字段 | 含义 |
| --- | --- |
| `association_id` / `analyzed_at` | 本次调用的随机 uuid4 与 UTC 时间戳 |
| `status` | `completed` 或 `completed_with_errors`（见第 5 节） |
| `timings` | 恰含 `decode_seconds` / `quality_seconds` / `total_seconds`，三者分别定义；总耗时在来源信息收集与报告组装完成后、返回前填写 |
| `provenance` | 关联模块版本、七个源文件的 SHA-256、质量模块版本（`null`）、运行库版本 |
| `read_consistency` | 两次读取的 SHA-256、`consistent`、`checked_fields`（固定 8 项） |
| `requested_roi` | 原样回显请求的 ROI（`null` 表示整图） |
| `measurements` | 每个 region **恰一条**质量测量记录 |
| `associations` | 每个 (region, profile) **恰一条**，通过 `measurement_id` 引用测量 |
| `qr_report` | **既有 `analyze_label` 的完整输出，逐字段原样保留** |
| `warnings` | 关联层自身的限制说明，**首版恒为 `[]`** |

`measurements[].basis` 恒为 `"original_normalized_image_region"`：质量测量始终在**标准化后的原图区域**
上完成，**不是**解码器内部降采样后的图。`try_downscale` 只影响解码 profile，不影响 `basis` / `region` /
`quality` 的取值。整图与 ROI 分别测量，同一区域的多个 profile **共用同一条**测量记录
（`len({a["measurement_id"] for a in associations}) == len(measurements)`）。

报告里共有**三处** warnings，来源与归属分明：

| 位置 | 来源 | 关联层的处理 |
| --- | --- | --- |
| `qr_report.warnings` | 既有 `analyze_label`（如 `decode_attempt_errors`） | 原样保留，不合并、不重排、不改写 |
| `measurements[].quality.warnings` | Phase 4.1 `analyze_quality`（`measurement_scope` 等） | 原样透传，不合并、不重排、不改写 |
| `warnings`（顶层） | 关联层自身 | 首版恒为 `[]` |

## 3. 读取一致性（为什么必须检测）

外围组合**会读两次图**：一次供质量测量，一次由 `analyze_label` 内部读取。这是组合方式的必然结果，
因此必须主动检测。关联层逐字段比对两侧的 `sha256`、`format`、`mode`、`width`、`height`、
`exif_orientation`、`analysis_width`、`analysis_height`；任一不一致即抛
`QualityQrAssociationError(code="source_changed_between_reads")`，**不输出报告**、不静默关联、
不"取其一为准"。

## 4. 状态与错误

- 关联层**不新增**状态词。`associations[].decode_status` 直接引用既有值
  （`decoded` / `not_decoded` / `decode_error` / `ambiguous` / `execution_error`）。
  `conflict` **仅在汇总层**出现，由保留的 `qr_report.decode_summaries[].decode.status` 表达。
- 无独立答案时 `truth_status` 必须为 `not_provided`；报告任何位置**不得**把读出称为 `correct`。
- 异常分类**逐类处理，不笼统捕获**：

| 阶段 | 异常 | 处理 |
| --- | --- | --- |
| 图片读取 / 标准化 | `images.AnalysisError` | 继续抛出，不返回报告 |
| ROI / 解码配置 / 真值参数 | `LabelAnalysisError` | 继续抛出，不返回报告 |
| 读取一致性 | 关联层自定义 | 继续抛出，不返回报告 |
| 质量测量 | `QualityAnalysisError` | 转为该测量的 `quality_error`，`quality` 置 `null`，保留 QR |
| 质量测量 | `MemoryError` / `cv2.error` | 继续抛出，**不得**解释为图像质量问题 |
| 其他 | 未预期异常 | 继续抛出 |

顶层 `status` 为 `completed_with_errors` 当且仅当任一测量有 `quality_error`，
或 `qr_report.status == "completed_with_errors"`。

## 5. 验证记录（2026-10-13 实测）

**环境**：项目 `.venv`，Python 3.12.10 / OpenCV 5.0.0 / NumPy 2.5.3 / Pillow 12.3.0 / zxing-cpp 3.1.1。

以下表格为首次执行者自测记录；独立复核发现的两项问题及修复后结果见 §5.1。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 规格契约 | 规格 4.3.0 快照比较 | `SPEC CONTRACT OK`：仅状态行与 §7/§8 正文可不同 |
| 保护对象 | 规格 4.3.1 | 清单 SHA-256 一致；170 项 = 168 字节不变 + 2 可改文档；168 项零变化；补充钉住 9 项零变化 |
| 新增文件范围 | 规格 4.3.2 | HEAD 未变；无越界已跟踪改动；新增文件全部在批准清单内 |
| 证据 oracle | 规格 4.3.3（内存比较，**未覆盖冻结版本**） | `ORACLE OK: identical except generated_at_utc` |
| 关联层验收 | `pytest -q tests/test_quality_qr_analysis.py` | **24 passed**；16 个 B 选择器逐条通过 |
| 完整回归 | `pytest -q` | **323 passed**（Phase 4.1 的 299 + 本次 24） |
| 评测闸门 | `tools\check_evaluation_expectations.py` | 退出码 0；两个 split 均「与入库期望完全一致」，**未刷新期望** |

B01–B18 的对应关系：B01/B02/B03/B04/B05/B06/B07/B08/B11/B12/B13/B14/B15/B16/B17/B18 分别对应
`tests/test_quality_qr_analysis.py` 中同名（或同前缀）的用例；B09/B10 为规格 4.3 的非 pytest 检查，
结果见上表前四行与最后两行。

**反例检查**：把读取一致性比较改为恒不触发（`if False and ...`）后，B01 的 8 个注入用例与 B18 的
一致性用例共 **9 项失败**，随后已恢复为原字节（SHA-256 `6e64006e…` 复核一致）。这说明该验收确实在
测量读取一致性，而不是空跑。

### 5.1 两项修复与独立复验（2026-10-13）

用户在独立复核指出问题后授权「修复并且复验」。本轮仅修复环境身份比较与总耗时漏计，
不增加功能、依赖或证据层级；原 oracle、清单、提取脚本、审核快照保持原字节。
任务规格 §7.4 明确记录 B07 的授权补充口径，原快照作为历史审核版本保留。

- **B07 的两种核验**：规格 §4.3.3 的本机冻结环境比较仍逐路径严格执行。
  通用 pytest 则只将 `source.path`、`provenance.runtime` 四项版本和
  `attempts[].decode.decoder.version` 的期望取自当前绝对路径及独立读取的运行库版本。
  不从被测报告取期望，不删除这些字段，不改原五条 volatile 路径；其余字段包括源码摘要、
  图片摘要、状态、载荷、位置、真值、配置及警告均精确对照冻结值。
- **总耗时**：报告组装完成后才记录 `total_seconds`，包括来源摘要与版本读取。
  新测试以确定性时钟分别为两项来源收集增加 2 秒与 3 秒；修复前报告 0 秒而失败，修复后为 5 秒。
  该回归测试不依赖真实 sleep 或性能阈值。

| 检查 | 实际结果 |
| --- | --- |
| 修复前的针对性回归 | 2 passed、1 failed；计时断言复现 `0.0 != 5.0` |
| 修复后的针对性回归 | 4 passed（含原 7 fixture oracle 核验） |
| 关联层完整测试 | 27 passed in 5.36s |
| 完整既有及新增回归 | 326 passed in 19.93s |
| 既有评测闸门 | 两个 split 与原期望完全一致，exit 0，未刷新 |
| PNG 冒烟 | 整图 1 条测量/2 条关联，偏移 ROI 2 条测量/4 条关联；严格 JSON、正常状态及原图摘要均通过 |
| 实际尾部延迟复验 | 内存增加来源收集延迟 100ms 后，总耗时 0.188717s，外部计时 0.188737s，延迟已计入；此数值只描述该次运行 |
| 跨环境比较反例 | 模拟 Linux 与另一 Windows 路径/Python 版本均通过；错误路径、Python 版本、解码器版本或 payload 均拒绝；内存期望构造未改冻结记录 |

完整测试与闸门在获准的沙箱外运行，沿用此前确认的 pytest 临时目录权限处理方式。
本轮未安装新包，没有配置独立 build/lint/type-check；实际 Ubuntu/GitHub Actions 尚未运行，
因此这里证明的是跨环境比较逻辑及本机回归，不声称远程 CI 已通过。

## 6. 能力边界（**不可声称**的部分）

- 本模块**读取两次**。它提供的只是 `read_consistency.checked_fields` 列出的字段在两次读取中相同的
  证据；**不声称**单次读取，**不声称**文件在整个过程中始终未变化，**不声称**检查范围之外的差异不存在。
- 它**不是**质量评分：没有百分制、等级、合格判定、`failure_reason`，也没有故障分类、阈值、自动重拍建议。
- 它**不新增**状态词、不重排 `attempts`、不重选候选、不改 `decode_summaries`、不改既有报告字段含义。
- 多个 profile **不是**多个独立样本，不得据此计算任何比例或识读率。
- 尚未接入 CLI、批量入口或现有报告；不写文件、不联网、不调用相机；**不新增**第三方依赖。
- 单次调用的耗时与状态只描述这一次运行，不能外推为稳定性或性能结论。

## 7. 未纳入本任务

质量评分与合格判定、故障分类（模糊/曝光/光照/脏污/条纹/噪点）、阈值与场景标定、机器学习、
GUI / Web 服务、CLI 接入、批量入口、相机参数控制、实验数据生成。

## 8. 复现命令

```powershell
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

# 关联层验收（B01–B18）
.\.venv\Scripts\python.exe -m pytest -q tests\test_quality_qr_analysis.py

# 完整回归 + 评测闸门（不加 --refresh）
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
```
