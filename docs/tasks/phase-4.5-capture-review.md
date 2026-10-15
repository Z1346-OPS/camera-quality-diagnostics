# Phase 4.5：采集任务离线复核入口（缩减版）

- 日期：2026-10-14。
- 状态：功能提交 `66b05d6` 已交付且远程 478 passed；本轮继续补齐固定 JSON/CSV 的真实符号链接测试（第 8.5 节），对应新版本 CI 待核验。历史自测与冻结规格保留，Windows 权限限制不变。
- 基线：`dd97998df18b2974a3530eae4d3e7e9cf41da33f`；本地工作区干净，已推送 `origin/main`。
- 基线远程验证：GitHub Actions `38551307781`，精确对应上述提交，`454 passed in 7.93s`，两组评测闸门通过。此为历史实测，不预填下一轮结果。
- 分工：Codex 设计；用户审核具体规格；Claude Code 实现与自测；Codex 验收；DeepSeek 只读复核；用户收尾。

## 1. 前提核验

| 能力 | 证据 | 结论 |
| --- | --- | --- |
| CSV 关联键校验 | `src/check_reports.py:23,52`：读取键与完整报告配对 | 已存在，直接复用 |
| PNG 缺失和可解码性 | `src/check_frame_evidence.py:17` | 已存在，不重写检测算法 |
| 单帧五项重算 | `src/verify_frame_metrics.py:27`：返回 CSV/重算字符串对 | 已存在，直接复用 |
| 批次逐帧复核 CLI | `src/verify_run_metrics.py:18`：需要用户提供 run_id 和三处路径，未读取任务 JSON | 已存在，但不是目录级入口 |
| 描述性统计 | `src/summarize_pairs.py:27` | 已存在，本任务不新增统计 |
| 输入一个定时采集目录，关联任务声明、CSV 与 PNG 并集中输出 | `src/capture_task.py:272,316` 写入任务与样本声明；上述复核入口不读取 `capture_task.json` | 确认缺失，仅补这一层组合 |

只读实测：`trial-003` 6 帧、`trial-004` 2 帧均配对、PNG 有效、五项重算一致。
对 `trial-004` 一帧仅在内存以 PNG 压缩 0/9 重编码，像素相同而摘要不同。这支持分别核对文件摘要与指标的必要性，未修改原图。

## 2. 目标与使用流程

用户运行既有定时采集，结束后只指定任务目录，即可取得逐帧复核结果，不再手动填写批次 ID、图片目录和两份 CSV 路径。

拟定入口（尚未实现）：

```powershell
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py data\reports\timed-capture\trial-003
```

首版只支持 schema_version=1、report_type=`camera_timed_capture`、status=`completed` 的静态任务目录。失败/中断任务明确返回未复核，不恢复数据。采集必须先结束；不支持并发改写输入目录。

### 2.1 最小实现

- 新增 `src/review_capture.py`，含 `CaptureTaskReviewer(task_dir).review()` 与 CLI `main(argv=None)`，支持脚本和 `python -m src.review_capture` 调用。一个对象负责一个目录的复核，不引入继承或插件体系。
- 构造对象不打开摄像头、不创建目录、不写文件。`review()` 每次只读检查；重复调用不累加状态。
- 自动使用目录中的 `capture_task.json`、`camera_quality_runs.csv`、`camera_colors_runs.csv`；不使用旧工具的全局默认路径。
- 从任务读取本次实际需要的字段：格式版本、类型、run_id、status、counts.samples_completed，以及 samples 中的 frame_count/image_file/image_sha256/三项保存状态。其余历史字段不重新建立校验体系。
- JSON 必须为对象，拒绝非有限 JSON 常量；版本为 Python int 且为 1，run_id 为规范小写 UUID。样本帧号为正 Python int、不得重复；摘要为64位小写十六进制。completed 任务的 samples 非空；缺字段/错误类型作为输入错误。
- `samples_completed` 与样本数不符或 completed 样本有非 written 保存状态：记录任务声明不一致，不判相机故障。**不要求实际数等于理论采样数**，不重演采样调度。
- 调用 `reconcile_reports(quality, color)` 核对完整文件。所有 CSV 键必须与任务声明的 `(run_id, frame_count)` 集合完全一致，禁止通过批次过滤掩盖混入记录。集合不一致时返回问题，不进入指标重算，不临时改写 CSV。
- 图片名必须等于 `camera_frame_<run_id>_<frame_count>.png`。先验证名称和解析后的路径位于任务目录内，再读取。固定 JSON/CSV 路径也不得通过链接逃出任务目录；路径不安全是输入错误。
- 对每个声明样本读取 PNG 摘要，与记录比较；调用既有 `compare_frame_metrics()` 完成 PNG 可解码性检查与五项重算，保留原接口的一位小数规则。不能从旧 CLI 的打印文本提取结果，不能复制指标算法。
- 无需单独重复调用 `check_frame_evidence()`：`compare_frame_metrics()` 已检查 PNG 格式与 BGR 图像有效性。缺失、空文件、不能解码均作为该帧无法复核，继续其他帧。
- 只检查声明的图片；**不扫描或判定其他额外文件**。新增“目录无任何多余文件”的规则不在本任务范围。
- 每帧摘要差异与指标差异分别记录；摘要不同但像素/指标相同，仍不能整体通过。

