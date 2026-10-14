# Phase 4.1：基于证据的图像质量测量模块任务规格

- 日期：2026-10-12
- 状态：方案已审核通过；用户已于 2026-10-12 授权实施，代码、测试与文档已按本规格完成，A01–A16 逐条验收见第 7、8 节。
- 规格编写阶段授权（历史记录）：仅编写任务规格，不修改代码、测试、配置、历史报告或样本。
- 项目定位：摄像头图像质量分析与视觉算法可靠性验证平台；QR 是当前验证对象。
- 本规格是后续分析、实施和验证共同使用的输入。测试不得反向定义或改写验收条件。

## 1. 前提核验（Step 0）

| 检查 | 证据 | 结论 |
| --- | --- | --- |
| 基础亮度是否存在 | `src/metrics.py:27`：灰度均值实现已存在 | 复用，不重新实现 |
| 基础对比度是否存在 | `src/metrics.py:50`：灰度总体标准差实现已存在 | 复用，不重新实现 |
| 基础清晰度是否存在 | `src/metrics.py:64`：灰度拉普拉斯方差实现已存在 | 复用，不重新实现 |
| 基础指标是否已有测试 | `tests/test_metrics.py:58`、`:78`、`:96`：亮度、对比度、清晰度测试 | 已覆盖基础指标，但不等于覆盖新模块契约 |
| 是否已有 ROI 约定 | `src/label_analysis.py:24`：xywh、右下边界不包含、越界拒绝 | 保持坐标语义，不改 QR 模块 |
| 是否已有报告中的指标 | `src/analyze_image.py:157`：组合基础指标；`:193`：现有单图报告 | 已存在，不重新设计现有报告 |
| 新模块是否不存在 | `src/quality_analysis.py:135`：工作区已有 `analyze_quality` 草稿，且为未跟踪文件 | 已有草稿；未执行验收，不得宣称已实现或已通过 |
| 新模块是否已有测试 | 本次项目内文件枚举及 `Test-Path tests/test_quality_analysis.py`（False）；既有 `tests/test_metrics.py:17` 起只覆盖基础函数 | 独立质量分析契约测试确认缺失 |

**前提核验结论：确认缺失的是按本规格完成验收的独立模块与验证证据。**
基础指标已存在，新模块已有未验收草稿；后续应先核对草稿，仅补齐差异，禁止重复建设。
本次不更改该草稿，也不依据草稿行为制定期望值。

## 2. 目标

提供 `analyze_quality(image, roi=None)`，返回 ROI 或整图的清晰度、亮度、对比度、
空间亮度分布，以及结构化测量限制。输出是测量事实，不是质量评分或故障判断。

### 2.1 范围

1. ROI 清晰度：复用已有灰度拉普拉斯方差。
2. ROI 亮度：灰度均值。
3. ROI 对比度：灰度总体标准差。
4. 亮度均衡：固定 4×4 分块的均值分布、均值范围及总体标准差。
5. 输入校验、适用性、严格 JSON 兼容、非破坏性及独立验收。

### 2.2 不纳入本任务

- 噪声估计、模糊分类、曝光异常、光照故障、合格判定和故障归因。
- 综合分数、百分制质量分、未经标定的质量阈值。
- QR 参数、解码、候选选择、真值核对或退出码变更。
- CLI 接入、批量入口、现有报告接入、相机参数控制。
- 机器学习、YOLO、深度学习、GUI、Web 服务及大规模重构。

## 3. 不改变（回归边界）

- `src/metrics.py` 的现有实现、字段语义与基础算法定义。
- 现有 QR 整图、人工 ROI、降采样、歧义/冲突、错误分类及真值比较。
- 现有 CLI 默认行为、JSON 版本与字段、CSV 格式和输出不覆盖策略。
- 合成数据集、清单、独立答案和评测期望；不生成样本、不运行 `--refresh`。
- `photo/`、`data/samples/` 原图及历史报告。
- 现有测试：不删除、跳过或弱化。

本阶段的新模块独立调用，不导入 QR 模块，不接入现有产品入口；不新增第三方依赖。

## 4. 验收条件（外部可核验）

