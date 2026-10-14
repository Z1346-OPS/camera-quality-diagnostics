# 文档 35：基于证据的图像质量测量模块（业务阶段 4.1）

> 编号 `35` 是**文档序号**，不代表业务阶段（见 `AGENTS.md` 的文档编号规范）。
> 任务契约：`docs/tasks/phase-4.1-quality-analysis.md`（用户已审核通过）。

- 日期：2026-10-12
- 代码基线：commit `afdca8f`
- 交付物：`src/quality_analysis.py`（独立模块）、`tests/test_quality_analysis.py`（A01–A16 验收）
- 本模块**只输出测量事实与适用性限制**，不输出评分、合格判定或故障类别

## 1. 为什么单独做一个模块

`src/metrics.py` 已经有亮度、对比度、清晰度三个基础指标，`src/analyze_image.py` 把它们组合进单图报告。
但两者都只描述**整张图**，且报告里没有「这些数字在什么条件下才成立」的说明。

本阶段补的是缺口，不是重复建设：

- 一个**独立的数组级函数** `analyze_quality(image, roi=None)`，可对整图或人工 ROI 调用；
- 一个**固定 4×4 分块**的亮度均衡测量（块均值分布 / 范围 / 标准差）；
- 一套**结构化测量限制**：哪些项因为区域太小而无法计算，用稳定原因码表达。

基础指标一律**复用** `src/metrics.py`，不重新实现；ROI 坐标语义（`x y w h`、右/下边界不包含、越界拒绝）
与 `src/label_analysis.py:24` 保持一致。本模块不导入 QR 模块、不接入任何现有入口。

## 2. 接口与输出契约

顶层**恰好三个字段**：`metrics`、`warnings`、`applicability`。

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| `metrics.sharpness` | float 或 null | 灰度拉普拉斯方差（复用 `metrics.calculate_sharpness`）；不可计算时 `null` |
| `metrics.brightness` | float | 分析区域灰度均值（0–255） |
| `metrics.contrast` | float | 分析区域灰度总体标准差（`ddof=0`） |
| `metrics.brightness_uniformity` | object 或 null | 固定 4×4 网格测量 |
| `warnings` | list[object] | 每项恰好 `type`、`evidence`、`severity` |
| `applicability.valid` | bool | 四项测量是否都满足本接口空间条件 |
| `applicability.reasons` | list[str] | 不可计算项的稳定原因码；无缺项时为 `[]` |

### 2.1 分块契约

对分析区域固定切为 **4 行 × 4 列**，不缩放、不丢边、不重叠。每个方向长度 `n = 4q + r` 时，
前 `r` 段长度 `q+1`，其余为 `q`。`blocks` 按行优先给出 16 个对象，各含 `x`、`y`、`width`、
`height`、`mean`；`x`/`y` 是**原输入数组坐标**（ROI 情形下已含偏移）。`mean_range` 为块均值极差，
`mean_std` 为 16 个块均值的总体标准差（各块等权，非等面积时不解释为全 ROI 标准差）。

### 2.2 小区域与 applicability

| 分析区域宽高 | brightness / contrast | sharpness | brightness_uniformity | valid |
| --- | --- | --- | --- | --- |
| 任一边 < 3 | 计算 | null | null | false |
| 两边 ≥ 3，任一边 < 4 | 计算 | 计算 | null | false |
| 两边 ≥ 4 | 计算 | 计算 | 计算 | true |

原因码顺序固定：`sharpness_insufficient_dimensions` → `uniformity_insufficient_dimensions`。

> 3×3 与 4×4 是**本接口的测量空间条件**，不是经实验标定的光学有效性标准。
> `valid=true` **不代表**图像清晰、曝光正常、适合识读、故障已定位或工业合格。

### 2.3 warnings 白名单（首版只有三种）

| type | 触发条件 | severity |
| --- | --- | --- |
| `measurement_scope` | 始终 | info |
| `constant_region` | 分析区域 `min_gray == max_gray` | info |
| `insufficient_spatial_support` | 存在不可计算指标 | warning |

**正常的块间亮度差异属于 metrics，不因 `mean_range > 0` 产生任何警告。**
`severity` 只表示测量限制的重要性，不表示质量等级或故障严重程度。
不提供 `block_brightness_variation`、`small_blocks` 或其他阈值提示。

