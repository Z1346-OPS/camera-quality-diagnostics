# 详细使用与历史阶段指南

本页保留原 README 的详细命令、学习教程与阶段记录。带日期的设备验收和环境安装状态属于各自历史环境；当前交付、版本与测试结果请从[仓库首页](../README.md)和[公开验收汇总](verification/acceptance-summary-2026-10-27.md)查看。命令在仓库根目录执行；示例图片、run_id 和输出目录按实际情况替换。

2026-10-01 的后续方向：逐步接入手机图片上传、标签可读性检查和服务化存储。详见[项目方向转变与迁移计划](project-direction-and-migration-plan.md)。该文档区分现有能力与规划。当前状态：**手机服务与数据库尚未实现**；**QR 解码、人工 ROI 与按清单批量评测已实现**（见下方「阶段 2」与[文档 32 文档与实现一致性核对](stage-32-docs-vs-code-consistency.md)）。

阶段 1 已新增本地 JPEG/PNG 图片分析入口（仍无手机上传）：

2026-10-02 的入口核验已补充错误码、JSON 格式版本 2、分析 ID、配置与源码哈希、运行库版本及 Git 状态。原有指标字段保留，旧 JSON 不改写。真实手机照片已由用户确认实拍来源及正确方向；验证与操作步骤见[阶段 1 核验记录](stage-1-local-input-verification.md)。

```powershell
# 在自己的克隆仓库根目录执行
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_image.py '.\photo\label.jpg' --output '.\data\reports\label-analysis-001.json'
```

结果同时打印 JSON。`--output` 可省略，此时只打印，不保存结果；指定的 JSON 路径必须是新文件，重新分析请换新文件名，父目录需先创建。原图只读、不覆盖。程序按图片内容识别 JPEG/PNG，接受 8 位灰度、RGB、带透明度及调色板图；16 位等模式明确拒绝。EXIF 方向 1–8 按定义处理；方向值 0 保留原始像素排列，并在 JSON 的 `warnings` 中提示人工核对方向，其他无效值仍拒绝。透明像素以白色背景合成，包含 RGBA/LA、调色板透明度以及 RGB/灰度 PNG 的透明色（tRNS），结果记录原图 SHA-256、预处理、全图分析区域和阈值。单文件上限 25 MiB，像素上限 1600 万；超限图片会明确报错。指标仅描述整张照片，不做标签可读性或合格判定；详见[阶段 1 记录](stage-31-local-image-analysis.md)与[本轮修正记录](stage-39-release-review-fixes.md)。

### 阶段 2：本地 QR 基线与人工 ROI

新增独立入口，不改变历史图片分析报告格式。阶段 1 实拍已验收。**阶段 2 的实拍 + 已知答案验收已于 2026-10-09 完成**：`photo/A7.jpg` 基线读出失败（`decode_error`），启用降采样搜索后读出，且与预先固定的答案逐字节相同（`truth_check.status=correct`），结果见 `data/reports/qr-A7-downscale-001.json`（本机报告，被 `.gitignore` 忽略，不随仓库交付）。仅支持 QR Code，未接入增强、网页或数据库，详见[阶段 2 记录](stage-2-roi-qr-baseline.md)。

```powershell
# 内容预先确定的合成样例：可打印此 PNG 后用手机拍摄
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py '.\data\samples\stage2-known-qr.png' --expected-file '.\data\samples\stage2-known-qr.expected.txt' --truth-source '项目样例预先指定的生成内容 STAGE2-SMOKE-001' --output '.\data\reports\qr-synthetic-001.json'

# 实拍图未知内容时，只报告是否读出，不能称为正确
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py '.\photo\A1.jpg' --output '.\data\reports\qr-photo-001.json'

# 人工 ROI 示例（必须替换为照片实际区域，坐标基于 EXIF 处理后的图像）
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py '.\photo\label.jpg' --roi 100 200 600 600 --output '.\data\reports\qr-roi-001.json'
```

ROI 为左上角 `x y` 和 `width height`，右/下边界不包含，必须完整位于图内，不补边。结果 `attempts` 始终含整图；指定 ROI 时另加该区域。各自记录指标、位置、解码耗时与状态。`decoded` 表示读出，`not_decoded` 表示未读出，`ambiguous` 表示多候选，`decode_error` 表示候选解码失败，`execution_error` 表示执行异常/依赖不可用。无真值时 `truth_check.status` 为 `not_provided`；仅单一有效码与独立已知答案逐字节相同才为 `correct`。答案文件使用 UTF-8，不自动去除 BOM、换行或空格。未读出、歧义或答案不匹配不属于程序执行异常；候选解码/执行错误返回退出码 2，并保留结构化结果。输出仅新建，不自动打开 QR 内链接。

汇总层另有 `conflict`；评测层另有 `decoded_unverified` 与 `input_error`（各状态定义见源码与[文档 32](stage-32-docs-vs-code-consistency.md)）。

### 失败补救：内部降采样搜索