### 2.2 比较口径，不建立版本闸门

- 五项指标始终是“按当前算法与当前阈值重算”，不是声称重建采集时环境。
- 对比任务中可取得的 metric_config、运行库版本、`metrics.py`/`analysis_config.py` 摘要与当前值。缺失或不同仅产生 `measurement_context_unavailable` / `measurement_context_differs` 提示，不阻断文件与指标检查，不将其作为图片故障。
- 不核对其他四个采集源码摘要，不要求相同 Git 提交。不得增加“全版本相同才能复核”的强制闸门。
- 当前算法重算值不同，记为指标不一致；说明原因可能包含算法/配置差异，不自动归因。

### 2.3 输出与退出码

`review()` 返回可用 `allow_nan=False` 序列化的字典。CLI 成功处理输入时 stdout 只输出一份 JSON，不混入其他打印文本。结构固定为：

```json
{
  "schema_version": 1,
  "report_type": "capture_task_review",
  "run_id": "...",
  "task_status": "completed",
  "verification_status": "consistent",
  "comparison_basis": "current_algorithm_one_decimal",
  "counts": {"reported_samples": 2, "csv_pairs": 2, "verified_frames": 2},
  "frames": [
    {"frame_count": 1, "image_sha256_match": true,
     "metrics": {"brightness": ["100.0", "100.0"]}}
  ],
  "issues": [],
  "warnings": []
}
```

示例只展示一个 frame 和一项 metric；实际 frames 按帧号升序，成功重算包含既有接口全部五项 `(CSV字符串, 当前重算字符串)`，JSON 中为两元素数组。无法重算时 metrics=null；无法取得图片摘要时 image_sha256_match=null。issues/warnings 条目统一为 `{code, frame_count, detail}`，批次级 frame_count=null。

- `reported_samples` 保留任务中声明的完整样本数；`csv_pairs` 为实际配对键数；`verified_frames` 仅统计摘要相同且五项均一致的帧。
- `verification_status=consistent`：支持的 completed 输入，所有规定检查一致，issues 为空；CLI 0。上下文差异 warnings 允许存在，comparison_basis 必须明确。
- `verification_status=inconsistent`：任务声明、CSV 集合、图片摘要或指标存在差异/无法复核；CLI 1。CSV 集合不一致时 frames=[]、verified_frames=0。
- 有效但非 completed 的同类型任务：`verification_status=not_reviewed`、CLI 2；仅报告原 task_status、run_id 和 `task_not_completed`，counts=null、frames=[]，不分析部分记录、不修改原状态。
- 必需文件缺失/不可读、坏 JSON/CSV、缺字段、类型错误、版本/类型不支持、不安全路径：API 保留 OSError 或抛 ValueError；CLI stderr 明确说明，退出2，stdout为空。缺失 PNG 是逐帧问题，属于 CLI 1；区别于必需的 JSON/CSV 输入缺失。
- 逐帧只捕获 OSError/ValueError/cv2.error 记录 `frame_unverifiable`。MemoryError 与其他未预期异常继续传播；不要吞异常或返回成功。
- 本入口不提供 --output、不创建新报告、不打开摄像头、不导出配对中间文件。输出是否另存由调用方决定，实施者不得覆盖任何历史文件。

