# Phase 4.2：QR 结果与图像质量测量关联

- 日期：2026-10-12（第 4 轮修订，独立反例复核后）
- 状态：**规格编写阶段**。本文件只定义任务；**尚未授权实施**，第 7、8 节留空。
- 本轮修订依据：DeepSeek 只读复核 F1–F10、技术审核后的最小修订清单及用户「进行修订」授权；见
  `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md`。
- 规格编写阶段授权：只允许新增与修订本任务规格及证据说明文件；
  **不修改**源码、测试、配置、原图、历史报告、既有哈希清单、oracle 或提取脚本。
- 项目定位：摄像头图像质量分析与视觉算法可靠性验证平台；QR 是当前验证对象。
- 本规格是后续分析、实施和验证共同使用的输入。测试不得反向定义或改写验收条件。

---

## 1. 前提核验（Step 0）

| 检查 | 证据 | 结论 |
| --- | --- | --- |
| 基础质量测量是否已存在 | `src/quality_analysis.py:131`：`analyze_quality(image, roi=None)` 已实现并验收 | **复用，不重新实现** |
| 质量模块是否已有独立验收 | `tests/test_quality_analysis.py`（A01–A13、A16，共 14 个用例）；`docs/stage-35-evidence-based-quality-analysis.md` §4 | **功能测试已通过**；本任务不重测其内部契约。但 Phase 4.1 的历史资产保护验收**仍有证据缺口**（见 5.1），本规格不宣称其全部验收完成 |
| QR 单图报告是否已存在 | `src/analyze_label.py:49`：`analyze_label(path, roi, expected_file, truth_source, try_downscale=)` 返回完整报告（`:96`–`:102`） | **复用，不改字段含义** |
| QR 报告是否已含基础指标 | `src/analyze_label.py:70`：每个 attempt 带 `metrics = images.calculate_image_metrics(frame)` | 已含**整图/ROI**的基础指标；本任务不重复建设 |
| QR 尝试与汇总是否已保留 | `src/analyze_label.py:77`–`:84`：`attempts` 保留每次解码；`decode_summaries` 保留按 region 的汇总 | **原样保留**，不重算 |
| 状态词表是否已固定 | `src/label_evaluation.py:29`–`:30`：`OUTCOMES` 含 `correct/incorrect/decoded_unverified/not_decoded/decode_error/ambiguous/conflict/execution_error/input_error`；`src/label_analysis.py:48`–`:95` 产生 `decoded/not_decoded/decode_error/ambiguous/execution_error`；`:98`–`:117` 产生 `conflict` | 已有稳定词表；本任务**不新增**状态 |
| 无真值时是否已不称正确 | `src/label_analysis.py:120`–`:127`：`check_expected(decoded, None)` → `{"status": "not_provided"}` | 已满足；本任务沿用，不得自造 `correct` |
| ROI 坐标约定是否已存在 | `src/label_analysis.py:24`–`:38`：`xywh`、右/下边界**不包含**、越界拒绝、不裁剪 | 沿用，不新建语义 |
| 图像标准化是否已存在 | `src/analyze_image.py:81`：`load_normalized_image` 返回 uint8 BGR 与 `source`（path/format/bytes/sha256/width/height/mode）与 `preprocessing` | 复用；本任务不重复实现预处理 |
| 关联模块是否已存在 | 本次枚举 `src/`：无 `quality_qr_analysis.py`；`grep -rn "quality_qr" src/ tests/` 无命中 | **确认缺失** |
| 关联能力是否已被间接覆盖 | `src/analyze_label.py` 的 `attempts[].metrics` 是 `calculate_image_metrics`（`src/analyze_image.py:157`），**不是** Phase 4.1 的 `analyze_quality`；两者字段与适用性语义不同（前者无 `brightness_uniformity` / `applicability` / 小区域契约） | **确认缺失**，且不是重复建设 |
| 关联层是否已有测试 | 本次枚举 `tests/`：无 `test_quality_qr_analysis.py` | **确认缺失** |

**前提核验结论：确认缺失的是「把同一图像、同一区域的 Phase 4.1 质量测量与既有 QR 报告关联起来」的独立模块与验证证据。**

现有 `analyze_label` 已经把 `calculate_image_metrics` 挂到了每个 attempt 上，但那是**基础指标**，
不是 Phase 4.1 的测量契约（没有 4×4 分块均衡、没有 `applicability` 原因码、没有小区域 `null` 语义）。
本任务**不重复**已有基础指标，也**不重算** QR 尝试与汇总；只新增一层**关联**。

> **本次规格不修改任何源码。** 下面的契约是对**后续实施**的要求。

---

## 2. 目标

提供 `analyze_quality_and_qr(path, roi=None, expected_file=None, truth_source=None, *, try_downscale=False)`：
对**同一张图、同一个区域**同时取得 QR 结果与 Phase 4.1 质量测量，并输出**可追溯的结构化关联记录**。

一句话行为变化：**两次读取的文件摘要及规定的标准化信息一致，质量测量与 QR 结果按同一区域关联。**

> **能力边界（不得夸大）**：本模块采用外围组合，会**读取两次**（一次供质量测量，一次由
> `analyze_label` 内部读取）。它提供的是**规定检查范围内**的一致性证据——
> 即 `read_consistency.checked_fields` 列出的那些字段在两次读取中相同。
> 它**不声称**单次读取，**不声称**文件在整个过程中始终未变化，
> 也**不声称**检查范围之外的差异不存在。检查范围与拒绝条件见第 6.3 节。

采用**外围组合**：不重写解码、不重写测量、不改既有报告字段；
把既有 `analyze_label` 的完整输出作为新报告的**子对象** `qr_report` 原样保留，关联信息放在它旁边。

### 2.1 范围

1. 一次调用内取得 QR 报告与质量测量，并建立**可核验的关联**（读取一致性、区域对应、profile 归并）。
2. 整图与 ROI **分别**测量；同一区域的多个解码 profile **共用**一条测量记录。
3. 结构化输出：严格 JSON、Python 原生类型、缺失只能为 `null`。
4. 三类耗时**分别定义**；记录关联模块与质量模块的版本/源码摘要。
5. 质量测量失败时**明确记录错误并保留 QR 结果**，不吞异常、不伪造成功。

### 2.2 不纳入本任务（禁止加入）

- 质量评分、百分制、等级、合格判定、`failure_reason`。
- 故障分类（模糊 / 曝光异常 / 光照故障 / 脏污 / 条纹 / 噪点）。
- 质量阈值、场景标定、自动重拍建议。
- 机器学习、YOLO、深度学习、GUI、Web 服务。
- CLI 接入、批量入口、现有报告接入、相机参数控制、实验数据生成。
- 修改 QR 解码、候选选择、真值判断、退出码或既有报告字段含义。

---

## 3. 不改变（回归边界）

以下为回归测试的靶子，也是验证阶段的核验清单。**逐条都必须保持不变。**

- `src/metrics.py` 的实现、字段语义与算法定义（当前 SHA-256 `aacc4977…`）。
- `src/quality_analysis.py` 的接口、输出契约与 `applicability` 语义（当前 SHA-256 `cbf16c5f…`）。
  **本任务不修改质量模块**；只调用它。
- `src/analyze_label.py`、`src/label_analysis.py`、`src/analyze_image.py`、`src/analysis_config.py`、
  `src/label_evaluation.py` 的实现与字段含义（当前 SHA-256 见第 5.3 节）。
- 既有 QR 整图 / 人工 ROI / 降采样搜索 / 歧义 / 冲突 / 错误分类 / 真值比较。
- 既有 CLI 默认行为、JSON 版本与字段、CSV 格式、输出不覆盖策略。
- 合成数据集、清单、独立答案与评测期望：不生成、不运行 `--refresh`。
- `photo/`、`data/samples/` 原图及历史报告（`data/reports/`）。
- 现有测试：不删除、不跳过、不弱化。

本阶段的新模块**独立调用**，不接入现有产品入口；**不新增第三方依赖**。

---

## 4. 验收条件（外部可核验）

### 4.1 核验命令约定