整图或指定 ROI 读不出时，加 `--try-downscale` 会**保留原基线**、额外尝试解码器内部降采样搜索：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py '.\photo\A7.jpg' --try-downscale --output '.\data\reports\qr-A7-downscale-001.json'
```

两条 profile（`baseline` 与 `internal_downscale_search`）的结果、选中索引与失败索引都会写进报告，便于定位「哪条路径读出、哪条失败」，而不是只知道最终成功或失败。

### 按清单批量评测

`src/evaluate_labels.py` 按冻结清单批量评测：清单要求 8 个必填字段（`id`、`image`、`sha256`、`label_id`、`batch_id`、`split`、`source_kind`、`source`）与 4 个可选字段（`expected_file`、`expected_sha256`、`truth_source`、`roi`）。固定答案逐字节校验，失败样本**留在正确率分母内**，无真值样本单独统计，并做分组泄漏检查（同一 `label_id`、`batch_id` 或 `expected_sha256` 不允许同时出现在 `development` 与 `test`）。

```powershell
# 清单位于本机 photo\ 下（该目录被 Git 忽略），需自行准备
.\.venv\Scripts\python.exe -X utf8 .\src\evaluate_labels.py '.\photo\evaluation-development-001.json' --split development --output '.\data\reports\eval-001.json'
```

评测报告里的 `evaluation_policy` 会显式声明统计口径，例如候选选择**不使用真值**（`selection_uses_truth: false`）、正确率分母规则（`all_manifest_samples_with_truth_including_failures`），以及 `independence` 说明——它只做分组检查，**拍摄历史与答案独立性仍需人工确认**。

> ⚠️ 上表中那份**实拍**清单只有 1 个 `development` 样本、没有 `test` 样本，因此**不能用它**声称任何识读率、准确率或泛化能力。可复现的 `test` split 现在是合成数据集（见下节），它同样只描述受控退化下的行为。

### 独立质量测量模块（业务阶段 4.1）

新增数组级函数 `analyze_quality(image, roi=None)`（`src/quality_analysis.py`），对**整图或人工 ROI** 返回：

- `metrics`：清晰度（复用拉普拉斯方差）、亮度（灰度均值）、对比度（灰度总体标准差），以及
  **固定 4×4 分块**的亮度均衡（16 个块均值、`mean_range`、`mean_std`）；基础指标**复用** `src/metrics.py`，未重新实现
- `applicability`：四项测量是否都满足本接口的空间条件；区域任一边 <3 时清晰度为 `null`，任一边 <4 时亮度均衡为 `null`，
  并给出稳定原因码（`sharpness_insufficient_dimensions` / `uniformity_insufficient_dimensions`）
- `warnings`：只有三种白名单提示——`measurement_scope`（始终）、`constant_region`（区域灰度恒定）、
  `insufficient_spatial_support`（存在不可计算项）

```python
from src.quality_analysis import analyze_quality
result = analyze_quality(bgr, roi=(100, 200, 600, 600))  # roi 为 x y width height，右/下边界不包含
```

> ⚠️ 输出的是**测量事实**，不是质量评分：没有合格判定、故障类别或自动重拍动作。
> **正常的块间亮度差异不会产生警告**——`mean_range > 0` 只是测量结果，块间差异可能来自图案内容、颜色或阴影，
> 不能直接称为光照故障。固定网格不保证发现块内部的局部暗点，也不保证不同场景/尺寸之间可比。
> `valid=true` 不代表清晰、曝光正常或工业合格。本模块尚未接入 CLI、批量入口或现有报告。详见[文档 35](stage-35-evidence-based-quality-analysis.md)。

### QR 结果与质量测量的关联层（业务阶段 4.2）

新增 `analyze_quality_and_qr(path, roi=None, expected_file=None, truth_source=None, *, try_downscale=False)`
（`src/quality_qr_analysis.py`）。它是一次调用的**外围组合**：对**同一张图、同一个区域**同时取得 QR 结果
与质量测量，把既有 `analyze_label` 的完整输出作为子对象 `qr_report` **原样保留**，把 `analyze_quality`
的测量放在旁边，再用读取一致性、区域对应与 profile 归并把两者关联成一条可追溯的记录。

```python
from src.quality_qr_analysis import analyze_quality_and_qr