建议稳定问题码：`task_sample_count_mismatch`、`task_sample_state_mismatch`、`csv_keys_mismatch`、`image_hash_mismatch`、`metric_mismatch`、`frame_unverifiable`。detail 说明实际差异，不包含质量评分、合格判定或故障诊断。

## 3. 不改变与实施文件范围

允许新增：`src/review_capture.py`、`tests/test_review_capture.py`。
允许更新：本任务状态行及第7/8节；README 新入口说明；能力矩阵新增能力与实际受影响数据。
除此之外不得修改源码、已有测试、AGENTS、依赖、CI、清单、原图、实验产物、冻结证据或历史报告。

不做：新统计算法、图表、质量评分、故障分类、QR集成、部分失败恢复、重连、并发、GUI、Web、数据库、框架或通用审计平台。

## 4. 独立验收条件

| ID | 输入及预先确定的验收条件 | 核验方式 |
| --- | --- | --- |
| R01 | 人工构造4×5 BGR常量100；CSV独立填亮度100.0，其余四项0.0；配对键/PNG摘要正确。单帧全部一致，0退出；五项预期不得由新模块计算 | 新测试与真实 CLI 临时夹具 |
| R02 | 使用第5节 trial-004 基线，逐帧五项字符串对与改动前接口一致，帧1/143，2帧通过 | 真实CLI及基线逐字段比对 |
| R03 | 仅在临时副本对 PNG 无损重编码，更新后的像素相同而文件摘要不同；不更新任务JSON | 指标仍一致、必须出现 image_hash_mismatch、1退出 |
| R04 | 临时副本分别删除PNG、写空PNG/损坏PNG、改一项CSV值；另有一帧正常 | 对应帧标识准确，不一致/无法复核不计verified；正常帧仍检查 |
| R05 | 两份CSV同时删去一个声明帧；或同时混入其他批次；或单侧增加记录 | csv_keys_mismatch，1退出；不能因两个CSV互相配对而通过 |
| R06 | 完整数与samples数矛盾；保存状态非written；另测理论6点但只有2个合法完整样本 | 前两种1退出；最后一种允许一致，不要求补齐理论点数 |
| R07 | 同类型 failed/interrupted 任务 | not_reviewed、2退出，不重算、不恢复、不改原状态 |
| R08 | 缺JSON/CSV、坏格式、错误字段类型、重复帧、重复CSV键、不安全图片路径 | 2退出且无成功JSON；拒绝路径在读取外部文件前发生 |
| R09 | 仅修改临时报告中的运行库版本/两项源码摘要/阈值记录，CSV/PNG保持一致 | 文件和当前算法检查照常完成；warning明确，不误报相机故障、不强制拒绝 |
| R10 | 注入MemoryError；同一对象连续review两次；对API/CLI输出JSON核验 | 原MemoryError传播；两次无计数累积；固定输出与已定义退出码 |
| R11 | 新旧入口在同一临时批次独立调用；对新入口运行前后保存输入文件清单及SHA-256 | 逐帧重算返回值相同；输入无增删改，包括失败路径 |
| R12 | 完整pytest、精确评测闸门；trial-003/004只读CLI冒烟 | 如实记录本轮数量/退出码；闸门与入库期望一致，不refresh |

不以测试数量验收，不要求额外搭建审核系统。反例只修改临时夹具或临时副本；不实际破坏设备、磁盘或内存。

## 5. 基线快照与数据依据

基线提交见文件头，覆盖已跟踪资产。实施前记录 git status，并对本轮会读取的 ignored 目录 trial-003/004 保存文件清单与摘要到仓库外临时证据目录；它是本轮实施前快照，不能补造更早阶段证据。

2026-10-14，在创建本规格前直接调用旧 `compare_frame_metrics()` 得到 trial-004 基线：

- run_id：`0117d23f9da141ab9c124a96b004a762`，2条完整样本。
- 五项按 brightness/dark_ratio/bright_ratio/sharpness/contrast 排列；下列每值都是 `(CSV值, 重算值)` 两侧相同。

| 帧号 | brightness | dark_ratio | bright_ratio | sharpness | contrast |
| --- | --- | --- | --- | --- | --- |
| 1 | 165.9 | 4.5 | 13.0 | 270.5 | 54.8 |
| 143 | 168.9 | 3.9 | 15.3 | 298.4 | 54.6 |