以下命令从项目根执行。`Q <selector>` 是文档简写，展开为：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_quality_qr_analysis.py -k '<selector>'
if ($LASTEXITCODE -ne 0) { throw "selector run failed with exit code $LASTEXITCODE" }
```

表中给出的 `test_*` 是**后续必须实现**的验收用例名称，不表示目前已有。
**本次规格编写阶段未执行任何验收。**

### 4.2 固定验收项

| ID | 输入或核验对象 | 通过条件；不满足即失败 | 核验命令 |
| --- | --- | --- | --- |
| B01 | 第 6.3 节的 **8 个字段逐项参数化**：每次仅注入一个字段差异，其余一致；另设全一致对照 | 每个差异均抛 `QualityQrAssociationError`，`code == "source_changed_between_reads"`，不返回报告；对照成功且 `checked_fields` 恰为规定的 8 个字段（顺序同 6.3、无缺失/重复/额外项） | `Q test_read_consistency_refusal` |
| B02 | 同一原图的整图与 ROI（含贴边 ROI、偏移 ROI） | 两个 region 各自成测量；`measurement_id` 不重复；块坐标指向原数组；右/下边界不包含；整图与 ROI 的测量互不串配 | `Q test_full_and_roi_regions_do_not_cross` |
| B03 | `try_downscale=True`（每区域 2 个 profile）与 `False`（1 个 profile），分别含无 ROI / 有 ROI | 每个 region 恰好 1 条测量记录；用包裹真实 `analyze_quality` 的调用计数验证：无 ROI 实际调用 1 次，有 ROI 实际调用 2 次，切换 profile 数不增加测量次数；profile 通过 `measurement_id` 共用测量 | `Q test_profiles_share_single_measurement` |
| B04 | 同一固定 PNG 与 ROI | 关联记录里的 `quality` 与**独立调用** `analyze_quality(同一数组, 同一ROI)` 逐字段相等 | `Q test_quality_matches_independent_call` |
| B05 | 同一固定 PNG 与 ROI | `qr_report` 去掉 volatile 路径后，与同一时刻独立调用 `analyze_label` 的输出逐字段相等，且与 oracle 一致；另外保存完整 `qr_report` 深拷贝，再分别修改外层 `measurements[].region`、`associations[].region`，每次都断言整个 `qr_report` 未变，验证无跨层可变引用 | `Q test_qr_subobject_unchanged` |
| B06 | 固定夹具矩阵，状态按 attempt / summary / truth 分层断言 | 真实解码覆盖 attempt 的 `decoded/not_decoded/decode_error/ambiguous`；解码层完整夹具注入覆盖 `execution_error`，以及两 profile 均为 `decoded`、payload 不同而 summary 为 `conflict`（断言 `qr_report.decode_summaries[].decode.status`，关联表仍为 `decoded`）；还须覆盖无真值、小区域、测量异常。补充 decoded + 独立错误答案 → `truth_status == "incorrect"`，及前 profile `decode_error`、后 profile `decoded` 的恢复（失败记录/警告保留）；恢复仅在解码层注入，不能替代前述真实解码覆盖 | `Q test_fixture_matrix_covers_states` |
| B07 | 证据 oracle `docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json` | 7 个 fixture 的 `qr_report` 去掉 volatile 路径后**逐路径**一致；volatile 集合**恰好等于**第 5.4 节列出的路径，不多不少 | `Q test_qr_stable_fields_oracle` |
| B08 | 真实 PNG `data/samples/stage2-known-qr.png`，分别无 ROI、合法偏移 ROI `(66,66,132,132)` | 两次调用均 `status == "completed"`；各测量 `quality` 非 null、`quality_error is None`；严格 JSON 序列化成功；图片 SHA-256 调用前后一致 | `Q test_real_png_smoke_and_serialization` |
| B09 | 原 170 项清单按 5.5 分三类；另核验 4.3.0 的规格快照、4.3.1 的补充摘要及 4.3.2 的已跟踪修改范围 | 168 项字节不变；两份可改文档与其实施前副本作增量 diff 逐块审查；新增文件属于批准清单；规格除状态行和 §7/§8 正文外保持不变（§9 用户专属）；工具/配置/证据摘要一致；缺失、重复、白名单之外变化任一即失败 | 见 4.3 |
| B10 | 既有行为 | 完整 pytest 通过；评测闸门「与入库期望完全一致」，**未刷新期望**；不接受仅以新用例通过为完成依据 | 见 4.3 |
| B11 | 无独立答案的夹具 | `known_truth.status == "not_provided"`；报告任何位置**不得**把读出称为 `correct` | `Q test_no_truth_is_not_correct` |
| B12 | 小区域（任一边 < 3 / < 4） | 透传 `analyze_quality` 输出：不可计算项为 `null`（非 0）、`applicability.reasons` 顺序与内容原样保留 | `Q test_small_region_passthrough` |
| B13 | 注入质量测量失败 | 对应测量记录写入 `quality_error`（含 `code`、`message`、`exception_type`）且 `quality is null`；`qr_report` **完整保留**；顶层 `status == "completed_with_errors"`；**不得**吞异常后报成功 | `Q test_quality_failure_keeps_qr` |
| B14 | 任意返回报告的调用（包含错误状态及注入夹具），注入结构满足 6.7.1 | `timings` 恰含 `decode_seconds`、`quality_seconds`、`total_seconds`，三者均非负；`decode_seconds` 严格等于所有 attempt 的 `decode.duration_seconds` 之和；`total_seconds >= decode_seconds + quality_seconds`；不得对缺字段默认填零 | `Q test_timings_are_defined_separately` |
| B15 | 正常 / 小区域 / 质量失败三类输出 | 顶层字段严格符合第 6.2 节；所有数值为 Python 原生类型且有限；`json.dumps(result, allow_nan=False)` 成功且可回读；`provenance` 含关联模块与质量模块的源码摘要 | `Q test_output_schema_and_provenance` |
| B16 | 同一固定 PNG、偏移 ROI，分别 `try_downscale=False/True` | 包裹真实 `analyze_quality`，调用时复制实际数组并记录 ROI；数组逐元素等于独立标准化完整原图（形状/dtype 相同），整图传 None、ROI 传原图 ROI，最终测量区域像素等于对应切片；两种 profile 设置得到相同 `quality/region/basis`。保留 `basis` 常量断言，但不得只检查自报字段 | `Q test_measurement_basis_is_original_image` |
| B17 | 任意成功或失败输出 | 关联层 `warnings` **恒为 `[]`**（第 6.11 节：首版没有可证伪的关联层限制）；`measurements[].quality.warnings` 与 `qr_report.warnings` **原样保留**，不被合并、重排或改写 | `Q test_association_warnings_contract` |
| B18 | 输入失败 / 一致性失败 / 资源耗尽 / 底层库错误 | 输入与校验失败抛对应既有错误码且**不返回报告**；`MemoryError`、`cv2.error` **继续抛出**，不得转成 `quality_error`，也不得解释为图像质量问题；**仅** `QualityAnalysisError` 转 `quality_error` 并保留 QR | `Q test_exception_taxonomy` |

### 4.3 非 pytest 核验命令（可直接执行）

以下脚本均从**项目根**执行，按 4.3.0 → 4.3.1 → 4.3.2 → 4.3.3 顺序核对；任一抛错立即停止。
4.3.4 留给功能实施后的完整回归；文档修订不得据前述检查宣称 B01–B18 已通过。

> **原生命令的失败处理（强制）**：`$ErrorActionPreference = 'Stop'` **不会**因**原生命令**
> （`python.exe`、`git`、`cmd` 等）返回非零退出码而停止脚本——它只管 PowerShell 的 cmdlet 错误。
> 因此**每一条**原生命令都必须在其**紧后**显式检查 `$LASTEXITCODE`，非零即 `throw` 并停止；
> **不得**在失败后继续执行，也**不得**继续使用失败命令的输出。
> 本页所有代码块均已按此规则补齐。

> **编码说明（重要）**：下列脚本刻意**只用 ASCII**（含注释），因为 Windows PowerShell 5.1
> 对**无 BOM** 的 `.ps1` 文件按 ANSI 解码，中文会破坏字符串终止符、导致解析失败（本机已实测）。
> 中文说明一律放在代码块**外**的正文里。
> 若你把脚本存成 `.ps1` 文件并加入任何非 ASCII 字符，**必须**保存为 **UTF-8 with BOM**；
> 直接粘贴进 PowerShell 控制台执行则无此问题。

#### 4.3.0 B09 前置：核对审核版本，限定规格可回填区段

`specification-review-snapshot.md` 是本轮修订完成后保存的规格**逐字节副本**，用户审核通过后作为
实施基线。它的 SHA-256 由本轮交付消息与修订记录提供，**不写入规格自身**，避免自引用。
实施者必须从用户确认的交付消息取得摘要，先在 PowerShell 设置 `$approvedSpecSha`，再执行本段。
**不得**从待核验文件即时计算该变量，也不得自行替换审核值来消除差异。
本轮只是提交候选版本，**用户确认前仍未授权功能实施**。

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'
if ($approvedSpecSha -cnotmatch '^[0-9a-f]{64}$') { throw 'Set approvedSpecSha from the user-approved delivery first' }

@'
from pathlib import Path
import hashlib, re, sys

root = Path.cwd()
spec = root / "docs/tasks/phase-4.2-quality-qr-association.md"
snapshot = root / "docs/tasks/evidence/phase-4.2-quality-qr-association/specification-review-snapshot.md"
frozen = snapshot.read_bytes()
if hashlib.sha256(frozen).hexdigest() != sys.argv[1]:
    raise SystemExit("APPROVED SPEC SNAPSHOT CHANGED")

def contract(data):
    # Keep headings and all other bytes; remove only approved record bodies.
    for start, end in ((b"## 8. ", b"## 9. "), (b"## 7. ", b"## 8. ")):
        starts = list(re.finditer(rb"(?m)^" + re.escape(start), data))
        ends = list(re.finditer(rb"(?m)^" + re.escape(end), data))
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError("Missing or repeated section heading")
        body = data.index(b"\n", starts[0].start()) + 1
        stop = ends[0].start()
        if body >= stop:
            raise ValueError("Section order changed")
        data = data[:body] + b"<record body>\n" + data[stop:]
    # UTF-8 prefix for the one status line; keep this PowerShell block ASCII.
    status_prefix = bytes.fromhex("2d20e78ab6e68081efbc9a")
    matches = list(re.finditer(rb"(?m)^" + re.escape(status_prefix) + rb"[^\r\n]*", data))
    if len(matches) != 1:
        raise ValueError("Missing or repeated status line")
    return re.sub(rb"(?m)^" + re.escape(status_prefix) + rb"[^\r\n]*", b"<status>", data)

if contract(spec.read_bytes()) != contract(frozen):
    raise SystemExit("SPEC CONTRACT CHANGED OUTSIDE STATUS / SECTION 7 / SECTION 8")
print("SPEC CONTRACT OK: only status and record bodies may differ")
'@ | .\.venv\Scripts\python.exe -B -X utf8 - $approvedSpecSha
if ($LASTEXITCODE -ne 0) { throw 'spec contract check failed' }
```