result = analyze_quality_and_qr('data/samples/stage2-known-qr.png', roi=(66, 66, 132, 132))
result['measurements']   # 每个 region 恰一条：整图与 ROI 分别测量
result['associations']   # 每个 (region, profile) 恰一条，用 measurement_id 引用测量
result['qr_report']      # 既有 analyze_label 的完整输出，逐字段原样
```

- **`basis` 恒为 `original_normalized_image_region`**：测量始终在标准化后的**原图区域**上完成，不是解码器
  内部降采样图。`try_downscale` 只影响解码 profile，不影响 `basis` / `region` / `quality`。
- **同一区域的多个 profile 共用一条测量记录**，不会被计成多个独立样本。
- **三处 warnings 归属分明**：`qr_report.warnings` 与 `measurements[].quality.warnings` 原样保留，
  关联层自己的 `warnings` 首版恒为 `[]`。
- **总耗时覆盖到返回前**：包含读图、解码、质量测量、来源摘要与运行库版本收集，以及报告组装。
- **只有 `QualityAnalysisError` 会转成 `quality_error` 并保留 QR 结果**；`MemoryError`、`cv2.error` 等
  继续抛出，不会被说成图像质量问题。

> ⚠️ **能力边界（不得夸大）**：本模块**读取两次**（一次供质量测量，一次由 `analyze_label` 内部读取）。
> 它只提供 `read_consistency.checked_fields` 列出的 8 个字段在两次读取中相同的证据——**不声称**单次读取，
> **不声称**文件始终未变化，**不声称**检查范围之外的差异不存在。它**不是**质量评分：没有合格判定、
> 故障分类、阈值或自动重拍建议，也不新增状态词、不改既有报告字段含义。尚未接入 CLI 或批量入口。
> 详见[文档 36](stage-36-quality-qr-association.md)。

### 固定矩阵模糊实验（业务阶段 4.3）

用一次固定的受控实验回答一个问题：同一张 QR 基图施加不同强度的高斯模糊后，质量测量怎么变，
基线解码、内部降采样搜索与最终汇总分别是什么结果。

```powershell
# 开发组与验证组分别执行；每轮新建 <run-id> 目录，已存在即拒绝覆盖
.\.venv\Scripts\python.exe -X utf8 tools\run_blur_experiment.py --group development
.\.venv\Scripts\python.exe -X utf8 tools\run_blur_experiment.py --group test
```

固定协议（不可调参）：4 张既有 clean 灰度 PNG（264×264 模块 8 px、198×198 模块 6 px，各两组）
× σ ∈ {0,1,3,5,8}，共 **20 个条件**；σ=0 直接引用原图，σ>0 每次从**原图**独立生成
（`GaussianBlur`、`ksize=(0,0)`、`sigmaX=sigmaY=σ`、`BORDER_REFLECT_101`、灰度 PNG 压缩 6），
新增 16 张退化 PNG；每条件调用一次 `analyze_quality_and_qr(..., try_downscale=True)`。
独立答案直接取清单的 `expected_file`/`expected_sha256`/`truth_source`。
分析返回后核对报告中实际使用的图片与答案摘要；与计划不一致即中断，不将该条件计为完成。

实测（2026-10-13）：清晰度随 σ 急剧下降（约 7300–10300 → 约 2.3–4.2），亮度基本不变，
对比度单调下降。σ=0/1 全部 `decoded`+`correct`，σ=3 有 3 个 `correct`、`test-02` 为
`decode_error`，共 11 个条件为 `correct`；σ=5 的失败形态因基图而异
（`ambiguous` / `decode_error` / `not_decoded`），σ=8 全部 `not_decoded`。
**基线解码与内部降采样搜索在全部 20 个条件中状态逐一相同**——本矩阵中没有出现降采样恢复。

> ⚠️ **能力边界**：只做固定矩阵的模糊实验，不含其他退化类型、多因素组合或 ROI 实验。
> 不输出准确率、通用阈值、故障原因或跨场景有效性结论；状态数量只描述这 20 个条件与 4 张基图，
> **不能外推**。验证组（`test` split）已在历史回归中出现，**不是盲测**。
> 产物仅新建于 `data/experiments/phase-4.3-blur-v1/<run-id>`，不覆盖。
> 详见[Phase 4.3 记录](tasks/phase-4.3-blur-experiment.md)。

### 定时采集与间隔留证（业务阶段 4.4）

**Linux 后端适配（2026-10-19）**：`run_capture.py` 在 Linux 上请求 `CAP_V4L2`，
Windows 上继续请求 `CAP_DSHOW`；报告记录对应请求与实际后端，均保留取帧失败传播防护。
本次适配不涉及 `main.py`、`camera_test.py` 的交互入口。Ubuntu 实机采集仍待验证，
不能由单元测试推断任意设备可用。详见 [Linux 适配记录](stage-38-linux-capture-backend.md)。

Ubuntu 在项目根使用已安装依赖的 `.venv`；输出目录须不存在：

```bash
./.venv/bin/python -B -X utf8 src/run_capture.py --camera-index 0 --duration 10 --interval 5 --output-dir data/reports/linux-trial-001
./.venv/bin/python -B -X utf8 src/review_capture.py data/reports/linux-trial-001
```

无预览的定时采集入口：按固定间隔从单个摄像头采样，只对选中帧测量、保存并留证，
最后发布一份任务报告。首版只做运行保护，**不做质量评分或故障判定，也不保证严格到时退出**
（同步读取、测量与保存都可能阻塞；报告记录的是实际时长）。

```powershell
.\.venv\Scripts\python.exe -X utf8 src\run_capture.py --camera-index 0 --duration 30 --interval 5 --output-dir data\reports\timed-capture\trial-001
```

- 参数：`--camera-index`（默认 0）、`--duration`（默认 30，1～3600 秒）、
  `--interval`（默认 5，1～3600 秒）、`--output-dir`（必填的新目录，已存在即拒绝）。
  理论采样点数 `ceil(duration/interval)` 不得超过 120；`interval` 大于 `duration` 时只有一个理论采样点。
  3600 秒与 120 个采样点是**首版运行保护策略**，不是相机或质量阈值。
- 采样规则：打开成功后取单调时钟起点 `t0`；每次 `read()` 前检查截止时间；
  有效帧按 `floor(elapsed/interval)` 归属区间，**同一区间最多一个样本，跨过的旧区间不补采**；
  截止后返回的有效帧计入有效帧数但不保存。读取失败或无效图像优先作为错误，
  不因已经超时而掩盖失败。
- **取帧失败传播（2026-10-17）**：默认摄像头后端（`CAP_DSHOW`）经一层薄适配读取，
  显式检查 `grab()`/`retrieve()` 的真实成功标志——`grab` 失败即判读取失败且不再 `retrieve`，
  `retrieve` 失败即使返回非空数组也不作为成功帧交给采集流程。此前直接调用
  `cv2.VideoCapture.read()` 时，其丢弃 `retrieve()` 返回值、仅按输出数组是否为空判定成功，
  底层取帧失败但数组非空会被误计为成功采集。此改动只修正失败传播，**不**新增重试、
  补采、删帧或亮度阈值，也**不**声称历史近黑画面的根因已确认。详见
  [取帧失败传播防护记录](stage-37-read-failure-guard.md)。
- 每个新任务目录含 `camera_quality_runs.csv`、`camera_colors_runs.csv`、
  `camera_frame_<run_id>_<frame_count>.png` 与 `capture_task.json`。
  `run_id` 由程序生成（32 位小写十六进制 UUID，不接受 CLI 输入）；颜色记录
  `scene_label` 固定为 `unspecified`；不写历史公共 CSV，也不生成旧会话 JSON。
- 一次采样的顺序为：计算指标 → 质量 CSV → 颜色 CSV → PNG → PNG 的 SHA-256。
  任一步失败立即停止，已有成功内容保留，不回滚、不删除、不追加伪成功记录。
- 退出码：正常完成 0；参数错误与已定义的采集失败 2；`KeyboardInterrupt` 130；
  其他未预期异常保留回溯和非零退出（不会「打印错误但返回 0」）。
- 报告 `capture_task.json` 为严格 JSON（不允许 NaN/Infinity），记录状态、停止原因、
  计数、逐样本记录、设备信息（取不到时写 null，不猜测）、来源文件 SHA-256 与运行库版本；
  正式报告先写同目录临时文件、完整关闭后用硬链接独占发布；即使同名目标在发布瞬间出现也拒绝覆盖。
  输出文件系统须支持硬链接（本机 NTFS 与 Ubuntu CI 的发布测试已验证；其他文件系统需另行验证），不支持时明确报错并保留临时文件。
  发布成功后移除临时名字；移除失败会报错并注明正式报告已发布，不自动删除正式报告。详见[本轮修正记录](stage-39-release-review-fixes.md)。

**实机验收（2026-10-14，本机内置摄像头，`.venv`；下表的两个目录对应最终源码版本）**：

| 运行 | 目录 | 请求 | `capture_elapsed_seconds` | 计划/实际样本 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | `data/reports/timed-capture/trial-003` | 30 秒 / 5 秒 | 30.0 秒 | 6 / 6 | `completed`，6 个样本 5 项指标逐帧复核一致 |
| 2 | `data/reports/timed-capture/trial-004` | 10 秒 / 5 秒 | 10.0 秒 | 2 / 2 | `completed`，设备可再次打开，2 个样本复核一致 |

（「实际时长」是报告里的 `capture_elapsed_seconds`，只含采集与逐样本处理／保存，
不含打开与释放设备；两次进程的总耗时分别约 31.7 秒与 11.6 秒。
更早的 `trial-001`、`trial-002` 是修复前版本的运行，原样保留、未改写，
其报告中的源码摘要对应旧源码，不作为最终版本证据。
上述试跑目录位于本机 `data/reports/`，被 Git 忽略、不随仓库交付；
公开复现请使用[三种情况的采集复核演示](tasks/capture-review-walkthrough.md)。）

> ⚠️ **能力边界**：只做本机单设备的固定间隔采样；不做重试、不切换后端、不自动重连，
> 也不做并发或断点续跑。实机结果**不构成**硬实时、工业稳定性或识读准确率结论。
> 产物仅新建于指定任务目录，不覆盖。详见[Phase 4.4 记录](tasks/phase-4.4-timed-capture.md)。

### 采集任务离线复核入口（业务阶段 4.5）

初次使用可按[三种情况的操作演示](tasks/capture-review-walkthrough.md)运行临时合成数据，查看正常、缺图与指标不一致的完整 JSON；示例不依赖本机实拍文件。

采集结束后只指定任务目录即可复核：读取该目录的 `capture_task.json`、两份 CSV 与留证 PNG，
核对任务声明、CSV 关联键、图片摘要与「按当前算法重算」的五项指标，输出一份 JSON。

```powershell
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py data\reports\timed-capture\trial-003
```

- 只支持 `schema_version=1`、`report_type=camera_timed_capture`、`status=completed` 的静态任务目录；
  非 completed 返回 `not_reviewed`（退出 2），不复核部分记录、不恢复数据、不改原状态。
- 全部 CSV 键必须与任务声明的 `(run_id, frame_count)` 集合完全一致，**不做批次过滤**；
  集合不一致时 `frames=[]`、`verified_frames=0`，不进入指标重算。
- 图片摘要与指标分别核对：PNG 无损重编码导致像素相同而文件摘要不同时，仍报 `image_hash_mismatch`，不能整体通过。
- 五项指标始终是「按当前算法与当前阈值重算」，`comparison_basis` 固定为 `current_algorithm_one_decimal`；
  任务记录与当前运行库、阈值、`metrics.py`/`analysis_config.py` 摘要的差异只作为
  `measurement_context_*` 提示，不阻断、不归因、**不建版本闸门**。
- 退出码：一致 0；不一致 1；非 completed 2；必需 JSON/CSV 缺失、坏格式、类型错误或不安全路径为输入错误（2，stdout 为空）；
  缺失 PNG 是逐帧问题（1）。只读、不打开摄像头、不创建新报告、不覆盖历史文件。

> 复核只证明「文件与当前算法一致」，**不**证明画面真实、场景标签正确或工业合格，也不做故障判定。
> 实机 `trial-003`（6 帧）与 `trial-004`（2 帧）逐帧复核一致。
> 详见 [Phase 4.5 记录](tasks/phase-4.5-capture-review.md) 与 [2026-10-15 本地复验](tasks/phase-4.5-verification-2026-10-15.md)。

### 测试与验证体系

- **pytest 自动化回归**：`pytest.ini` 将默认收集范围固定为完整 `tests/`，本机 `data/reports/` 中的历史诊断夹具不会混入；需要运行历史夹具时显式指定路径及其环境。用例数量、实际通过／跳过及环境限制见[能力矩阵第 0 节](stage-34-project-capability-matrix.md)；远程结果以对应提交的 Actions 记录为准。
- **输入校验与错误分类**：非法参数、边界与资源上限、业务结果与程序执行异常分开处理
- **证据核对**：原始帧留证、指标重算、跨报告关联键核对、留证 PNG 可解码性
- **非破坏性输出**：`--output` 独占新建、不覆盖；历史报告与历史 JSON 的字段含义不改写；只读命令不修改 CSV
- **可复现口径**：报告记录源码 SHA-256、实现版本、Git 提交与运行库版本

### 合成回归数据集与 CI 期望闸门

**为什么存在**：唯一能证明「基线失败 → 内部降采样搜索救回」的原始证据是实拍图 `photo/A7.jpg`，而该照片被 `.gitignore` 忽略、进不了 CI。合成数据集把这条恢复路径变成**每次提交都能重复验证**的样本。

**覆盖什么**：`data/samples/synthetic-qr-v1/`，`development` 与 `test` 各 23 个受控退化样本（clean / downscale / blur / brightness / rotation / jpeg / occlusion / **noise-large**）。两个 split 的载荷完全不相交（`SYNTH-DEV-*` 与 `SYNTH-TEST-*`），因此不存在标签、批次或答案跨组泄漏。其中 `noise-large`（大像素模块 + 传感器噪声 + JPEG）是唯一能复现真实拍摄失败形态的一族。

**当前行为**（`data/manifests/evaluation-synthetic-expectations.json`，**精确值而非阈值**）：

| split | 基线 | 降采样搜索 | paired_change |
| --- | --- | --- | --- |
| development | 18/23 | 21/23 | improved=3 degraded=0 |
| test | 18/23 | 21/23 | improved=3 degraded=0 |

**CI 验证什么**：`GitHub Actions` 在 push 和 pull request 时执行完整 pytest 测试（`.venv/bin/python -m pytest -q`）与 `tools/check_evaluation_expectations.py`。当前本地测试数量与验证记录见[能力矩阵](stage-34-project-capability-matrix.md)；本地通过不代表远程 CI 已通过，远程执行结果以对应提交的 Actions 记录为准。闸门**不依赖退出码**——评测器对「程序故障」与「有样本按预期读不出」都返回 2，因此它把报告 JSON 与入库期望逐项精确比对。行为确实变了必须 `--refresh` 并经人工确认后提交。

关联层的通用 pytest 将图片绝对路径、运行库版本、解码器版本及源码摘要按当前环境和实际源码文件独立校验，
业务稳定字段仍与冻结 oracle 精确比较；历史 oracle 保持原字节。
路径/版本/源码身份适配不等于忽略这些字段，也不扩大 volatile 白名单；篡改任一源码摘要仍必须失败。
原验证记录见文档 36，本次源码身份核验调整见[文档 39](stage-39-release-review-fixes.md)。

```powershell
# 重新生成数据集（重写样例目录与两份清单；稳定后不要反复重生成）
.\.venv\Scripts\python.exe -X utf8 tools\generate_synthetic_samples.py