这些是真实既有产物的回归记录，不是场景质量标签。CI 不依赖未入库实机图片：R01等合成夹具放pytest临时目录；R02/R12实机部分在本机独立验收，不让缺失本地图片导致CI失败。

## 6. 技术步骤、风险与验证

1. 实施前核对基线/工作区/本轮文件范围，跑实际完整测试与闸门，记录 ignored 实机产物摘要。
2. 先实现最小读取与组合类，调用既有接口，再接CLI，不调用旧 main() 或解析打印文本。
3. 按R01–R11写独立断言与必要故障注入，不自生成真值；完成R12再更新说明。
4. 审查本轮diff及资产摘要，交回Codex；不自行commit/push或新增功能。

主要风险：文件对应关系一致不等于图像真实或工业合格；必须保留comparison_basis与结论边界。复用接口会重复读取CSV/PNG，120个样本规模先保持简单，不引入缓存或并发；不保证并发改写时读取一致。
回滚方式：本功能未改既有实现；需要撤回时仅撤销本次批准的新增入口/测试及说明增量，不重置或清理其他成果。

拟定核验命令（入口尚未实现）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_review_capture.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py data\reports\timed-capture\trial-003
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py data\reports\timed-capture\trial-004
```

执行环境需要禁止向仓库写测试缓存时，使用 `-B`、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider` 与仓库外 --basetemp。不要在历史目录重定向stdout或生成中间报告。

## 7. 实现记录（Claude Code填）

### 7.1 实际修改文件（本轮只新增源码/测试，未改既有实现）

- 新增 `src/review_capture.py`：`CaptureTaskReviewer(task_dir).review()` 与 CLI `main(argv=None)`，
  支持 `python src\review_capture.py <dir>` 与 `python -m src.review_capture <dir>`。
  仅组合既有 `reconcile_reports()` 与 `compare_frame_metrics()`；不复制指标算法、不解析旧 CLI 打印文本。
- 新增 `tests/test_review_capture.py`：18 项，覆盖 R01–R11，全部在 pytest 临时目录内构造夹具。
- 更新说明：本文件状态行与本节、`README.md` 新入口说明、`docs/stage-34-project-capability-matrix.md` 受影响内容。

未修改：既有采集、QR、指标算法、旧测试、依赖、CI、数据集、冻结证据、原图、历史报告。

### 7.2 实施前基线（实测）

- `git rev-parse HEAD` = `dd97998df18b2974a3530eae4d3e7e9cf41da33f`，与规格一致；
  `git status --porcelain` 仅 `?? docs/tasks/phase-4.5-capture-review.md`。
- `.venv\Scripts\python.exe -m pytest -q` → `454 passed`，exit 0。
- `.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py` → 两组 split 与入库期望完全一致，exit 0。
- 实机产物前置摘要（保存在**仓库外**临时目录）：`trial-003` 9 个文件、`trial-004` 5 个文件的 SHA-256 清单。

### 7.3 本轮命令与退出码

| 命令 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | `472 passed`，exit 0（454 + 新增 18） |
| `... -B -p no:cacheprovider --basetemp=<仓库外>` | `472 passed`，exit 0（未向仓库写测试缓存） |
| `... -X utf8 tools\check_evaluation_expectations.py` | 闸门通过，exit 0 |
| `... -X utf8 src\review_capture.py data\reports\timed-capture\trial-003` | exit 0，`consistent`，6 帧全部 verified |
| `... -X utf8 src\review_capture.py data\reports\timed-capture\trial-004` | exit 0，`consistent`，2 帧全部 verified |
| `... -X utf8 -m src.review_capture data\reports\timed-capture\trial-004` | exit 0，与脚本调用输出逐字节相同 |

### 7.4 逐条验收（R01–R12）