允许回填的只有状态行、§7/§8 **正文**；节标题仍受保护。§9 由用户填写，执行者不得修改。
改变接口、验收表、比较脚本、保护摘要或其他契约均须重新审核，不能作为「补记录」提交。

#### 4.3.1 B09：保护对象比对（分三类，缺失 / 重复 / 越界变化一律报错）

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

$manifest = 'docs\tasks\evidence\phase-4.2-quality-qr-association\protected-sha256.txt'

# Integrity of the manifest ITSELF, by full SHA-256 (confirmed in revision-2026-10-12.md).
# An entry count alone is NOT sufficient: a tampered manifest can still have 170 lines.
$manifestSha = 'ecac1507047a21957bb6a323666145445e68e6368993d7625da27bf02ea46f95'
$actualManifestSha = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLower()
if ($actualManifestSha -ne $manifestSha) { throw "MANIFEST CHANGED: $actualManifestSha" }

# Supplemental pins: do not rewrite the original 170-entry manifest.
$evidence = 'docs/tasks/evidence/phase-4.2-quality-qr-association'
$supplemental = @{
    'tools/check_evaluation_expectations.py' = '1b2d66e4992f07cd5ec6b2c84125ee3b01c2a309c9d4172a4db8b2dfe30d461e'
    'tools/generate_synthetic_samples.py' = 'c9f9752f617417064e8284b2d3fed28e35eaa7225aee6c015ff47459d7db02b8'
    '.github/workflows/tests.yml' = 'fba46a6f24dbfca9300d8f0e53729ba605e515e643ef1e6facac16db9133df00'
    'requirements.txt' = '69413e3518d8ea8cc59596f391c6c987565fee72180265f0d9e3ff000d82630b'
    '.gitignore' = 'fcf5b5ad04e539b2fe39e0f28993dce6d04db46f4e64ca670ae07cbafcaf7899'
    "$evidence/README.phase-4.2-baseline.md" = '3c0b83fb047b3737a80ac111a444a668c2c09383f14cbb59cde2c62a373e54b7'
    "$evidence/stage-34.phase-4.2-baseline.md" = 'b88cfc4114c6c11b6f520238844bc915e957f879ba676a6f0b9aa49adb2c9233'
    "$evidence/revision-2026-10-12.md" = '45e3b0103ede999b1f83fd5718e883f81f0352ccae4be98f6991d51d04270457'
    "$evidence/README.md" = 'f03a57e9fdb1038c4ed7a5c292f3e92e3c36228aedee1c7ab422b7939ceb35dd'
}
foreach ($rel in $supplemental.Keys) {
    if (-not (Test-Path -LiteralPath $rel -PathType Leaf)) { throw "SUPPLEMENTAL FILE MISSING: $rel" }
    $actual = (Get-FileHash -LiteralPath $rel -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $supplemental[$rel]) { throw "SUPPLEMENTAL FILE CHANGED: $rel" }
}
Write-Host "supplemental pins: $($supplemental.Count) checked, 0 changed"

# Class 2: documents Phase 4.2 is ALLOWED to modify.
# Their recorded digest only locates the baseline; it is NOT required to stay unchanged.
# NOTE: docs/tasks/README.md is a DIFFERENT file and is NOT in this list.
$mutableDocs     = @('README.md', 'docs/stage-34-project-capability-matrix.md')
$mutableExpected = 2
$frozenExpected  = 168

# Parse manifest: format check + duplicate path check.
$entries = New-Object System.Collections.Generic.List[object]
$seen = @{}
$lineNo = 0
foreach ($line in Get-Content -LiteralPath $manifest -Encoding UTF8) {
    $lineNo++
    if ($line -match '^\s*#' -or $line.Trim() -eq '') { continue }
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "bad manifest line $lineNo : $line" }
    $digest = $Matches[1]; $rel = $Matches[2]
    if ($seen.ContainsKey($rel)) { throw "duplicate path in manifest: $rel" }
    $seen[$rel] = $true
    $entries.Add([pscustomobject]@{ Rel = $rel; Digest = $digest })
}

# Classify first, then assert the split is exactly 168 + 2.
foreach ($doc in $mutableDocs) {
    if (-not $seen.ContainsKey($doc)) { throw "mutable doc absent from manifest: $doc" }
}
$frozenEntries  = @($entries | Where-Object { $mutableDocs -notcontains $_.Rel })
$mutableEntries = @($entries | Where-Object { $mutableDocs -contains    $_.Rel })
if ($mutableEntries.Count -ne $mutableExpected) { throw "mutable docs in manifest: $($mutableEntries.Count), expected $mutableExpected" }
if ($frozenEntries.Count  -ne $frozenExpected)  { throw "byte-frozen in manifest: $($frozenEntries.Count), expected $frozenExpected" }
Write-Host "manifest parsed: $($entries.Count) entries = $($frozenEntries.Count) byte-frozen + $($mutableEntries.Count) mutable"

$missing = @(); $frozenChanged = @(); $mutableChanged = @()
foreach ($e in $entries) {
    $full = $e.Rel -replace '/', '\'
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { $missing += $e.Rel; continue }
    $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLower()
    if ($actual -eq $e.Digest) { continue }
    if ($mutableDocs -contains $e.Rel) { $mutableChanged += $e.Rel } else { $frozenChanged += $e.Rel }
}

if ($missing.Count)       { throw "MISSING FILES $($missing.Count):`n" + ($missing -join "`n") }
if ($frozenChanged.Count) { throw "CHANGED OUTSIDE WHITELIST $($frozenChanged.Count):`n" + ($frozenChanged -join "`n") }

# Report the two classes SEPARATELY. Never lump them into one "170 frozen" figure.
Write-Host "byte-frozen objects : $($frozenEntries.Count) checked, $($frozenChanged.Count) changed"
Write-Host "mutable docs        : $($mutableEntries.Count) checked, $($mutableChanged.Count) changed"