# 校验评测结果与入库期望是否一致
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
```

> ⚠️ 该数据集**只能**说明「受控退化下的行为」，**不能**用于声称识读率、准确率或泛化能力。详见[文档 33](stage-33-synthetic-regression-dataset.md)。

### 能力与文档的一致性

上面的能力描述已与代码对齐，核对过程与逐条证据见[文档 32 文档与实现一致性核对](stage-32-docs-vs-code-consistency.md)。**未实现的能力不要写成已实现**；判断某能力是否已实现，以该文档为准。

---

## 1. 项目名称

`camera-quality-diagnostics` —— 摄像头图像质量诊断工具

---

## 2. 项目目标

在工业视觉场景里，摄像头拍出来的图**质量会变差**，但原因往往不好判断。例如：

- 镜头脏了 → 画面整体发雾
- 对焦跑了 → 边缘模糊
- 光源老化 → 整体偏暗或偏色
- 传输丢包 → 画面出现马赛克、条纹
- 相机过热 → 噪点变多

长期目标是逐步研究可复核的图像质量排查方法。**目前已实现**摄像头采集、亮度/曝光比例/清晰度/对比度等指标、颜色通道均值、读帧失败事件记录、按批次保存 CSV/JSON，以及可选原始帧 PNG 留证和数值复核。

**尚未实现**脏污、条纹、噪点、偏色等故障的自动识别，也未完成具体场景阈值标定。现有数字用于观察和对照，不能直接判定工业相机是否合格或推断故障原因。场景标签由操作者按键选择，不是程序识别结果。

---

## 3. 环境安装方式

### 已经装好了，这里是记录

| 项目 | 值 |
|---|---|
| Python | **3.12.10**（官方 CPython，64 位） |
| Python 安装位置 | `D:\DevTools\Python312` |
| 虚拟环境 | `D:\Projects\Python\camera-quality-diagnostics\.venv` |
| pip 缓存 | `D:\DevCache\pip` |

> 上表记录的是本机环境，不要求其他电脑使用完全相同的安装路径；重建环境前应核对项目依赖与本机 Python 版本。

### 如果要在别的电脑上重建

```powershell
# 1. 安装与依赖兼容的 Python 3.12，并确认 python 命令可用