| ID | 结果 | 证据 |
| --- | --- | --- |
| R01 | 通过 | 合成 4×5 常量 100；CSV 独立填亮度 100.0、其余 0.0；`EXPECTED_METRICS` 为人工推导常量（不由新模块计算），单帧一致、CLI 0。`test_r01_*` |
| R02 | 通过 | 新入口逐帧五项字符串对与直接调用 `compare_frame_metrics()` 一致（合成夹具，CI 安全）；实机 trial-004 与第 5 节基线逐字段一致（帧 1 = 165.9/4.5/13.0/270.5/54.8，帧 143 = 168.9/3.9/15.3/298.4/54.6），2 帧通过。`test_r02_*` + 7.3 冒烟 |
| R03 | 通过 | 临时副本以无压缩重编码 PNG（字节不同、像素相同），指标仍一致但出现 `image_hash_mismatch`，exit 1。`test_r03_*` |
| R04 | 通过 | 删图/空图/坏图/改一项 CSV，另一帧仍检查；逐帧码准确，verified=0。`test_r04_*` |
| R05 | 通过 | 双侧删帧、双侧混入其他批次、单侧加记录三种均 `csv_keys_mismatch`，exit 1，frames=[]。`test_r05_*` |
| R06 | 通过 | 计数矛盾、保存状态非 written 各 exit 1；理论 6 点仅 2 样本 → 一致、exit 0，不要求补齐理论点数。`test_r06_*` |
| R07 | 通过 | failed/interrupted → `not_reviewed`、exit 2，counts=null、frames=[]，输入摘要不变。`test_r07_*` |
| R08 | 通过 | 缺 JSON/CSV、坏 JSON、NaN、类型错、重复帧、重复 CSV 键、不安全图片路径 → exit 2 且 stdout 为空；路径在读取外部文件前拒绝。`test_r08_*` |
| R09 | 通过 | 改运行库版本、两项源码摘要、阈值记录后，文件与当前算法检查照常完成，仅 `measurement_context_differs` warning，exit 0，不误报相机故障。`test_r09_*` |
| R10 | 通过 | 注入 MemoryError 原样传播；同一对象两次 `review()` 结果一致（无计数累积）；输出可 `allow_nan=False` 序列化且 CLI stdout 为单份 JSON。`test_r10_*` |
| R11 | 通过 | 新旧入口在同一临时批次独立调用，逐帧重算返回值相同；成功与失败路径前后输入文件清单与 SHA-256 均无增删改。`test_r11_*` |
| R12 | 通过 | 完整 pytest 472、闸门 exit 0、trial-003/004 只读 CLI 冒烟 exit 0；未 refresh 期望。见 7.3 |

### 7.5 资产摘要比较

`trial-003`、`trial-004` 全部文件在本轮实施与全部冒烟前后 SHA-256 **完全一致**（与 7.2 前置清单逐行 diff 无差异）；
仓库 `git status --porcelain` 仅出现本轮三个新增未跟踪文件。

### 7.6 实现口径与限制

- 五项指标始终是「按当前算法与当前阈值重算」，`comparison_basis` 固定为 `current_algorithm_one_decimal`。
  上下文（`metric_config`、运行库版本、`metrics.py`/`analysis_config.py` 摘要）缺失或不同只产生
  `measurement_context_unavailable` / `measurement_context_differs` warning，不阻断、不归因、不建版本闸门。
- 非 completed 任务只返回 `run_id`、原 `task_status` 与 `task_not_completed`；`counts=null`、`frames=[]`。
  为保持固定结构，其 `comparison_basis` 仍为该字符串，但没有任何逐帧比较发生。
- 逐帧只捕获 `OSError`/`ValueError`/`cv2.error` 记为 `frame_unverifiable`；`MemoryError` 与其他未预期异常继续传播。
- R08 中「符号链接逃出任务目录」一项依赖运行环境支持创建符号链接（本机实测可创建，已实际执行未跳过）；
  仅当环境不支持时该项 `pytest.skip`，其余断言不受影响。
- 未做：新统计/评分/故障判定、恢复、并发、GUI/服务、`--output`、缓存。120 样本规模先保持简单，
  复用接口会重复读取 CSV/PNG；不保证并发改写输入时的读取一致性。
- 失败与未完成项：无测试失败；无未完成项。

### 7.7 修复轮记录（2026-10-14，Codex 反例驱动）

7.1–7.6 的首轮自测记录**保留不改**；以下是修复经过，不把首次失败改写为首次通过。

**Codex 独立反例文件**（只读使用，未修改）：
`C:\Users\zex\.codex\visualizations\2026\10\12\01a12ed0-11d7-7d13-be87-0c4bd858475b\phase45-review\test_independent_contract.py`