# Compare current documents with their actual dirty-worktree baselines, NOT HEAD.
$docBaselines = @{
    'README.md' = "$evidence/README.phase-4.2-baseline.md"
    'docs/stage-34-project-capability-matrix.md' = "$evidence/stage-34.phase-4.2-baseline.md"
}
foreach ($doc in $mutableDocs) {
    git --no-pager diff --no-index -- $docBaselines[$doc] $doc
    $diffExit = $LASTEXITCODE
    # git diff --no-index: 0 = equal, 1 = differences to review, other = failure.
    if ($diffExit -notin @(0, 1)) { throw "baseline diff failed: $doc, exit $diffExit" }
    if ($diffExit -eq 1) { Write-Host "REVIEW REQUIRED: Phase 4.2 increment in $doc" }
}
```

#### 4.3.2 B09 补充：新增文件必须属于批准清单

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

# Class 3: newly approved files (section 6.8).
$approvedNew = @(
    'src/quality_qr_analysis.py',
    'tests/test_quality_qr_analysis.py',
    'docs/stage-36-quality-qr-association.md'
)
# Baseline untracked set = the table in section 5.1 (state before implementation).
$baselineUntracked = @(
    'docs/observations/2026-10-12-phase4.1-review.md',
    'docs/stage-35-evidence-based-quality-analysis.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/README.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/protected-sha256.txt',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/revision-2026-10-12.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/README.phase-4.2-baseline.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/stage-34.phase-4.2-baseline.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/specification-review-snapshot.md',
    'docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md',
    'docs/tasks/phase-4.1-quality-analysis.md',
    'docs/tasks/phase-4.2-quality-qr-association.md',
    'src/quality_analysis.py',
    'tests/test_quality_analysis.py'
)

$nowUntracked = @(git ls-files --others --exclude-standard)
# A failed git call yields empty output, which would make the checks below pass vacuously.
if ($LASTEXITCODE -ne 0) { throw "git ls-files failed with exit code $LASTEXITCODE; refusing to use its output" }

$removed = @($baselineUntracked | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($removed.Count) { throw "BASELINE FILES MISSING:`n" + ($removed -join "`n") }

# HEAD remains fixed: no commit/push is authorized. Include staged changes.
$head = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'git rev-parse failed' }
if ($head -ne 'afdca8f43b66dcb8eca2b6280aebefd6215e4f03') { throw 'HEAD changed; obtain approval and rebaseline' }
$trackedChanged = @(git diff --name-only HEAD --)
if ($LASTEXITCODE -ne 0) { throw 'git diff HEAD failed' }
$allowedChanged = @('README.md', 'docs/stage-34-project-capability-matrix.md') + $approvedNew + $baselineUntracked
$outside = @($trackedChanged | Where-Object { $allowedChanged -notcontains $_ })
if ($outside.Count) { throw "UNAPPROVED TRACKED CHANGES:`n" + ($outside -join "`n") }

$added = @($nowUntracked | Where-Object { $baselineUntracked -notcontains $_ })
$unapproved = @($added | Where-Object { $approvedNew -notcontains $_ })
if ($unapproved.Count) { throw "UNAPPROVED NEW FILES:`n" + ($unapproved -join "`n") }
Write-Host "new files all approved: $($added -join ', ')"
```

原有文件以存在性及各自内容检查保护，不要求一直保持 `??`；暂存不构成删除。
当前仍未授权 commit/push；若用户另行批准提交，必须重新确认 HEAD 和工作区基线后再验收。
本段覆盖已跟踪文件的修改范围，不能仅凭「未跟踪文件集合合规」宣称保护检查完成。

#### 4.3.3 B07：重算 oracle 并比较（**绝不覆盖冻结版本**）

在**内存**里比较：比较脚本自己以子进程方式运行提取脚本、按**字节**捕获其输出，
因此不产生任何候选文件，也**不可能**写到冻结路径。

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

@'
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(r"D:\Projects\Python\camera-quality-diagnostics")
FROZEN = ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json"
SCRIPT = ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py"

# Integrity of the FROZEN oracle itself, by full SHA-256 (confirmed in revision-2026-10-12.md).
# Without this, overwriting the frozen file with a fresh run would make the comparison pass.
FROZEN_SHA = "dd0738266f0fed5a3f910e02ca3fb9c82cb7cc3e922f8a8f311f3bcba8f732b4"
actual_frozen_sha = hashlib.sha256(FROZEN.read_bytes()).hexdigest()
if actual_frozen_sha != FROZEN_SHA:
    print(f"FROZEN ORACLE CHANGED: {actual_frozen_sha}")
    sys.exit(1)

SCRIPT_SHA = "c5dac7f0bb1acf618616a60028720cff38f30506cff7bca30fc1e73a2c032fac"
frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
if hashlib.sha256(SCRIPT.read_bytes()).hexdigest() != SCRIPT_SHA or frozen["generator_source_sha256"] != SCRIPT_SHA:
    raise SystemExit("EXTRACTOR HASH MISMATCH")

# Capture the extractor output as BYTES: no shell/console encoding is involved.
run = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT)],
                     capture_output=True, check=True)
candidate = json.loads(run.stdout.decode("utf-8"))