# 2. 建虚拟环境
python -m venv .venv

# 3. 按清单装依赖
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 4. 如何运行

### 方式一：在 VS Code 里（推荐）

1. 用 VS Code 打开本文件夹
2. 按 **F5** → 选择「调试主程序 (src/main.py)」
3. 下方终端会打印环境自检结果

**F5 之前不需要手动敲任何命令。** VS Code 会自动用 `.venv` 里的 Python。

### 方式二：在终端里

```powershell
# 本机示例：先进入项目根目录；其他电脑请换成实际路径
# 在自己的克隆仓库根目录执行

# 环境自检
.\.venv\Scripts\python.exe src\main.py

# 摄像头质量测试（按 s 保存当前指标，按 q 退出）
.\.venv\Scripts\python.exe src\camera_test.py

# 可选：按 s 时额外保存未叠加文字的原始帧 PNG；画面可能含个人信息，默认不启用
.\.venv\Scripts\python.exe src\camera_test.py --save-frames

# 无预览定时采集：按间隔采样并留证；输出目录必须是新目录，已存在即拒绝
.\.venv\Scripts\python.exe -X utf8 src\run_capture.py --camera-index 0 --duration 30 --interval 5 --output-dir data\reports\timed-capture\trial-001

# 只读汇总带标签颜色报告（不打开摄像头，不修改 CSV）
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_colors.py

# 新批次报告产生后，按 run_id 和场景分别汇总（旧报告保持不变）
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_colors.py .\data\reports\camera_colors_runs.csv

# 同次按 s 的质量指标写入 camera_quality_runs.csv，与颜色批次报告共享 run_id 和 frame_count

# 只读检查两份批次报告是否存在单侧记录；有未配对记录时退出码为 1
.\.venv\Scripts\python.exe -X utf8 .\src\check_reports.py

# 只显示指定批次的配对情况；仍校验完整 CSV，不修改旧记录
.\.venv\Scripts\python.exe -X utf8 .\src\check_reports.py --run-id 7bfd31a24dc64d96aa22311a78bf7200

# 只读检查指定批次的 PNG 是否存在且可解码
.\.venv\Scripts\python.exe -X utf8 .\src\check_frame_evidence.py --run-id 9dd84fe9fbe24e32ab52ab0972e83ba3

# 只读重算一张原始帧的 5 项质量指标，并与同帧 CSV 比较
.\.venv\Scripts\python.exe -X utf8 .\src\verify_frame_metrics.py --run-id 9dd84fe9fbe24e32ab52ab0972e83ba3 --frame 306

# 只读复核该批次全部已记录帧，逐帧报告一致、数值不同或无法复核
.\.venv\Scripts\python.exe -X utf8 .\src\verify_run_metrics.py --run-id 9dd84fe9fbe24e32ab52ab0972e83ba3

# 首次记录一个新批次时使用；此示例批次已创建备注，再运行会报“文件已存在”
.\.venv\Scripts\python.exe -X utf8 .\src\record_conditions.py 7bfd31a24dc64d96aa22311a78bf7200 --note '采集后回忆：按2时换上了彩色物体，其他条件基本没变。光照、位置和纸张距离未量化；自动曝光状态未核实。'

# 摄像头退出后，按批次导出完整配对的 JSON；替换成实际 run_id
.\.venv\Scripts\python.exe -X utf8 .\src\export_pairs.py f1c6d22b952147bf91a2b3ac7c0cbc9b

# 只读汇总一个批次 JSON 中各场景的样本数与指标范围
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_pairs.py .\data\reports\camera_pair_f1c6d22b952147bf91a2b3ac7c0cbc9b.json

# 只读核对三场景标签是否按白纸→彩色物体→恢复白纸各保存一次
.\.venv\Scripts\python.exe -X utf8 .\src\validate_capture.py .\data\reports\camera_pair_7bfd31a24dc64d96aa22311a78bf7200.json

# 只读比较同一批次的白纸与恢复白纸标签，显示后者减前者的均值差
.\.venv\Scripts\python.exe -X utf8 .\src\compare_white.py .\data\reports\camera_pair_e5125e7c90fb4cfda143f2252b596fa0.json

# 跨批次汇总白纸差值；有更多批次时在命令末尾追加其 JSON 路径
.\.venv\Scripts\python.exe -X utf8 .\src\summarize_white_runs.py .\data\reports\camera_pair_e5125e7c90fb4cfda143f2252b596fa0.json

# 跑测试
.\.venv\Scripts\python.exe -m pytest
```