**修复前复跑该反例文件**（仓库外 `--rootdir/--confcutdir/--basetemp`，`-B`、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`）：
`3 failed, 9 passed`，exit 1。失败项即三处声明反例：

1. `test_declared_count_preserved_in_all_return_paths[False]` —— 正常返回分支 `reported_samples` 用了样本数而非声明值；
2. `test_declared_count_preserved_in_all_return_paths[True]` —— CSV 集合不一致提前返回分支同样问题；
3. `test_malformed_csv_uses_documented_value_error_contract` —— 坏 CSV 的 `csv.Error` 直接传播，未转为 `ValueError`。

**修复内容**：

| # | 位置 | 修复 |
| --- | --- | --- |
| 1 | `src/review_capture.py` `review()` 的两个返回分支 | `reported_samples` 改为保留 `counts.samples_completed` 声明值（原为 `len(samples)`）；`csv_pairs` 仍为实际配对键数 |
| 2 | `src/review_capture.py` 新增 `_reconcile_reports()` | 只在新增组合层把 `reconcile_reports` 的 `csv.Error` 转成 `ValueError`（`raise ... from error` 保留原因）；**未改** `check_reports.py`；**未**捕获或转换 `MemoryError` 及其他未预期异常；CLI 仍退出 2、stderr 说明原因、stdout 为空 |
| 3 | `tests/test_review_capture.py` | 拆分并修正符号链接用例：**先恢复规范图片名再构造目录外链接**，确保实际走到路径解析分支；环境不支持链接时如实 `pytest.skip`（不声称通过、不改系统设置）；新增「注入 `Path.resolve`」流程探针并注明**不能替代**真实符号链接测试；新增「缺失图与正常图并存」用例（坏帧报错、正常帧仍复核并计入 `verified_frames`）；新增 `reported_samples` 保留声明值（两个分支）与坏 CSV → `ValueError` 用例 |

**修复后复跑同一反例文件**：`12 passed`，exit 0。

**本轮项目测试**：`tests/test_review_capture.py` 由 18 项增至 **24 项**（净增 6；未删除、弱化或修改任何原有独立预期）。
完整 pytest：**`478 passed`**（failed 0、skipped 0）；评测闸门 exit 0（未 `--refresh`）；
`trial-003`（6 帧）、`trial-004`（2 帧）只读 CLI 冒烟均 exit 0、`consistent`。
实机产物在本轮修复前后 SHA-256 逐行一致（见 7.5 的前置快照比对）。

**范围约束**：未修改第 1–6 节验收契约、第 8 节独立验收区与第 9 节用户观察；
未新增统计、评分、故障判定、恢复、缓存、并发或框架；`not_reviewed` 的 `comparison_basis` 保持现状。
本轮跳过项：符号链接用例**未跳过**（本机可创建链接，实际执行）；无其他跳过。

## 8. 验证记录（Codex填）

### 8.1 独立复验与 DeepSeek 复核（2026-10-15）

依据第 1–6 节的 R01–R12，不修改验收条件。Codex 实际复跑 DeepSeek 套件、既有独立反例、项目专项、全量回归、精确评测闸门及真实 CLI；详见 [本地复验记录](phase-4.5-verification-2026-10-15.md)。

| 检查 | 实际结果 |
| --- | --- |
| DeepSeek 独立套件 | 49 passed、5 skipped，exit 0 |
| Codex 独立反例 | 8 passed、4 skipped，exit 0；此前三个失败反例均通过 |
| 项目专项 | 23 passed、1 skipped，exit 0 |
| 完整 pytest | 477 passed、1 skipped，25.65 秒，exit 0 |
| 精确评测闸门 | 两组与入库期望完全一致，exit 0；未 refresh |
| 实机产物只读冒烟 | trial-003 6 帧、trial-004 2 帧，均 consistent；逐帧五项值与旧接口对照一致 |
| 模块入口 | 与脚本入口结果一致，exit 0 |
| 真实 junction 逃逸探针 | JSON、两份 CSV、图片四条规范路径均拒绝逃逸，4 PASS / 0 FAIL / 0 SKIP |

R01–R07、R09–R12 的已执行检查符合规格。R08 的字段、坏格式、规范名称与路径解析注入检查通过；真实符号链接部分未验证，不能将 R08 的全部路径测试写成已完成。所有跳过项均因 WinError 1314；独立套件数量不并入项目测试总数。

本次检查前后 292 个项目文件的文件集合与 SHA-256 一致，Git 状态一致。该比较发生在新增本地复验 Markdown 及本次交付收尾之前；不是对随后文档改动宣称无变化。

### 8.2 边界判断与交付范围

- 原声明计数、坏 CSV 异常契约与测试覆盖问题已修复，独立反例证实有效；本轮未发现要求继续修改源码的问题。
- `csv_pairs` 是两份 CSV 彼此配对的键数。集合不一致时，这个数字不代表与任务声明匹配的帧数，已有 `csv_keys_mismatch` 明确标识问题；不改字段语义。
- 逐帧 `csv.Error` 在当前静态输入流程未复现；并发改写输入属于声明范围外，不概括为普遍不可达。
- 2026-10-15 重新尝试沙箱内与沙箱外普通用户进程，均无法创建真实符号链接（WinError 1314）。未提升管理员权限、未改系统设置。junction 证据不替代符号链接测试。
- 没有独立 build、lint 或类型检查配置；不临时引入框架。
- 本轮交付限于入口、对应测试、任务文档、README、能力矩阵及本地复验记录六个文件。源码与测试保持已复验字节，原图、历史报告、数据集、冻结期望、依赖和 CI 配置不变。
- `dd97998` 的远程 454 项记录是历史基线。Phase 4.5 的对应远程 CI 尚待执行，结果必须绑定实际提交，不预填成功。

### 8.3 交付前最终本地复验（2026-10-15）

本轮文档收尾后，完整 pytest 为 477 passed、1 skipped（29.51 秒），评测闸门与 trial-003 / trial-004 CLI 均 exit 0。源码、测试及数据资产未改；比较基线包含 293 个文件，有意改动限于收尾文档，详见本地复验记录的后续追加部分。远程 main 只读核验仍为 dd97998，可正常快进交付。

### 8.4 版本交付与远程 CI（2026-10-15）

- 功能提交：`66b05d655e7045aab71c5594723baf3684e8f379`（`feat(capture): add verified offline capture review entrypoint`），六个交付文件已正常推送 origin/main，无强推。
- 精确对应功能提交的 [GitHub Actions 38686222004](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/runs/38686222004)：event=push，runner=ubuntu-latest，结论 **success**。
- Run tests 日志实际为 **478 passed in 8.93s**，没有 skipped；两组精确评测闸门均与入库期望完全一致。
- 项目中此前在 Windows 跳过的图片符号链接用例已随完整套件在 Linux 执行通过；这补齐该项目用例的跨环境验证，不表示本机 Windows 权限已改变。
- 仓库外独立套件的四类符号链接参数化用例没有上传到 CI，仍保留 Windows 环境未验证记录；不能把项目中的一个图片用例扩大为所有链接类型和路径的全覆盖。
- 8.1–8.3 的本地结果与待交付状态属于执行当时记录，保留历史，不改写成首次即远程通过。
- 本次后续提交只补交付与 CI 文档证据，源码、测试、依赖和工作流不变。后续文档提交自身的远程运行以对应 Actions 为准。

### 8.5 补齐固定 JSON/CSV 的真实符号链接覆盖

R08 原本已要求固定 JSON/CSV 路径不得通过链接逃出目录。此前 CI 中只有图片真实符号链接用例；本轮为三个固定输入新增参数化用例，不增加产品行为、不改验收标准或 CI 配置。

新增 `test_r08_symlinked_fixed_input_escaping_dir_is_rejected_before_read` 覆盖任务 JSON、质量 CSV、颜色 CSV。外部文件复制有效内容，避免格式错误掩盖路径缺陷；用 `Path.open` 守卫确保拒绝发生在读取外部文件之前。原图片用例、注入探针与全部既有断言保留。

项目现在收集 481 项（原 478＋3），Phase 4.5 专项 27 项（原 24＋3）。当前 Windows 专项实际为 23 passed、4 skipped（1.47 秒），skip 均 WinError 1314。完整回归实际为 **477 passed、4 skipped（26.92 秒）**，exit 0；两组精确评测闸门通过，6＋2 帧 CLI 冒烟仍 consistent。对应提交的 Linux CI 待核验，不预填成功；8.4 的 478 项是原功能提交结果。

## 9. 用户观察

保留给用户，不由执行者填写。