## 3. 不改变（回归边界）

- `src/metrics.py` 未改动（哈希 `aacc4977…`，实施前后一致）。
- QR 解码 / 真值 / ROI / 降采样链路、CLI 默认行为、JSON 版本与字段、CSV 格式、输出不覆盖策略：未触碰。
- 合成数据集、清单、独立答案与评测期望：未生成、未 `--refresh`、哈希一致。
- `photo/`、`data/samples/` 原图与历史报告：哈希一致。
- 现有 285 项测试：未删除、未跳过、未弱化。

## 4. 验收记录（A01–A16）

核验命令约定（从项目根执行）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_quality_analysis.py -k '<selector>'
```

| ID | 用例 | 结果 | 证据 |
| --- | --- | --- | --- |
| A01 | `test_constant_image_oracle` | 通过 | 8×8 全 128：brightness=128、contrast=0、sharpness=0；16 块均值全 128，mean_range=0、mean_std=0；valid=true、reasons=[] |
| A02 | `test_two_level_image_oracle` | 通过 | 8×8 左四列 40 / 右四列 120：brightness=80、contrast=40；每行块均值 [40,40,120,120]；mean_range=80、mean_std=40 |
| A03 | `test_impulse_image_oracle` | 通过 | 5×5 中心 100：brightness=4、contrast=√384、sharpness=8000（整数精确比较，√384 用 rel/abs=1e-12） |
| A04 | `test_prechange_metrics_baseline` | 通过 | 三份固定输入对**改动前** `src.metrics` 基线逐字段一致（brightness/contrast/sharpness） |
| A05 | `test_roi_isolation_and_coordinates` | 通过 | 改 ROI 外像素后 ROI 内四项测量不变；块坐标指向原数组（2…8）；右/下边界外一列/一行未被包含 |
| A06 | `test_nondivisible_grid_oracle` | 通过 | 5×7：行高 [2,1,1,1]、列宽 [2,2,2,1]；16 块非空无重叠；面积和 35；块均值按固定像素手算核验；偏移 ROI 坐标正确 |
| A07 | `test_small_region_contract` | 通过 | 1×1/2×2/1×10/10×1 → 两项均 null；3×3/3×10/10×3 → sharpness 计算、uniformity null；4×4/4×10 → 全部计算；不可计算项为 `null` 而非 0 |
| A08 | `test_invalid_images` | 通过 | 非数组/None/空图/float32/uint16/bool/1D/4D/4 通道/2 通道 → `QualityAnalysisError(code="invalid_image")`，不返回成功结构 |
| A09 | `test_roi_validation_boundaries` | 通过 | 浮点/bool/numpy 整数/负坐标/零宽高/越界/长度≠4/ndarray/字符串 → `invalid_roi`；贴边 ROI 正常接受，不裁剪不补边 |
| A10 | `test_input_preservation_and_views` | 通过 | 原数组、只读数组、非连续视图、连续副本：输入 dtype/shape/像素不变，四项测量一致 |
| A11 | `test_grayscale_and_bgr_contract` | 通过 | 复制到 B/G/R 的同值三通道图与灰度图结果一致；纯蓝 BGR 期望 brightness=29（若误当 RGB 会得到 76） |
| A12 | `test_output_schema_and_serialization` | 通过 | 顶层三字段、`warnings` 项三字段、原因码与提示顺序稳定；全为 Python 原生类型；`json.dumps(..., allow_nan=False)` 成功 |
| A13 | `test_measurement_only_warnings` | 通过 | 常量图 / 黑白棋盘 / 渐变图：无评分·合格·故障字段；`mean_range > 0` 时仍只有 `measurement_scope`；`constant_region` evidence 仅 `min_gray`/`max_gray` |
| A14 | 哈希保护 | 通过 | 实施前后 `photo/`、`data/samples/`（含合成 46 图与答案）、`data/manifests/`、`src/metrics.py` 等 SHA-256 全部一致（见 §5） |
| A15 | 完整回归 + 闸门 | 通过 | `pytest -q` → **299 passed**；`tools/check_evaluation_expectations.py` → 两个 split 均「与入库期望完全一致」，未刷新期望 |
| A16 | `test_real_png_smoke` | 通过 | 用 `load_normalized_image` 加载固定 PNG `data/samples/stage2-known-qr.png`（264×264）独立调用新模块，整图与 ROI 均 valid、可严格 JSON 序列化；图片调用前后 SHA-256 一致 |

### 4.1 反例检查（主动尝试，不是「没尝试」）

构造了以下输入试图让它坏，结果均符合规格：

| 尝试 | 结果 |
| --- | --- |
| 4×4 常量图（块为 1×1 像素） | 只产生 `measurement_scope` + `constant_region`；**不再**出现草稿里的 `small_blocks` 警告 |
| 5×5 渐变图（行/列分块为 2,1,1,1） | 块间差异非零但 valid=true、无异常警告 |
| 1×1、1×12、ROI 1×1、ROI 1×10 | 两项均 `null`、valid=false、原因码齐全，未伪造为 0 |
| 贴边 ROI（`(0,6,10,4)`、`(9,9,1,1)`） | 正常接受 |
| `(0,0)` 尺寸、`(5,0,3)`、ROI 溢出图像 | `invalid_image` / `invalid_roi`，不静默裁剪 |
| 修改 ROI 外全部像素 | ROI 内四项测量完全不变 |

**未找到反例。** 另需说明：`metrics.py` 的 `_to_grayscale` 对空 1D 数组会先抛 `ValueError`，
本模块在自己的 `_to_gray` 里先行校验，因此错误码稳定为 `invalid_image`，不依赖旧函数的异常文案。

## 5. 保护对象哈希核验

实施前后对以下对象计算 SHA-256 并比对，**全部一致**：

- `photo/`（16 个文件，含 `evaluation-development-001.json`）
- `data/samples/synthetic-qr-v1/development|test/*.png`（46 张）与 `answers/*.txt`
- `data/manifests/*.json`（3 份，含 `evaluation-synthetic-expectations.json`）
- `data/samples/stage2-known-qr.png`、`stage2-known-qr.expected.txt`
- `src/metrics.py`、`src/analyze_image.py`、`src/label_analysis.py`、`src/analyze_label.py`

草稿 `src/quality_analysis.py` 在实施前的 SHA-256 为
`5f6d074d06cea98b9ddffe78a61a1b80c821cf9aca7ef5d62be60fdc7a6bbb06`，与规格快照一致；
本次是在其基础上**补齐规格差异**，不是重写。

## 6. 相对草稿的差异（本次实际改动）

草稿已具备接口、ROI 校验、分块与 `applicability`。本次只按规格 §6.5 补齐三处：

1. `measurement_scope` 的 evidence 由自由文本 `note` 改为规格要求的
   `limitations`（内容相关 / 固定网格分辨能力 / 跨场景可比性三条限制）。
2. `constant_region` 的 evidence 收敛为 `min_gray`、`max_gray` 两个字段，
   去掉超出「区域灰度恒定」的附加说明。
3. **删除 `small_blocks` 警告与 `SMALL_BLOCK_SIDE` 常量**——草稿的额外阈值提示不在白名单内。
   同时把模块 docstring 里「不同尺寸的区域因此可比」改为规格 §6.3 的措辞（固定网格不保证跨场景/尺寸可比）。

另清理了 `_to_gray` 中一行与上一行重复的维度校验。

## 7. 不可声称的边界

- 本模块输出的是**测量事实**，不是质量评分；没有合格判定、故障类别或自动重拍动作。
- 固定 4×4 网格**不能**保证发现块内部的局部暗点或局部变化，也**不保证**不同场景/尺寸之间可比。
- 块间差异可能来自物体、图案、颜色或阴影，**不能直接称为光照故障**。
- 未做场景标定（`scene_calibration: "none"`）；没有任何经实验标定的阈值。
- 尚未接入 CLI、批量入口或现有报告；接入方案需另行审核。

## 8. 后续

- 若要把结果写进现有报告，应放入独立的 `quality_analysis` 字段，并另行审核（不改历史 JSON 字段含义）。
- 若要扩展 warning 白名单（例如块内局部变化），必须单独审核，不能顺带加入。