第一次尝试时，先在 PowerShell 进入项目根目录，再运行摄像头命令。窗口获得焦点后按 `0/1/2/3` 选择场景标签、按 `s` 保存、按 `q` 退出；关闭采集程序后再运行只读核对命令，并把示例中的 `run_id` 和帧号换成终端实际输出。只有显式使用 `--save-frames` 才会产生 PNG；不启用时，图片核对命令报告缺失是预期结果。图片可能包含私人画面，不必上传到聊天或提交 Git。

JSON 导出只处理指定批次；该批次若有未配对记录会失败。历史其他批次的单侧记录不会混入导出。结果保存为 `data/reports/camera_pair_<run_id>.json`，已存在时不会覆盖。JSON 只是结构化指标，不包含故障判断。
首次按 `s` 保存 CSV 后，还会尝试独立保存 `data/reports/camera_session_<run_id>.json`，记录配置的摄像头编号、OpenCV 报告的后端和当前帧尺寸；失败会在终端提示，CSV 仍保留。它不记录或推断光照、纸张距离和自动曝光状态，这些仍需人工备注。
仅在显式添加 `--save-frames` 时，每次按 `s` 才会尝试保存 `data/reports/camera_frame_<run_id>_<frame_count>.png`。PNG 保留原始画面、没有指标文字，可能包含人脸或其他私人内容；文件只留在本机且被 Git 忽略，不应随意分享。保存失败会提示，已保存的 CSV 不会回滚。
JSON 汇总也只是描述性统计；单次或少量采样不能据此设定设备合格阈值。
白纸标签差值也不能证明相机故障或恢复效果；场景标签由操作者手动选择，需结合拍摄条件解释。
跨批次汇总会拒绝重复的 `run_id`；只有一个完整批次时不显示跨批次范围。多个批次也仍不足以自动设定合格阈值。