def walk(a, b, path=""):
    if type(a) is not type(b):
        yield f"{path}: type {type(a).__name__} != {type(b).__name__}"; return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:   yield f"{path}.{k}: extra"
            elif k not in b: yield f"{path}.{k}: missing"
            else:            yield from walk(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f"{path}: len {len(a)} != {len(b)}"; return
        for i, (x, y) in enumerate(zip(a, b)):
            yield from walk(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {a!r} != {b!r}"

# Only document-level volatile field: generation time.
# Report-level volatile paths are already stripped at generation time (see volatile_paths).
for d in (frozen, candidate):
    d.pop("generated_at_utc", None)

diffs = list(walk(frozen, candidate))
if diffs:
    print(f"ORACLE MISMATCH: {len(diffs)}")
    for d in diffs[:50]:
        print("   ", d)
    sys.exit(1)
print("ORACLE OK: identical except generated_at_utc")
'@ | .\.venv\Scripts\python.exe -B -X utf8 -
if ($LASTEXITCODE -ne 0) { throw "oracle comparison failed" }
```

> **禁止**把提取脚本的输出重定向到 `qr-stable-fields-oracle.json`。
> 该文件是**冻结**基线；重跑只允许在内存中比较，**不得覆盖、不得重新冻结**。

#### 4.3.4 B10：完整回归 + 评测闸门

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

# $ErrorActionPreference does NOT stop on a non-zero exit code of a NATIVE command.
# Every native command must be followed by an explicit $LASTEXITCODE check, and a
# failure must stop the script before any later command or output is used.
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py
if ($LASTEXITCODE -ne 0) { throw "evaluation gate failed with exit code $LASTEXITCODE" }
```

> 环境注记（来自 `docs/observations/2026-10-12-phase4.1-review.md` §1）：
> 闸门脚本在受限沙箱下可能因 `tempfile` 清理被拒而返回非 0。**那是环境限制，不是项目缺陷**；
> 复核时必须记录运行环境，不能把沙箱阻断误判成闸门失败。

### 4.4 oracle 与比较规则

- B07 的 oracle **来自本次改动之外**：由证据脚本用**改动前**的 `analyze_label` 生成，
  **已保存但未提交**（不在任何 commit 里，也不在 HEAD 里）。
- B04 的 oracle 是**独立调用** `analyze_quality`，不是关联模块的内部输出。
- B05 的 oracle 是**同一时刻独立调用** `analyze_label`，不是从 `qr_report` 里取。
- 比较必须**逐路径**；只允许第 5.4 节列出的 volatile 路径不同。
  **禁止**「差异属于时间类就整体忽略」这类笼统豁免。
- 不得用阈值或容差放宽 QR 期望。
- **oracle 是冻结的**：实施者不得用新模块输出刷新它，也不得重新生成覆盖它（见 4.3.3）。

### 4.5 证据目录的依赖规则（测试可用，源码不可用）

| 主体 | 允许 | 禁止 |
| --- | --- | --- |
| 产品源码 `src/` | — | **不得**以任何方式依赖证据目录（导入、读文件、拼路径） |
| 验收测试 `tests/test_quality_qr_analysis.py` | 可以**只读加载**冻结的 `qr-stable-fields-oracle.json` 作为期望 | **不得**导入或执行 `extract_qr_stable_fields.py` 来生成期望 |
| 提取脚本 `extract_qr_stable_fields.py` | 作为**证据工具**保留在原地 | 不得移动、删除、改名，不得成为产品依赖 |
| 实施者 | 用 4.3.3 的方式**比较** | **不得**用新模块输出刷新或覆盖 oracle |

> 依据：oracle 必须来自被测实现之外。测试**读取**一份冻结的外部事实是正当的；
> 让测试**运行**生成脚本、或让实现**回写**期望，都会把 oracle 变成被测对象的产物。

---

## 5. 基线快照

### 5.1 工作区与保护对象

- Git 基线：`afdca8f43b66dcb8eca2b6280aebefd6215e4f03`。

- **Phase 4.1 的状态（不得夸大）**：**功能测试通过**（`pytest` 299 passed、评测闸门与入库期望一致），
  但**历史资产保护验收仍有证据缺口**：`photo/` 只有 mtime 弱证据，
  `data/reports/` 被 `.gitignore` 排除、tracked 数为 0、无任何前置证据。
  详见 `docs/observations/2026-10-12-phase4.1-review.md` §2、§4。
  本规格**不宣称** Phase 4.1 全部验收完成。

- 本规格第 2 轮修订时刻的 `M`（2 个文件）与 `??`（11 个文件）：

  | 状态 | 路径 |
  | --- | --- |
  | `M` | `README.md` |
  | `M` | `docs/stage-34-project-capability-matrix.md` |
  | `??` | `docs/observations/2026-10-12-phase4.1-review.md` |
  | `??` | `docs/stage-35-evidence-based-quality-analysis.md` |
  | `??` | `docs/tasks/phase-4.1-quality-analysis.md` |
  | `??` | `docs/tasks/phase-4.2-quality-qr-association.md`（本文件） |
  | `??` | `docs/tasks/evidence/phase-4.2-quality-qr-association/README.md` |
  | `??` | `docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py` |
  | `??` | `docs/tasks/evidence/phase-4.2-quality-qr-association/protected-sha256.txt` |
  | `??` | `docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json` |
  | `??` | `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-2026-10-12.md` |
  | `??` | `src/quality_analysis.py` |
  | `??` | `tests/test_quality_analysis.py` |

  **全部必须逐项保留。** **禁止**清理、覆盖、`git clean`、`git reset --hard`，也**禁止**擅自提交。
  Phase 4.1 复核（`docs/observations/2026-10-12-phase4.1-review.md` §7）建议先单独提交规格文件以取得
  commit hash；**该动作不在本任务范围内**，需用户另行决定。
  上表保留第 2 轮历史状态。第 4 轮另外新建以下 4 份证据，均须逐项保留，
  故 4.3.2 的 `$baselineUntracked` 为上表 11 项加下列 4 项，共 **15 项**：
  - `docs/tasks/evidence/phase-4.2-quality-qr-association/README.phase-4.2-baseline.md`
  - `docs/tasks/evidence/phase-4.2-quality-qr-association/stage-34.phase-4.2-baseline.md`
  - `docs/tasks/evidence/phase-4.2-quality-qr-association/specification-review-snapshot.md`
  - `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md`
  前两项是原有脏工作区文档的逐字节副本；第三项是本轮规格候选快照；第四项为修订记录。
  本轮不执行提交。另行获准提交时必须重新审核基线，不能沿用旧 HEAD 检查结论。

- **HEAD 不是当前所有文件的实际基线。** HEAD 只覆盖 git 已跟踪对象；
  上表的未跟踪对象与 `photo/`、`data/reports/` 不在 HEAD 里。
- 保护对象 SHA-256 清单（本次新建，**未覆盖旧证据**）：
  `docs/tasks/evidence/phase-4.2-quality-qr-association/protected-sha256.txt`（170 项）。
  覆盖范围：`src/`(25)、`tests/`(22)、`data/samples/`(56)、`data/manifests/`(3)、
  `data/reports/`(41)、`photo/`(16)、`docs/tasks/`(2)、`docs/observations/`(1)、
  顶层 `README.md`/`AGENTS.md`/`docs/stage-34-*`/`docs/stage-35-*`(4)。

- **本快照的边界（必须遵守）**：
  1. 它只记录**当前（Phase 4.2 实施前）**的状态，只证明「生成时刻**之后**」这些对象是否变化。
  2. 它**不能**补造 Phase 4.1 的历史前置证据。
     生成时 Phase 4.1 的产出**已经存在且未提交**，所以它记录的是「Phase 4.2 开始前」的状态，
     **不是**「Phase 4.1 实施前」的状态。把它当后者使用属于倒填。
  3. 对 git 已跟踪对象，HEAD 基线是更强的 oracle（blob 哈希不可事后篡改）；本清单是补充。
  4. `photo/` 与 `data/reports/` 被 `.gitignore` 排除，git 覆盖不到——这是本清单存在的核心理由。
  5. 清单**不区分**「必须字节不变」与「允许修改」，因此**不能**整体当作"必须完全一致"来用；
     必须按第 5.5 节分三类处理。**不得为了让比对通过而修改基线清单。**

### 5.2 受保护源码的当前摘要

| 文件 | SHA-256（前 8 位） | 本任务是否允许改动 |
| --- | --- | --- |
| `src/metrics.py` | `aacc4977…` | ❌ 不允许 |
| `src/quality_analysis.py` | `cbf16c5f…` | ❌ 不允许 |
| `src/analyze_label.py` | `0cf29b0b…` | ❌ 不允许 |
| `src/label_analysis.py` | `d27deae8…` | ❌ 不允许 |
| `src/analyze_image.py` | `dd246c36…` | ❌ 不允许 |
| `src/label_evaluation.py` | `8573d156…` | ❌ 不允许 |

### 5.3 改动前的 QR 稳定业务字段 oracle（本次实测）

用**改动前**的 `src/analyze_label.py` 对 7 个固定夹具生成，**已保存但未提交**：

- 路径：`docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json`
  （SHA-256 `dd0738266f0fed5a3f910e02ca3fb9c82cb7cc3e922f8a8f311f3bcba8f732b4`）
- 生成脚本：`docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py`
  （SHA-256 `c5dac7f0bb1acf618616a60028720cff38f30506cff7bca30fc1e73a2c032fac`，
  与 oracle 内 `generator_source_sha256` 一致）
- 脚本**只读**、**不导入**待实现模块、确定性（除 `generated_at_utc` 外两次运行一致，已实测）。
- **冻结**：不得用新模块输出刷新它，也不得重新生成覆盖它（比较方式见 4.3.3）。

| fixture | 覆盖状态 | 真值 |
| --- | --- | --- |
| `stage2_full_no_downscale` | decoded | correct |
| `stage2_roi_with_downscale` | full_image=decoded / roi=not_decoded | correct / not_decoded |
| `dev01_clean_decoded` | decoded | correct |
| `dev07_blur5_decode_error` | decode_error | decode_error |
| `dev08_blur8_not_decoded` | not_decoded | not_decoded |
| `test07_blur5_ambiguous` | ambiguous | ambiguous |
| `dev01_clean_no_truth` | decoded | **not_provided** |

这份 oracle 与独立数学定义共同构成外部 oracle；**不得由新模块重生成覆盖**。

### 5.4 允许变化的字段（逐路径，禁止笼统忽略）

以下路径在「改动前后」比较中**不比较**：

| 路径 | 为什么允许变化 |
| --- | --- |
| `analysis_id` | 每次调用的随机 uuid4 |
| `analyzed_at` | 墙上时间戳 |
| `analysis_duration_seconds` | 耗时 |
| `provenance.git` | commit / working_tree_dirty / status 随提交变化 |
| `attempts[].decode.duration_seconds` | 单次解码耗时 |

（上表描述的是**既有 `analyze_label` 报告**的 volatile 路径。
新增的关联层另有 `association_id`、`timings` 等自身字段，见第 6.2 节。）

**其余任何路径出现差异均不得通过本基线比较。** 不接受按类型豁免。

**适用环境边界**：oracle 含绝对路径、运行库版本和解码器版本；本任务限定同一项目路径、
同一 `.venv` 冻结环境（Python 3.12.10 / OpenCV 5.0.0 / NumPy 2.5.3 /
Pillow 12.3.0 / zxing-cpp 3.1.1）。跨机器、迁移路径或升级依赖不在本次保证范围。
环境不匹配时停止并报告适用范围不满足，不能直接认定业务回归，也不能自动刷新 oracle。
`provenance.runtime` 与 decoder 版本**不加入** volatile 白名单；环境迁移另行审核。

### 5.5 保护对象清单的三类划分（B09 依据）

`protected-sha256.txt` 的 170 项**不能整体当作"必须完全一致"**，必须分三类处理。
**不得为了让比对通过而修改基线清单。**

| 类别 | 范围 | 实施后的要求 |
| --- | --- | --- |
| **1. 字节不变对象** | 清单中**除第 2 类以外**的全部 **168 项**（`src/`、`tests/`、`data/samples/`、`data/manifests/`、`data/reports/`、`photo/`、`docs/tasks/README.md`、`docs/tasks/phase-4.1-*`、`docs/observations/*`、`AGENTS.md`、`docs/stage-35-*` 等） | **逐项核对 SHA-256 必须一致**；任一不同即失败 |
| **2. 允许修改的文档** | **仅** `README.md`、`docs/stage-34-project-capability-matrix.md`（第 6.8 节批准） | 以本轮保存的实施前逐字节副本为基线，副本摘要须等于原清单对应摘要；用 4.3.1 的 `git diff --no-index` 逐块审查本次增量。当前文件不要求摘要不变；对 HEAD 的 diff 是含 Phase 4.1 的累计差异，不能替代本次增量审查 |
| **3. 新增文件** | 第 6.8 节批准的新增清单 | **单独核对**：新增文件必须属于批准清单；未批准的新增文件即失败 |

> 第 2 类只有这两份文档。`docs/tasks/README.md` 与顶层 `README.md` 是**两份不同的文件**：
> 前者不在白名单内，仍属第 1 类（字节不变）。

**清单外补充保护**：原清单仍为 170 项；4.3.1 另钉住工具、CI/依赖配置、忽略规则、
两份文档副本、旧修订记录与本轮证据说明的完整摘要。4.3.0 检查用户确认的规格快照及
允许回填区段；4.3.2 检查已跟踪修改范围。它们共同构成 B09，不能只跑原 170 项即宣称完成。

### 5.6 本轮修订后的产物版本（供确认）

| 产物 | SHA-256 |
| --- | --- |
| `protected-sha256.txt`（本轮**未改动**） | `ecac1507047a21957bb6a323666145445e68e6368993d7625da27bf02ea46f95` |
| `qr-stable-fields-oracle.json`（本轮**未改动**） | `dd0738266f0fed5a3f910e02ca3fb9c82cb7cc3e922f8a8f311f3bcba8f732b4` |
| `extract_qr_stable_fields.py`（本轮**未改动**） | `c5dac7f0bb1acf618616a60028720cff38f30506cff7bca30fc1e73a2c032fac` |
| 本规格 `docs/tasks/phase-4.2-quality-qr-association.md` | 见修订记录（规格自身的摘要不写入自身，避免自引用） |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-2026-10-12.md`（历史记录，本轮不改） | `45e3b0103ede999b1f83fd5718e883f81f0352ccae4be98f6991d51d04270457` |
| `README.phase-4.2-baseline.md` | `3c0b83fb047b3737a80ac111a444a668c2c09383f14cbb59cde2c62a373e54b7` |
| `stage-34.phase-4.2-baseline.md` | `b88cfc4114c6c11b6f520238844bc915e957f879ba676a6f0b9aa49adb2c9233` |
| `specification-review-snapshot.md` | 与本轮规格逐字节相同，摘要见修订记录及交付消息；用户审核后由 4.3.0 外部锚定 |

本轮完整产物摘要见 `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md`
及交付消息。修订记录自身摘要只在交付消息提供，不写入自身，避免自引用。

---

## 6. 分析区：接口、契约、影响与风险

### 6.1 函数与输入契约

```python
analyze_quality_and_qr(path, roi=None, expected_file=None, truth_source=None, *, try_downscale=False)
```

- `path`：本地 JPEG/PNG 路径，交给既有 `load_normalized_image` 读取与标准化。
- `roi`：`None`，或四个 Python 整数的 list/tuple（`x, y, width, height`）。
  语义与 `src/label_analysis.py:24` **完全一致**：右/下边界不包含、越界拒绝、不裁剪、不补边。
- `expected_file` / `truth_source`：语义与 `src/analyze_label.py:25` 一致；
  两者必须同时给或同时不给。
- `try_downscale`：必须是 `bool`（`type(v) is bool`），否则拒绝。
- 非法输入抛异常，**不返回报告**。复用既有错误类型与错误码：
  `images.AnalysisError`、`LabelAnalysisError`，以及本模块新增的
  `QualityQrAssociationError(ValueError)`（`code == "source_changed_between_reads"`）。
- **不修改输入文件**、不写文件、不联网、不打开相机、不调用 CLI。

### 6.2 输出契约

顶层字段（新增字段一律加前缀，避免与既有报告冲突）：

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| `schema_version` | int | 关联报告的版本，首版为 `1` |
| `report_type` | str | `"quality_qr_association"` |
| `association_id` | str | 每次调用的随机 uuid4 hex |
| `analyzed_at` | str | UTC ISO-8601 |
| `status` | str | `"completed"` 或 `"completed_with_errors"`（见 6.6） |
| `timings` | object | 第 6.7 节，恰含三个字段 |
| `provenance` | object | 第 6.9 节 |
| `read_consistency` | object | 第 6.3 节 |
| `requested_roi` | list 或 null | 原样回显请求的 ROI（`null` 表示整图） |
| `measurements` | list[object] | 每个 region 恰一条，见 6.4 |
| `associations` | list[object] | 每个 (region, profile) 恰一条，见 6.5 |
| `qr_report` | object | **既有 `analyze_label` 的完整输出，逐字段原样保留** |
| `warnings` | list[object] | 关联层自身的限制说明。**首版恒为 `[]`**（第 6.11 节）；**不与** `qr_report.warnings` 合并 |

`qr_report` **必须逐字段原样**，不得增删改任何字段或取值。
关联层不重算 QR、不重排 `attempts`、不重选候选、不改 `decode_summaries`。
外层 `measurements`、`associations` 的可变字段必须新建，不能与 `qr_report` 子对象共享可变引用。
这不要求改变或消除既有 QR 报告**内部**的共享引用；只隔离新关联层与 QR 子对象。
验收采用 B05 的修改后不变检查，不能仅以初始值相等或浅层 `is not` 作为完整证明。

报告里共有**三处** warnings，来源与归属必须分明：

| 位置 | 来源 | 关联层的处理 |
| --- | --- | --- |
| `qr_report.warnings` | 既有 `analyze_label`（如 `decode_attempt_errors`） | **原样保留**，不合并、不重排、不改写 |
| `measurements[].quality.warnings` | Phase 4.1 `analyze_quality`（`measurement_scope` 等） | **原样透传**，不合并、不重排、不改写 |
| `warnings`（顶层） | 关联层自身 | **首版恒为 `[]`**，见第 6.11 节 |

所有数值有限、Python 原生 `int`/`float`；缺失只能 `null`，**禁止** `NaN`/`Infinity`。

### 6.3 读取一致性（契约 1、2）

组合调用**会读两次图**（一次供质量测量，一次由 `analyze_label` 内部读取）。
这是"外围组合"的必然结果，因此必须**主动检测**：

- 关联层自己读一次，得到 `sha256(file bytes)` 与标准化结果（`format`/`mode`/`width`/`height`/
  `exif_orientation`/分析图宽高）。
- 调用 `analyze_label(path, ...)`，从 `qr_report.source` 与 `qr_report.preprocessing` 取同样字段。
- **逐字段比对**：`sha256`、`format`、`mode`、`width`、`height`、`exif_orientation`、
  `analysis_width`、`analysis_height`。
- 任一不一致 → 抛 `QualityQrAssociationError(code="source_changed_between_reads")`，
  **不输出报告**、不静默关联、不"取其一为准"。
- 一致 → `read_consistency` 记录两侧摘要与 `consistent: true`。

`read_consistency` 字段：`qr_read_sha256`、`quality_read_sha256`、`consistent`、
`checked_fields`（本次实际比对的字段名列表，顺序固定为
`["sha256", "format", "mode", "width", "height", "exif_orientation", "analysis_width", "analysis_height"]`）。

> 同一进程、同一标准化实现与环境下，相同文件字节通常产生相同标准化信息。
> 额外字段检查用来核验两条调用链遵守相同的标准化契约，并在回归或注入差异时拒绝关联；
> 它不是独立的图像像素一致性证明，也不据此声称能检出额外的现场故障。

### 6.4 测量记录（契约 3、4、7）

`measurements` 每个 region **恰一条**：

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| `measurement_id` | str | `"full_image"` 或 `"roi"`（region kind；至多各一个，天然唯一） |
| `region` | object | 与 `label_analysis.select_region` 同构：`kind`/`x`/`y`/`width`/`height` |
| `basis` | str | **恒为** `"original_normalized_image_region"` |
| `quality` | object 或 null | `analyze_quality` 的输出**原样**；失败时为 `null` |
| `quality_error` | object 或 null | `{code, message, exception_type}`；成功时为 `null` |
| `duration_seconds` | float | 该次 `analyze_quality` 调用的墙钟耗时 |

- **`basis` 的意义（契约 4）**：质量测量始终在**标准化后的原图区域**上完成，
  **不是**解码器内部降采样后的图。`try_downscale=True` 只影响解码 profile，
  **不影响** `basis`、`region` 或 `quality` 的取值。
- 报告中**不得**出现把测量标注为"解码器内部降采样图指标"的字段或措辞。
- 小区域时 `quality` 原样透传：不可计算项为 `null`、`applicability.reasons` 顺序与内容不变（契约 7）。
- 统一调用方式：整图为 `analyze_quality(完整标准化数组, None)`，ROI 为
  `analyze_quality(完整标准化数组, 原图ROI)`，以保留分块坐标与 warnings 区域的原图坐标。
  **禁止**先裁剪（无论是否再次传 ROI），禁止传入任何解码降采样图。
  B16 必须核对实际数组和 ROI，并将最终被测区域与独立标准化原图的相应切片逐元素核对。
  无 ROI 调用质量模块一次，有 ROI 分别测量整图/ROI 共两次；不得重复测量后丢弃结果。
  外层 `region` 按原图坐标记录，复制自既有结构时必须隔离可变引用。

### 6.5 关联表（契约 3）

`associations` 每个 (region, profile) **恰一条**：

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| `measurement_id` | str | **引用** 6.4 的记录；不复制测量内容 |
| `region` | object | 同上，与对应测量记录的 `region` 相等 |
| `profile` | str | `"baseline"` 或 `"internal_downscale_search"`（与 `analyze_label` 同名） |
| `attempt_index` | int | 在 `qr_report.attempts` 中的下标 |
| `decode_status` | str | `qr_report.attempts[attempt_index].decode.status` |
| `truth_status` | str | `qr_report.attempts[attempt_index].truth_check.status` |

**同一区域的多个 profile 必须引用同一条测量记录。**
因此 `len({a["measurement_id"] for a in associations}) == len(measurements)`，
且 `len(associations) == len(qr_report.attempts)`。
**多个 profile 不得被计为多个独立样本。**

### 6.6 状态与错误（契约 5、6、8）

- 关联层**不新增**状态词；`decode_status` 直接引用既有值：
  `decoded` / `not_decoded` / `decode_error` / `ambiguous` / `execution_error`。
  `conflict` **仅在汇总层**出现，由保留的 `qr_report.decode_summaries[].decode.status` 表达，
  不出现在 `associations[].decode_status`，本任务不新增汇总关联字段。
  注入 A/B 两个不同 payload 时，两个 association 均保留 `decoded`，对应 summary 保留 `conflict`。
- 无独立答案时，`truth_status` 必须为 `not_provided`；
  **不得**在任何位置把读出称为 `correct`（契约 6）。
- 顶层 `status`：
  - `"completed"`：所有测量成功，且 `qr_report.status == "completed"`。
  - `"completed_with_errors"`：任一测量记录有 `quality_error`，
    或 `qr_report.status == "completed_with_errors"`。
- **质量测量失败时（契约 8）**：
  - 写入该测量的 `quality_error`，`quality` 置 `null`；
  - `qr_report` **完整保留**；
  - 顶层 `status` 置 `"completed_with_errors"`；
  - **不得**吞掉异常后报成功，也**不得**因为测量失败而丢弃 QR 结果。
- 输入/校验阶段失败 → **抛异常**，不返回报告。这与"测量阶段失败"是两回事，不得混淆。

#### 6.6.1 异常分类（必须逐类处理，不得笼统捕获）

| 阶段 | 异常 | 处理 | 错误码 |
| --- | --- | --- | --- |
| 图片读取 / 标准化 | `images.AnalysisError` | **继续抛出**，不返回报告 | 沿用既有（`input_not_found` / `corrupt_image` / `unsupported_format` / `file_limit_exceeded` / `pixel_limit_exceeded` / `unsupported_mode` / `invalid_orientation` 等，`src/analyze_image.py:88`–`:131`） |
| ROI / 解码配置 / 真值参数 | `LabelAnalysisError` | **继续抛出**，不返回报告 | 沿用既有（`invalid_roi`、`invalid_decoder_config`、`invalid_truth`、`expected_read_failed` 等，`src/label_analysis.py:29`–`:37`、`src/analyze_label.py:25`–`:51`） |
| 读取一致性 | 关联层自定义 | **继续抛出**，不返回报告 | `source_changed_between_reads`（第 6.3 节） |
| 质量测量 | `QualityAnalysisError` | **转为**该测量的 `quality_error`，`quality` 置 `null`，**保留 QR**，顶层置 `completed_with_errors` | 沿用 `invalid_image` / `invalid_roi` |
| 质量测量 | `MemoryError`、`cv2.error` | **继续抛出** | — |
| QR 解码 | `MemoryError` | **继续抛出**（既有行为：`src/label_analysis.py:88`–`:89` 直接 re-raise） | — |
| 任何阶段 | 其他未预期异常 | **继续抛出** | — |

硬性规则：

1. **只有 `QualityAnalysisError` 会被转换成 `quality_error`。** 其余异常一律继续抛出。
2. **不得**用 `except Exception` 或裸 `except` 兜底；若确需捕获，必须列出具体异常类型。
3. **不得**把 `MemoryError`、`cv2.error` 或其他程序/资源错误解释为"图像质量问题"，
   也不得因此产出 `quality_error`，或把失败降级成成功。
4. QR 侧的 `execution_error` **不是异常**，而是 `decode_qr` 内部捕获后写入报告的**状态**
   （`src/label_analysis.py:90`–`:93`）。它必须作为状态原样保留，
   不得被关联层重新抛出、改写或当成"测量失败"。

### 6.7 三类耗时（契约 9）

`timings` 恰含三个字段，**分别定义、互不替代**：

| 字段 | 定义 | 是否含 I/O |
| --- | --- | --- |
| `decode_seconds` | `qr_report.attempts[].decode.duration_seconds` 之和 | 否（仅解码） |
| `quality_seconds` | `measurements[].duration_seconds` 之和 | 否（仅测量） |
| `total_seconds` | 组合函数入口到返回的墙钟时间 | **是**（含两次读图与校验） |

三者**不是**互斥分解：`total_seconds` 还包含两次读图 I/O 与校验开销。
`total_seconds >= decode_seconds + quality_seconds` 应成立（解码与测量在时间上不重叠），
但**不得**把它当等式，也不得据此反推某一项。

#### 6.7.1 注入式解码夹具契约

借鉴旧测试的注入位置，不照搬仅用于旧汇总函数测试的最小字典。
B06/B14 所用的解码夹具必须符合真实 `decode_qr` 的结构：
`status`、`symbols`、`error`、`decoder`、`config`、`duration_seconds` 全部存在；
symbol 字段依状态符合真实格式（decoded 时恰一有效 symbol，含 payload、文本、位置等）；
`config` 的 `try_downscale` 与当前 profile 一致，错误对象与状态一致。
`duration_seconds` 必须为有限、非负的 Python 数值；首选 `0.0`，避免虚构耗时破坏墙钟不等式。
严格按必需键求和，不得使用 `.get("duration_seconds", 0.0)` 或以零补缺。
夹具缺键属于测试构造错误，不得通过修改既有 QR 逻辑或放宽产品输出契约来适配。
夹具只能替代解码调用，不得直接伪造整个关联报告；conflict 由既有真实汇总逻辑产生。

### 6.8 影响文件与实施顺序（待授权）

| 文件 | 计划 | 是否本次创建 |
| --- | --- | --- |
| `src/quality_qr_analysis.py` | 新增：外围组合层，复用 `analyze_label` 与 `analyze_quality` | ❌ 待授权 |
| `tests/test_quality_qr_analysis.py` | 新增：B01–B18 对应验收测试（可**只读**加载冻结 oracle，见 6.8.1） | ❌ 待授权 |
| `docs/stage-36-quality-qr-association.md` | 新增：设计与验证记录（文档序号 36 = 现有最大 35 + 1） | ❌ 待授权 |
| `README.md` | 新增小节：关联模块能力与**不可声称的边界** | ❌ 待授权 |
| `docs/stage-34-project-capability-matrix.md` | 实测后更新能力行与受影响数字，**不预填成功结论** | ❌ 待授权 |
| `docs/tasks/phase-4.2-quality-qr-association.md` | 本文件；实施后回填第 7、8 节与状态行 | ✅ 本次创建 |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/README.md` | 本轮同步说明；功能实施阶段冻结 | ✅ 已创建，本轮修订 |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-2026-10-12.md` | 第 2/3 轮历史修订记录，本轮不改 | ❌ 不改动 |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/README.phase-4.2-baseline.md`、`stage-34.phase-4.2-baseline.md` | 两份可改文档的实施前逐字节副本；功能实施阶段冻结 | ✅ 本轮新增 |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/specification-review-snapshot.md` | 本轮规格候选快照，待用户审核；功能实施阶段冻结 | ✅ 本轮新增 |
| `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md` | 本轮最小修订记录、检查结果与摘要；功能实施阶段只读 | ✅ 本轮新增 |
| `protected-sha256.txt`、`qr-stable-fields-oracle.json`、`extract_qr_stable_fields.py` | **冻结基线**：本轮与实施阶段均**不得改动** | ❌ 不改动 |

**不改动**：`src/metrics.py`、`src/quality_analysis.py`、`src/analyze_label.py`、
`src/label_analysis.py`、`src/analyze_image.py`、`src/analysis_config.py`、
`src/label_evaluation.py`、`src/evaluate_labels.py`、QR/评测链路、CLI、
合成数据集与清单、`photo/` 与 `data/samples/` 原图、`data/reports/` 历史报告、`AGENTS.md`。

**实施顺序**：从用户确认的交付消息取得规格摘要，核对快照与不可变区段（4.3.0）→
核对最新工作区与保护对象哈希（4.3.1 + 4.3.2）→ 重算并比较证据 oracle（4.3.3，
**不覆盖冻结版本**）→ 实现组合层 → 逐条验收与反例检查 → 完整回归与真实 PNG 冒烟（4.3.4）→
更新文档 → 审查 diff（第 2 类文档须逐块审查）。

#### 6.8.1 批准的新增文件与证据依赖规则

**批准的新增文件**（4.3.2 的 `$approvedNew`，与本节表格一致）：

- `src/quality_qr_analysis.py`
- `tests/test_quality_qr_analysis.py`
- `docs/stage-36-quality-qr-association.md`

**证据目录的依赖规则**（与第 4.5 节一致，此处为实施约束）：

- **产品源码 `src/` 不得依赖证据目录**——不导入、不读文件、不拼路径。
- **验收测试可以只读加载**冻结的 `qr-stable-fields-oracle.json` 作为期望。
- **测试不得导入或执行** `extract_qr_stable_fields.py` 来生成期望。
- **实施者不得用新模块输出刷新 oracle**，也不得重新生成覆盖它。
- 提取脚本作为**证据工具保留在原地**：不移动、不删除、不改名，不引入产品依赖。

### 6.9 版本与源码摘要（契约 10）

`provenance` 至少含：

- `implementation_version`：关联模块自报版本，首版 `"quality-qr-association-1"`。
- `source_sha256`：至少覆盖
  `quality_qr_analysis.py`（自身）、`quality_analysis.py`、
  `analyze_label.py`、`label_analysis.py`、`analyze_image.py`、`analysis_config.py`、`metrics.py`。
- `quality_module_version`：`src/quality_analysis.py` **没有**版本常量，
  因此记为 `null`，并以其 `source_sha256` 作为身份标识。**不得**为了填这个字段去改质量模块。
- `runtime`：Python / OpenCV / NumPy / Pillow / zxing-cpp 版本。
- QR 侧自身的 provenance 保留在 `qr_report.provenance`，**不重复**一份。

严格 JSON：`json.dumps(result, allow_nan=False)` 必须成功且可回读。

### 6.10 风险、检测与回退

| 风险 | 检测方式 | 回退方式 |
| --- | --- | --- |
| 双读不一致被忽略，关联了两次不同读取的结果 | B01 注入式夹具；`read_consistency.checked_fields` | 抛 `source_changed_between_reads`，不放宽 |
| 把解码降采样图当作原图测量 | B16 记录实际输入数组/ROI，对最终测量像素独立比对；B04 数值对照 | 修正质量模块调用输入，不改质量模块 |
| 多 profile 重复测量或被计为独立样本 | B03 验证真实调用次数及记录唯一性 | 修正关联层调用与引用关系 |
| 正常 ROI 被二次裁剪却包装为测量错误 | B08 合法偏移 ROI 必须 completed、quality 非 null、quality_error 为 null；B04 对照 | 修正传参，不放宽异常契约 |
| 外层字段别名穿透改写 QR 子对象 | B05 修改外层 region 后整个 qr_report 与深拷贝相等 | 隔离新关联层可变对象，不改 QR 内部结构 |
| 质量测量失败被吞成成功 | B13 注入式夹具 + 顶层 `status` | 改为显式 `quality_error` + `completed_with_errors` |
| 笼统 `except Exception` 把程序/资源错误说成质量问题 | B18 异常分类；代码审查确认无兜底 except | 收窄到 `QualityAnalysisError`，其余继续抛出 |
| **B09 与允许修改的文档冲突**：把 `README.md` / `docs/stage-34-*` 也要求字节不变 | 第 5.5 节三类划分；4.3.1 的 `$mutableDocs` 白名单 | 修正比对规则，**不改基线清单** |
| 为了让比对通过而修改基线清单 | 4.3.1 校验清单条目数必须为 170、路径不得重复 | 恢复清单原样；改比对规则而不是改基线 |
| 实施时改动到既有 QR / 质量 / 指标模块 | B09 第 1 类逐项哈希 + 最终 `git diff` | 仅回退本次新增文件增量 |
| 误覆盖 Phase 4.1 的未跟踪产出 | 4.3.2 文件存在性检查 + 4.3.1 内容摘要 + 实施前重读 `git status` | 保留已有内容；不执行 `clean` / `reset --hard` |
| 改弱验证器或配置后假通过 | 4.3.1 补充工具/配置摘要 + 4.3.2 已跟踪修改范围 | 恢复本次越界改动，保留原有工作区内容 |
| 回填记录时改写验收条件 | 4.3.0 对用户确认快照比较，仅允许状态行及 §7/§8 正文变化 | 恢复契约或重新提交用户审核 |
| 输出覆盖历史报告 | 本模块**不写文件**；B09 | 无需回退；若将来加写盘，必须"仅新建" |
| 误刷新评测期望 | B10 闸门**不加** `--refresh` | 不刷新；期望变化须另行人工确认 |
| 重算 oracle 时覆盖冻结版本 | 4.3.3 **内存比较**：子进程按字节捕获提取脚本输出，不产生任何候选文件；比较前先核对冻结 oracle 的完整 SHA-256 | 从本轮的 SHA-256（第 5.6 节）确认未被改动 |
| 基线清单自身被改动却仍靠条目数通过 | 4.3.1 先核对清单**自身的完整 SHA-256**，再解析；条目数只作补充 | 恢复清单原样；改比对规则而非改基线 |
| 原生命令失败后被忽略，后续步骤继续用其输出 | 4.3 强制规则：每条原生命令紧后检查 `$LASTEXITCODE` | 补齐检查并停止，不得继续 |
| 证据目录被产品代码依赖 | 第 4.5 / 6.8.1 节依赖规则；代码审查 | 移除依赖；证据目录保持只读 |
| 测试只复述实现 | B04/B05/B07 用**独立调用**与**已保存的冻结 oracle**，不用关联模块内部输出 | 不放宽期望，回到契约定位差异 |
| 测试用提取脚本现算期望 | 第 4.5 节：测试不得导入/执行提取脚本 | 改为只读加载冻结 JSON |

**依赖**：现有 NumPy、OpenCV、Pillow、zxing-cpp、pytest 与项目 `.venv`；不安装新包，不申请提权。

**人工依赖**：用户确认本规格后才能开始代码修改。

### 6.11 关联层 warnings 契约（契约 5）

**首版 `warnings` 恒为 `[]`（空列表）。**

理由：关联层没有引入任何**新的、可证伪的**测量限制事实。Phase 4.1 的质量模块已经通过
`measurements[].quality.warnings` 表达其测量限制（`measurement_scope` / `constant_region` /
`insufficient_spatial_support`），既有 `analyze_label` 也通过 `qr_report.warnings` 表达解码限制。
关联层若再加警告，只会是未经审核的重复或推测。

因此：

- 关联层**不定义**任何 warning `type`，**不新增** `severity` 取值，**不设** warning 顺序表。
- 关联层**不合并、不重排、不改写**另外两处 warnings（见第 6.2 节的三处归属表）。
- 未来若要新增关联层 warning，必须**单独审核**，并在同一份审核里补齐全部四项：
  `type`（稳定字符串）、**触发条件**、`evidence` 的**完整字段清单**、
  `severity`（`info` / `warning`），以及它在 `warnings` 列表中的**固定位置**。
  **不得**在实施中临时扩展，也**不得**顺带加入。

对应验收：B17。

---

## 7. 实现记录（执行者填）

> 尚未实施。本任务**未授权**。

---

## 8. 验证记录（验证者填）

> 尚未实施。本任务**未授权**。

---

## 9. 观察（用户填写）

| 类别 | 观察 |
| --- | --- |
| A 理解：是否准确理解现有能力与 Phase 4.1 产出状态 | 待填写 |
| B 输出价值：规格是否提供可执行、可证伪的增量 | 待填写 |
| C 执行质量：实施返工情况 | 尚未实施 |
| D 验证质量：独立验收和反例是否发现有效问题 | 尚未实施验证 |

本次不访问或写入项目外的观察记录目录。

---

## 10. 修订历史

| 轮次 | 日期 | 范围 | 记录 |
| --- | --- | --- | --- |
| 第 1 轮 | 2026-10-12 | 初版规格 + 基线证据（清单 170 项、oracle 7 fixture、提取脚本） | — |
| 第 2 轮 | 2026-10-12 | 按用户审核意见 1–6 修订：B09 三类划分、证据依赖规则、oracle 内存比较、读取一致性措辞、warnings/异常契约（B17、B18）、状态与证据措辞 | `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-2026-10-12.md` |
| 第 3 轮 | 2026-10-12 | 原生命令退出码守卫、冻结摘要校验与证据措辞修正 | 同上 §4 |
| 第 4 轮 | 2026-10-12 | 按独立反例复核修订状态层次、夹具契约、验收实证、工具/配置保护、增量文档基线及规格冻结；仍未授权功能实施 | `docs/tasks/evidence/phase-4.2-quality-qr-association/revision-4-2026-10-12.md` |

**第 2 轮未改动**：`protected-sha256.txt`、`qr-stable-fields-oracle.json`、
`extract_qr_stable_fields.py`（SHA-256 见第 5.6 节，与本轮开始时一致）。