### 4.1 核验命令约定

以下命令从项目根执行。`Q <selector>` 是文档中的简写，不是新脚本或产品命令，展开为：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_quality_analysis.py -k '<selector>'
```

表中给出的 `test_*` 是后续必须实现的验收用例名称，不表示目前已有这些用例。
本次仅实测了第 5 节的旧指标基线，尚未执行以下验收。

### 4.2 固定验收项

| ID | 输入或核验对象 | 通过条件；不满足即失败 | 核验命令 |
| --- | --- | --- | --- |
| A01 | 8×8 全 128 灰度图 | brightness=128、contrast=0、sharpness=0；16 块均值全为 128，mean_range=0、mean_std=0；valid=true、reasons=[] | `Q test_constant_image_oracle` |
| A02 | 8×8 左四列 40、右四列 120 | brightness=80、contrast=40；按行排序每行块均值为 [40,40,120,120]；mean_range=80、mean_std=40 | `Q test_two_level_image_oracle` |
| A03 | 5×5 全零，仅中心像素 100 | brightness=4、contrast=sqrt(384)、sharpness=8000；不得用新模块输出生成期望 | `Q test_impulse_image_oracle` |
| A04 | 第 5 节的三份固定输入 | 三个基础指标逐字段与改动前基线一致：brightness/contrast/sharpness；不使用当前新模块重新生成基线 | `Q test_prechange_metrics_baseline` |
| A05 | 在背景中嵌入已知 ROI，修改 ROI 外像素 | ROI 内四项测量保持一致；所有块坐标正确指向原输入数组；右/下边界不包含 | `Q test_roi_isolation_and_coordinates` |
| A06 | 5×7 非整除区域，以及偏移后的同尺寸 ROI | 每像素恰好覆盖一次；16 块非空、无重叠；面积和为 35；行高 [2,1,1,1]、列宽 [2,2,2,1]；块均值按固定像素独立手算核验 | `Q test_nondivisible_grid_oracle` |
| A07 | 1×1、2×2、3×3、4×4、细长区域 | 严格符合第 6 节小区域契约；不可计算项为 null、不可伪造为 0；原因码和 valid 一致 | `Q test_small_region_contract` |
| A08 | 非数组、空图、错误 dtype/维度/通道 | 抛出 QualityAnalysisError，code=invalid_image；不得返回成功结构 | `Q test_invalid_images` |
| A09 | 浮点/布尔/负数/零宽高/越界/错误长度 ROI | 抛出 QualityAnalysisError，code=invalid_roi；合法贴边 ROI 正常接受；不得自动裁剪或补边 | `Q test_roi_validation_boundaries` |
| A10 | 原数组、只读数组、非连续视图和对应连续副本 | 输入 dtype/shape/像素保持不变；同内容测量一致；只读输入正常接受 | `Q test_input_preservation_and_views` |
| A11 | 灰度图及复制到 B/G/R 的同值三通道图 | 四项结果一致；另用预先固定的纯蓝 BGR 期望验证通道顺序，不能误当 RGB | `Q test_grayscale_and_bgr_contract` |
| A12 | 正常、常量、小区域三类输出 | 顶层及各字段符合第 6 节契约；所有数值为 Python 原生类型；`json.dumps(result, allow_nan=False)` 成功；原因码和提示顺序稳定 | `Q test_output_schema_and_serialization` |
| A13 | 常量图、黑白图案、渐变图 | 不出现评分/故障/合格字段；不因块间差异非零产生警告；warning 类型及 evidence 只能描述规定的事实与限制 | `Q test_measurement_only_warnings` |
| A14 | 第 5 节现有原图、答案、报告、清单、期望与草稿保护 | 本次规格更新保持全部原样；后续实施只允许修改明确批准的文件，原图/答案/历史报告/回归数据仍须 SHA-256 一致 | 规格更新：`Get-FileHash src/quality_analysis.py -Algorithm SHA256`；实施验证：实施前后对受保护数据执行 `Get-FileHash -Algorithm SHA256` 并用 `Compare-Object` 比较清单 |
| A15 | 既有行为 | 完整 pytest 通过；原合成期望精确一致，未刷新期望；不接受仅以新用例通过为完成依据 | `.\.venv\Scripts\python.exe -m pytest -q`；`.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py` |
| A16 | 实际图片运行冒烟 | 用现有读取函数加载固定 PNG，独立调用新模块，核对区域/结果类型并严格 JSON 序列化；图片调用前后 SHA-256 一致 | `Q test_real_png_smoke` |

### 4.3 oracle 与数值比较规则

- A01–A03 的主 oracle 来自固定像素和数学定义；A04 来自本次改动前的现有代码输出。
- 脉冲图的四邻域拉普拉斯响应为中心 -400、四个邻点各 100，其余 0；
  均值为 0，方差为 (400² + 4×100²)/25 = 8000。
- 该图原灰度均值为 4，方差为 10000/25 - 4² = 384。
- 整数可精确表示的已知结果精确比较；sqrt(384) 等浮点结果使用预先固定的
  `rel=1e-12, abs=1e-12` 数值误差界。这不是质量阈值，不适用于放宽 QR 期望。
- 非整除网格用固定数组、手算块范围及像素覆盖计数核验，不调用待测分块辅助函数生成期望。
- 与现有指标函数一致性只能作为补充检查，不能替代数学 oracle。
- 固定测试证据可以由 pytest 执行，但通过条件不得从被测实现推导或刷新。

## 5. 基线快照

### 5.1 工作区与保护对象

- Git 基线：`afdca8f43b66dcb8eca2b6280aebefd6215e4f03`。
- 规格更新前 `git status --short`：仅 `?? src/quality_analysis.py`。
- 已有未跟踪草稿 SHA-256：
  `5f6d074d06cea98b9ddffe78a61a1b80c821cf9aca7ef5d62be60fdc7a6bbb06`。
- 本次不修改草稿；后续实施前重新检查其状态，不能假设它仍与此快照相同。
- 现有测试规模引用 `docs/stage-34-project-capability-matrix.md` 的历史记录；
  本次没有重跑完整测试，不能将记录写成本轮实测。
- 后续代码修改前，应重新运行现有测试并记录结果，保存受保护数据哈希清单。
  原图、答案、历史报告和已入库评测清单/期望都属于保护对象。
  哈希快照只保存路径与摘要，不复制图片或整个仓库。

### 5.2 改动前基础指标输出（本次实测）

使用项目 `.venv`、`-B -X utf8` 调用现有 `src.metrics`，未导入新草稿、未写入文件：

```json
{
  "constant128": {"brightness": 128.0, "contrast": 0.0, "sharpness": 0.0},
  "left40_right120": {"brightness": 80.0, "contrast": 40.0, "sharpness": 1600.0},
  "center_impulse100": {"brightness": 4.0, "contrast": 19.595917942265423, "sharpness": 8000.0}
}
```

这份快照与独立数学期望共同构成外部 oracle；不得由新模块重生成覆盖。
基线复核可使用 A04 命令，实施前须将这些固定值作为常量写入对应验收用例。

## 6. 分析区：接口、数据结构、影响与风险

### 6.1 输入和错误契约

- 函数：`analyze_quality(image, roi=None)`。
- image 为非空 NumPy uint8 二维灰度或三维 BGR 三通道数组；不接受其他 dtype、
  alpha、RGB 语义声明或自动缩放。BGR 转灰度沿用现有 OpenCV 转换。
- roi 为 None，或 list/tuple 的四个 Python 整数；不接受 bool、浮点数。
- `x,y >= 0`，`width,height > 0`，完整处于输入内；坐标为传入数组坐标。
- 文件读取、EXIF 方向、alpha 合成由调用方负责，模块不重复预处理。
- 非法输入抛 `QualityAnalysisError(ValueError)`，code 为 invalid_image 或 invalid_roi。
- 运行库错误/资源耗尽不能包装成“质量不好”或静默成功。
- 不修改数组或其底层存储，不读写文件、不联网、不打开相机、不调用 QR。

### 6.2 输出契约

顶层恰好三个字段：`metrics`、`warnings`、`applicability`。

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| metrics.sharpness | float 或 null | 灰度拉普拉斯方差，复用现有实现；不可计算时 null |
| metrics.brightness | float | 分析区域的灰度均值，范围 0–255 |
| metrics.contrast | float | 分析区域的灰度总体标准差，ddof=0 |
| metrics.brightness_uniformity | object 或 null | 第 6.3 节固定网格测量 |
| warnings | list[object] | 每项恰好 type、evidence、severity；固定顺序见第 6.5 节 |
| applicability.valid | bool | 四项测量是否都满足本接口空间条件 |
| applicability.reasons | list[str] | 不可计算项目的稳定原因码；无缺项时 [] |

没有评分、合格、故障类别、failure_reason 或自动重拍动作。
所有数值有限、使用 Python 原生 int/float；缺失只能用 null，禁止 NaN/Infinity。

### 6.3 brightness_uniformity

- 对分析区域固定切为 4 行 × 4 列，不缩放、不丢边、不重叠。
- 每个方向令长度 n = 4q + r，前 r 段长度 q+1，余下段长度 q。
  这是明确的采样契约，不是由草稿输出生成的期望。
- `grid_shape` 为 [4,4]。
- `blocks` 为按行优先排列的 16 个对象，各含 x、y、width、height、mean。
  x/y 为原输入数组坐标；其余尺寸为像素；mean 为该块灰度均值。
- `mean_range` 为块均值 max-min，单位为灰度值。
- `mean_std` 为 16 个块均值的总体标准差，各块等权；非等面积时不解释为全 ROI 的标准差。
- 面积加权块均值应与 ROI 灰度均值一致，可作为独立一致性检查。
- 固定网格不能自动保证不同场景/尺寸可比，不能保证发现块内部的小暗点或局部变化。
- 块间差异可能来自物体、图案、颜色或阴影，不能直接称为光照故障。

### 6.4 小区域与 applicability

| 分析区域宽高 | brightness / contrast | sharpness | brightness_uniformity | valid |
| --- | --- | --- | --- | --- |
| 任一边 <3 | 计算 | null | null | false |
| 两边 >=3，任一边 <4 | 计算 | 计算 | null | false |
| 两边 >=4 | 计算 | 计算 | 计算 | true |

reasons 按以下顺序列出确实不可计算的项目：

1. `sharpness_insufficient_dimensions`
2. `uniformity_insufficient_dimensions`

3×3 与 4×4 是本接口的测量空间条件，不是经实验标定的光学有效性标准。
valid=true 不代表清晰、曝光正常、适合识读、故障已定位或工业合格。

### 6.5 warnings：落实审核意见

**正常的块间亮度差异属于 metrics，不因 mean_range > 0 产生警告。**
首版允许的提示按以下顺序输出：

| type | 触发条件 | evidence 必须包含 | severity |
| --- | --- | --- | --- |
| measurement_scope | 始终 | region（kind,x,y,width,height）、scene_calibration="none"、limitations（内容相关、固定网格分辨能力、跨场景可比性限制） | info |
| constant_region | 分析区域 min_gray == max_gray | min_gray、max_gray；只说明区域灰度恒定 | info |
| insufficient_spatial_support | 存在不可计算指标 | region、unavailable（原因码列表）、required_minimum_side（sharpness=3、brightness_uniformity=4） | warning |

severity 表示测量限制的重要性，不表示质量等级或故障严重程度。
不新增 block_brightness_variation、small_blocks 或其他阈值提示；如需扩展须单独审核。
草稿中存在额外提示和跨尺寸可比性措辞，当前不修改，后续应按本规格核对差异。

### 6.6 与现有报告兼容方式

- 本任务只交付独立模块与验证，不改既有入口、历史 JSON 或报告默认字段。
- 未来接入时可把完整结果放入独立 `quality_analysis` 字段，但接入方案需另行审核。
- 未来必须记录所用输入/区域、源码与配置版本，不能用新结果改写历史 metrics。
- QR 的状态、候选选择、真值与耗时口径保持原契约；质量测量不筛除失败样本。

### 6.7 影响文件与实施顺序（待确认执行）

| 文件 | 计划 |
| --- | --- |
| src/quality_analysis.py | 已有未验收草稿；先核对，再仅补齐规格差异，复用基础指标 |
| tests/test_quality_analysis.py | 新增与 A01–A16 对应的独立验收测试 |
| docs/stage-35-evidence-based-quality-analysis.md | 实施完成后新增设计与验证记录；创建时重新核对最大文档编号 |
| README.md | 实施完成后说明新模块能力与不可声称的边界 |
| docs/stage-34-project-capability-matrix.md | 实测后更新能力行及受影响数字，不预填成功结论 |

实施顺序：检查最新工作区和草稿 → 固定 oracle 与现有回归基线 → 补齐模块差异 →
逐条验收与反例检查 → 完整回归和真实 PNG 冒烟 → 更新文档 → 审查 diff。
本次只新增本任务规格，表中后续改动尚未执行。

### 6.8 风险、检测与回退

| 风险 | 检测方式 | 回退方式 |
| --- | --- | --- |
| 内容差异被解释为照明故障 | A13 黑白图案/渐变反例及固定 warning 白名单 | 停用新增解释，保留原始测量；修正本次增量 |
| 测试仅复述实现 | A01–A04 的手算与改动前基线；不调用待测 helper 生成 oracle | 不放宽期望，回到公式定位实现差异 |
| ROI 外像素影响清晰度边界 | A05 修改周边像素、连续副本与视图对照 | 修正新增模块的区域处理，不改旧指标定义 |
| 误覆盖其他人的未跟踪草稿 | 实施前重读 status 与文件哈希，审查差异 | 保留已有内容；仅回退本次明确改动，不执行清理或硬重置 |
| 影响历史行为或数据 | A14 哈希保护、A15 现有回归、最终 diff | 仅回退新增模块/测试/文档增量，历史数据不改写 |

依赖：现有 NumPy、OpenCV、pytest 和项目 `.venv`；不安装新包，不申请提权。
人工依赖：用户确认本次更新后的规格后才能开始代码修改。

## 7. 实现记录

- 实施日期：2026-10-12；项目 `.venv`，未安装新依赖，未提交/推送。
- 实施前状态核对：`git status --short` 仅 `?? docs/tasks/phase-4.1-quality-analysis.md` 与 `?? src/quality_analysis.py`；
  HEAD = `afdca8f43b66dcb8eca2b6280aebefd6215e4f03`；草稿 SHA-256 =
  `5f6d074d06cea98b9ddffe78a61a1b80c821cf9aca7ef5d62be60fdc7a6bbb06`，与第 5.1 节快照一致。
- 实施前基线：`pytest -q` → **285 passed**（与第 5.1 节引用一致），本机实测 14.69 s。
- 保留已有工作：`src/quality_analysis.py` **不是重写**，仅在草稿基础上补齐本规格差异。

### 7.1 改动文件

| 文件 | 改动 |
| --- | --- |
| `src/quality_analysis.py` | 补齐规格 §6.5：`measurement_scope.evidence` 改用 `limitations`；`constant_region` 只保留 `min_gray`/`max_gray`；**删除** `small_blocks` 警告与 `SMALL_BLOCK_SIDE`；docstring 去掉「不同尺寸因此可比」措辞；清理 `_to_gray` 一行重复维度校验 |
| `tests/test_quality_analysis.py` | 新增，14 个用例覆盖 A01–A16（A14/A15 为哈希与回归核验，用命令执行） |
| `docs/stage-35-evidence-based-quality-analysis.md` | 新增设计与验证记录（文档序号 35 = 现有最大 34 + 1） |
| `README.md` | 新增「独立质量测量模块」小节与不可声称边界；测试数 285→299、21→22 个测试文件；目录结构补充 `quality_analysis.py` |
| `docs/stage-34-project-capability-matrix.md` | 新增能力行 8；第 0 节测试数与文档数更新；第 2 节标注分项未重算 |
| `docs/tasks/phase-4.1-quality-analysis.md` | 本文件第 4/5 节**未改动**；仅回填第 7、8 节与状态行 |

**未改动**：`src/metrics.py`、`src/analyze_image.py`、`src/label_analysis.py`、`src/analyze_label.py`、
QR/评测链路、CLI、合成数据集与清单、`photo/` 与 `data/samples/` 原图、历史报告、`AGENTS.md`。

### 7.2 执行结果

| 命令 | 结果 |
| --- | --- |
| `python -m pytest -q tests/test_quality_analysis.py` | **14 passed**（0.18 s） |
| `python -m pytest -q` | **299 passed**（19.66 s；285 基线 + 14 新增，无失败/跳过） |
| `python -X utf8 tools/check_evaluation_expectations.py` | 两个 split 均「与入库期望完全一致」，闸门通过；**未运行 `--refresh`** |
| 保护对象 SHA-256 比对 | `photo/`、合成 46 图与答案、3 份清单、`stage2-known-qr.png`、`src/metrics.py` 等实施前后**全部一致** |

### 7.3 反例检查

主动构造 4×4 常量图、5×5 渐变图、1×1/1×12/1×10 ROI、贴边 ROI、零尺寸与溢出 ROI、修改 ROI 外全部像素等输入；
结果均符合规格（详见 `docs/stage-35-*` 第 4.1 节）。**尝试后未找到反例。**

## 8. 验证记录

### 本次规格更新核验

- 已读取项目规则、任务格式、相关基础实现与现有测试证据。
- 已通过项目 `.venv`、禁写字节码的方式获得第 5.2 节旧指标基线，退出码 0。
- 代码、测试、配置和数据修改：无。
- 完整 pytest、评测闸门、A01–A16：本次未执行；仅更新文档，不声称实现已通过。
- 未运行新草稿，也未对其做动态反例验证；不能写成“没找到反例”。
- 文档写入后的 diff/status、草稿哈希保持核验结果在本次会话报告中记录。

### 实施后逐条验收（A01–A16）

核验命令：`.\.venv\Scripts\python.exe -m pytest -q tests/test_quality_analysis.py -k '<selector>'`，
外加第 4.2 节给出的完整 pytest 与闸门命令。**期望值与验收条件均未修改或放宽。**

| ID | 用例 / 核验 | 结论 | 实际输出与证据 |
| --- | --- | --- | --- |
| A01 | `test_constant_image_oracle` | 通过 | brightness=128.0、contrast=0.0、sharpness=0.0；16 块均值全 128.0；mean_range=0.0、mean_std=0.0；`applicability == {"valid": True, "reasons": []}` |
| A02 | `test_two_level_image_oracle` | 通过 | brightness=80.0、contrast=40.0；每行块均值 `[40,40,120,120]`；mean_range=80.0、mean_std=40.0 |
| A03 | `test_impulse_image_oracle` | 通过 | brightness=4.0；contrast=√384（`approx(rel=1e-12, abs=1e-12)`）；sharpness=8000.0（精确） |
| A04 | `test_prechange_metrics_baseline` | 通过 | 三份固定输入对 `src.metrics` 逐字段一致：`{128.0,0.0,0.0}`、`{80.0,40.0,1600.0}`、`{4.0,19.595917942265423,8000.0}`（oracle = 第 5.2 节常量，非新模块重生成） |
| A05 | `test_roi_isolation_and_coordinates` | 通过 | ROI(2,2,6,6) 内 brightness=100.0、contrast=0.0、sharpness=0.0；改 ROI 外全部像素后 `metrics` 逐字段相等；块坐标 x/y ∈ [2,8)，右边界外第 8 列与下边界外第 8 行未被包含 |
| A06 | `test_nondivisible_grid_oracle` | 通过 | 5×7：行高 `[2,1,1,1]`、列宽 `[2,2,2,1]`；16 块均非空；覆盖计数全为 1；面积和 35；块均值与固定数组手算一致；偏移 ROI(4,3,7,5) 的 x/y 与均值同步正确 |
| A07 | `test_small_region_contract` | 通过 | 1×1/2×2/1×10/10×1 → sharpness 与 uniformity 均 `None`；3×3/3×10/10×3 → sharpness 计算、uniformity `None`；4×4/4×10 → 全部计算；reasons 顺序与 valid 一致；不可计算项为 `None` 而非 0 |
| A08 | `test_invalid_images` | 通过 | 12 类非法输入均抛 `QualityAnalysisError`，`code == "invalid_image"`，且是 `ValueError` 子类；无一返回成功结构 |
| A09 | `test_roi_validation_boundaries` | 通过 | 18 类非法 ROI 均抛 `code == "invalid_roi"`；`(0,0,10,10)`、`(6,6,4,4)`、`(0,0,1,1)`、`(9,9,1,1)`、`[0,0,4,4]` 正常接受，未裁剪或补边 |
| A10 | `test_input_preservation_and_views` | 通过 | 原数组 `np.array_equal` 不变、dtype 不变；只读数组、非连续视图（`flags["C_CONTIGUOUS"] is False`）、连续副本四项测量逐字段一致 |
| A11 | `test_grayscale_and_bgr_contract` | 通过 | 三通道复制图与灰度图 `metrics`/`applicability` 相等；纯蓝 BGR 期望 brightness=29.0（若误当 RGB 会得 76），contrast=0.0、sharpness=0.0 |
| A12 | `test_output_schema_and_serialization` | 通过 | 顶层恰为 `{metrics, warnings, applicability}`；`warnings` 每项恰为 `{type, evidence, severity}`；递归断言全为 Python 原生类型且浮点有限；`json.dumps(..., allow_nan=False)` 成功且可回读；提示顺序 `measurement_scope → constant_region → insufficient_spatial_support` 稳定 |
| A13 | `test_measurement_only_warnings` | 通过 | 常量图/黑白棋盘/渐变图均无评分·合格·故障字段；`mean_range > 0` 的棋盘与渐变图**只有** `measurement_scope`；`constant_region.evidence` 恰为 `{min_gray, max_gray}`；`measurement_scope.evidence` 恰为 `{region, scene_calibration, limitations}` |
| A14 | 受保护数据 SHA-256 | 通过 | 实施前后对 `photo/`(16)、合成 PNG(46) 与 `answers/*.txt`、`data/manifests/*.json`(3)、`stage2-known-qr.png/.expected.txt`、`src/metrics.py` 等逐一比对，**摘要全部相同**；`src/metrics.py` = `aacc4977…`、`src/analyze_image.py` = `dd246c36…` |
| A15 | 完整 pytest + 闸门 | 通过 | `pytest -q` → **299 passed**（无 failed/skipped）；`check_evaluation_expectations.py` → development/test 两个 split「✅ 与入库期望完全一致」，`improved=3 degraded=0`，**未运行 `--refresh`** |
| A16 | `test_real_png_smoke` | 通过 | `load_normalized_image('data/samples/stage2-known-qr.png')` → 264×264 uint8 BGR；整图与 ROI(66,66,132,132) 均 `valid=True`、`brightness_uniformity` 非空、`json.dumps(allow_nan=False)` 成功；ROI 的 `evidence.region.kind == "roi"`、整图为 `"full_image"`；图片 SHA-256 调用前后一致 |

**结论：A01–A16 全部通过，无失败项。**

### 反例检查结论

- 已主动尝试：4×4 常量图（块 1×1）、5×5 渐变图（分块 2,1,1,1）、1×1 / 1×12 / 1×10 区域、
  贴边与零尺寸/溢出 ROI、修改 ROI 外全部像素、只读数组、非连续视图、复制三通道图。
- 这些输入全部符合规格：草稿里会触发的 `small_blocks` 警告在 4×4/5×5 下**不再出现**；
  极小区域输出 `null` 而非 0；ROI 外像素不影响 ROI 内测量。
- **结论：尝试后未找到反例。** 未发现需要修改验收条件的情形，验收条件未被放宽。

## 9. 观察（用户填写）

| 类别 | 观察 |
| --- | --- |
| A 理解：是否准确理解现有能力与草稿状态 | 待填写 |
| B 输出价值：规格是否提供可执行、可证伪的增量 | 待填写 |
| C 执行质量：实施返工情况 | 尚未实施 |
| D 验证质量：独立验收和反例是否发现有效问题 | 尚未实施验证 |

本次不访问或写入项目外的观察记录目录。