> ⚠️ **不要用全局 Python 跑这个项目。** 在 PowerShell 中从项目根目录使用 `.\.venv\Scripts\python.exe`，
> 否则会出现"明明装了包却 import 不到"的问题。

---

## 5. 如何调试

在 VS Code 里按 **F5**，`launch.json` 已经准备好三套配置：

| 配置名 | 用途 |
|---|---|
| **调试主程序 (src/main.py)** | 默认，按 F5 直接走这个 |
| **调试当前文件 (当前打开的 .py)** | 换文件不用改配置，通用 |
| **调试摄像头测试 (src/camera_test.py)** | 专门调摄像头那个程序 |

### 打断点

在行号左边点一下，出现红点就是断点。按 F5 后程序会停在那里。

| 按键 | 作用 |
|---|---|
| <kbd>F5</kbd> | 启动 / 继续 |
| <kbd>F10</kbd> | 单步跳过（不进入函数） |
| <kbd>F11</kbd> | 单步进入（进入函数内部） |
| <kbd>Shift</kbd>+<kbd>F5</kbd> | 停止调试 |

**看变量值**：停住时鼠标悬停在变量上，或看左侧「变量」面板。

> 💡 **建议先练一次**：打开 `src/main.py`，在 `in_venv = sys.prefix != sys.base_prefix`
> 这一行打断点，按 F5，然后悬停看 `sys.prefix` 和 `sys.base_prefix` 的区别 ——
> 这能帮你直观理解「虚拟环境」到底是什么。

---

## 6. 当前阶段功能

**v0.1 —— 环境验证阶段，已完成：**

- ✅ Python 3.12.10 安装并配置好 PATH
- ✅ 项目虚拟环境 `.venv` 建好
- ✅ OpenCV / NumPy / Matplotlib / pytest 装好
- ✅ VS Code 配置好（F5 可调试，自动用 `.venv`）
- ✅ 环境自检程序 `src/main.py`
- ✅ 摄像头测试程序 `src/camera_test.py`
- ✅ 自动化测试 `tests/test_environment.py`

**v0.2 —— 基础质量指标阶段，已完成：**

- ✅ 平均亮度、欠曝比例和过曝比例
- ✅ 拉普拉斯方差清晰度分数
- ✅ 灰度标准差对比度分数
- ✅ 256级灰度直方图、峰值灰度和峰值像素数量
- ✅ 实时画面叠加显示
- ✅ 按 `s` 追加保存单帧 CSV 报告
- ✅ 指标和报告自动化测试

> 当前结果依赖画面内容、光照和相机自动曝光。默认阈值尚未完成具体工业场景标定，不应把单个分数直接解释为“合格”或“故障”。

**v0.2.1 —— 采集事件记录，已完成：**

- ✅ 已打开摄像头发生读帧失败时记录 `read_failed`
- ✅ 独立保存到 `data/reports/camera_events.csv`
- ✅ 记录毫秒时间、最后成功帧数、事件类型和说明
- ✅ 软件模拟验证终端提示、事件写入和资源释放

> 当前电脑使用内置摄像头，因此没有进行真实硬件断连测试；集成流程通过安全的软件模拟验证。

**后续完成的记录与核对能力：**

- ✅ 同一次按 `s` 的质量与颜色记录用 `run_id`、帧号关联；可按批次导出配对 JSON
- ✅ 人工场景标签、三场景顺序检查、白纸前后与跨批次的描述性比较
- ✅ 首次保存时记录摄像头编号、OpenCV 后端与帧尺寸的会话 JSON
- ✅ 显式启用后保存未叠字原始帧 PNG；真实摄像头批次已验证保存成功
- ✅ 只读核对 PNG 与 CSV 的关联、可解码性，以及单帧或整批次的 5 项指标数值一致性
- ✅ 定时采集任务目录级只读复核入口 `src/review_capture.py`：组合任务声明、两份 CSV 与留证 PNG，分别核对文件摘要与指标

> 已完成的“核对”不是自动场景识别。真实留证批次只验证了少量手动保存帧；不能据此声称检测准确率或设备故障识别能力。

**标签读码与独立评测阶段，已完成：**

- ✅ 本地 QR 解码入口 `src/analyze_label.py`：整图与人工 ROI，依赖 `zxing-cpp`
- ✅ 失败补救：`--try-downscale` 内部降采样搜索，两条 profile 与失败索引写入报告
- ✅ 独立答案核对：仅单一有效码与预先固定的答案逐字节相同才判 `correct`；无真值时为 `not_provided`
- ✅ 按清单批量评测 `src/evaluate_labels.py`：清单契约、分组泄漏检查、失败样本留在正确率分母、无真值样本单独统计
- ✅ 实拍排障记录：`photo/A7.jpg` 基线 `decode_error` → 降采样读出 → 与预设答案逐字节相同
- ✅ 评测闭环已实测（2026-10-12）：`exit=0`、`status=completed`、`selection_uses_truth: false`、运行前后仓库无改动

> 评测**机制**已经具备；**实拍**方向目前只有 1 份 `development` 清单、1 个样本，可复现的 `test` split 由合成数据集提供（见上文「合成回归数据集与 CI 期望闸门」）。现有数字都是过程记录，不能当作识读率或准确率结论。

**定时采集与间隔留证，已完成（业务阶段 4.4）：**

- ✅ 无预览定时采集入口 `src/run_capture.py`：按间隔采样，只对选中帧测量与保存
- ✅ 可注入的摄像头工厂与单调时钟；模拟设备与可控时钟下不等待真实时间即可验证调度
- ✅ 严格区间调度：同一区间最多一个样本、跨过的旧区间不补采、截止后有效帧计入但不保存
- ✅ 每个任务独占新目录，含质量 CSV、颜色 CSV、留证 PNG 与 `capture_task.json`
- ✅ 报告为严格 JSON：状态、停止原因、计数、逐样本状态与 SHA-256、来源摘要与运行库版本
- ✅ 报告先写同目录临时文件、完整关闭后再发布；目标已存在即拒绝，不留半截报告
- ✅ 异常与清理：保留原异常类型、优先释放设备、报告发布失败不覆盖原始执行异常

> 只做本机单设备的固定间隔采样。不保证严格到时退出，实机结果不构成硬实时、工业稳定性或识读准确率结论。

---

## 7. 后续计划

按难度递进，逐步把"判断图像哪里不对"做出来：

**v0.2 —— 基础质量指标**
- [x] 平均亮度计算与实时显示
- [x] 过曝/欠曝像素比例（默认阈值用于观察，尚未完成场景标定）
- [x] 清晰度分数：拉普拉斯方差（模糊阈值尚未标定）
- [x] 对比度分数：灰度标准差（低对比度阈值尚未标定）
- [x] 灰度直方图及峰值显示
- [x] 按 `s` 输出单帧质量报告（CSV）

**v0.3 —— 故障模式识别**
- [ ] 脏污检测：通过局部对比度异常定位镜头脏点
- [ ] 条纹/马赛克检测：基于频域分析
- [ ] 噪点估计：估计噪声水平
- [ ] 偏色检测：BGR 通道均值已完成，基准和阈值未完成

**v0.4 —— 工程化**
- [ ] 实时监控模式（连续检测并画趋势曲线）
- [ ] 阈值可配置（不同场景不同标准）
- [ ] 报告可视化（Matplotlib 出图）
- [ ] 对任意历史图片做批量质量分析（现有批次复核只处理本项目已保存、已关联 CSV 的 PNG）

**v1.0 —— 可用工具**
- [ ] 打包成可执行文件，不装 Python 也能用
- [ ] 图形界面

---

## 8. 目录结构

```
camera-quality-diagnostics\
├── .venv\                  ← 虚拟环境（不要提交到 Git）
├── .vscode\
│   ├── settings.json       ← 让 VS Code 用 .venv
│   └── launch.json         ← F5 调试配置
├── src\
│   ├── main.py             ← 环境自检
│   ├── camera_test.py      ← 摄像头采集、显示、按键和保存入口
│   ├── run_capture.py      ← 无预览定时采集入口（按间隔采样并留证）
│   ├── capture_task.py     ← 定时采集的配置、调度、测量、保存与任务报告
│   ├── metrics.py          ← 图像质量指标计算
│   ├── quality_analysis.py ← 独立质量测量（ROI / 固定 4×4 分块 / 结构化测量限制）
│   ├── quality_qr_analysis.py ← QR 报告与质量测量的关联层（外围组合，读取一致性）
│   ├── report.py           ← CSV 报告保存
│   ├── frame_evidence.py   ← 可选原始帧 PNG 保存
│   ├── check_reports.py    ← 两份 CSV 的关联键核对
│   ├── check_frame_evidence.py ← PNG 是否存在且可解码
│   ├── verify_frame_metrics.py ← 单帧 PNG 指标重算核对
│   ├── verify_run_metrics.py   ← 整批次 PNG 指标重算核对
│   ├── review_capture.py   ← 定时采集任务目录级只读复核入口
│   └── ...                 ← JSON 导出、场景与跨批次描述性分析
├── tests\                 ← 指标、报告、采集流程及各核对命令的自动测试
├── data\
│   ├── samples\            ← 样本图片（会提交）
│   └── reports\            ← 生成的报告（不提交）
├── docs\                   ← 分阶段学习记录、真实验证证据和阶段总结
├── .gitignore
├── README.md               ← 本文件
└── requirements.txt        ← 依赖清单
```

---

## 9. 常见问题

### 按 F5 报 `ModuleNotFoundError: No module named 'cv2'`

说明用的是全局 Python，不是 `.venv`。
点 VS Code 右下角的 Python 版本号，选 `.venv\Scripts\python.exe`。

### 摄像头打不开

常见原因（程序里也会提示）：
1. 被相机应用 / 腾讯会议 / 钉钉 / Zoom 占用
2. 编号不是 0，把 `camera_test.py` 里的 `CAMERA_INDEX` 改成 1 或 2
3. 驱动问题，去设备管理器看有没有黄色感叹号

这属于硬件条件，不代表 Python 环境有问题。

### 装了包但 import 不到

确认命令用的是 `.\.venv\Scripts\python.exe -m pip install xxx`。
如果直接敲 `pip install xxx`，可能装到了全局 Python。
