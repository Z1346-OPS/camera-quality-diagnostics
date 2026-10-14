# Phase 4.2 任务证据目录

- 建立于：2026-10-12（**规格编写阶段**）；当前为同日**第 4 轮修订**，未授权功能实施
- 关联任务：`docs/tasks/phase-4.2-quality-qr-association.md`
- 代码基线：HEAD = `afdca8f43b66dcb8eca2b6280aebefd6215e4f03`
- 第 2/3 轮历史记录：`revision-2026-10-12.md`（本轮不改）；本轮记录：`revision-4-2026-10-12.md`

本目录是**证据**，不是产品代码、不是 `tools/`、不是 `src/`。

## 依赖规则（第 2 轮修订）

| 主体 | 允许 | 禁止 |
| --- | --- | --- |
| 产品源码 `src/` | — | **不得**以任何方式依赖本目录（导入、读文件、拼路径） |
| 验收测试 `tests/test_quality_qr_analysis.py` | 可以**只读加载**冻结的 `qr-stable-fields-oracle.json` 作为期望 | **不得**导入或执行 `extract_qr_stable_fields.py` 来生成期望 |
| 实施者 | 用**内存比较**的方式核对 oracle（见下） | **不得**用新模块输出刷新或覆盖 oracle |

理由：oracle 必须来自被测实现**之外**。测试**读取**一份冻结的外部事实是正当的；
让测试**运行**生成脚本、或让实现**回写**期望，都会把 oracle 变成被测对象的产物。

## 文件

| 文件 | 是什么 | 状态 |
| --- | --- | --- |
| `protected-sha256.txt` | 170 个保护对象的当前 SHA-256 清单（含 `.gitignore` 排除的 `photo/` 与 `data/reports/`） | **冻结**，实施阶段亦不得改动 |
| `qr-stable-fields-oracle.json` | 用**改动前**代码对 7 个固定夹具生成的 QR **稳定业务字段** | **冻结**，不得覆盖、不得重新冻结 |
| `extract_qr_stable_fields.py` | 生成上面那份 oracle 的证据工具 | **冻结**：不移动、不删除、不改名，不引入产品依赖 |
| `README.md` | 本说明 | 第 4 轮同步修订，功能实施阶段冻结 |
| `revision-2026-10-12.md` | 第 2/3 轮历史修订记录 | 本轮不改，摘要由规格 4.3.1 钉住 |
| `README.phase-4.2-baseline.md` | 顶层 README 的实施前逐字节副本，含 Phase 4.1 既有改动 | 本轮新建，功能实施阶段冻结 |
| `stage-34.phase-4.2-baseline.md` | 能力矩阵的实施前逐字节副本，含 Phase 4.1 既有改动 | 本轮新建，功能实施阶段冻结 |
| `specification-review-snapshot.md` | 本轮修订后规格的逐字节候选副本 | 待用户审核；功能实施阶段冻结 |
| `revision-4-2026-10-12.md` | 本轮修订、核验记录与产物摘要 | 本轮新建，功能实施阶段只读 |

冻结产物的 SHA-256（供确认）：

| 产物 | SHA-256 |
| --- | --- |
| `protected-sha256.txt` | `ecac1507047a21957bb6a323666145445e68e6368993d7625da27bf02ea46f95` |
| `qr-stable-fields-oracle.json` | `dd0738266f0fed5a3f910e02ca3fb9c82cb7cc3e922f8a8f311f3bcba8f732b4` |
| `extract_qr_stable_fields.py` | `c5dac7f0bb1acf618616a60028720cff38f30506cff7bca30fc1e73a2c032fac` |
| `README.phase-4.2-baseline.md` | `3c0b83fb047b3737a80ac111a444a668c2c09383f14cbb59cde2c62a373e54b7` |
| `stage-34.phase-4.2-baseline.md` | `b88cfc4114c6c11b6f520238844bc915e957f879ba676a6f0b9aa49adb2c9233` |

## 规格与可改文档的基线（第 4 轮）

完整检查顺序见规格 4.3.0–4.3.3。用户审核后，从交付消息取得规格摘要设置
`$approvedSpecSha`；4.3.0 先验证快照，再比较当前规格，仅允许状态行与 §7/§8 正文回填。
§9 是用户观察区，执行者不得修改。快照摘要不能由实施者即时计算后冒充审核值；
外部审核消息是版本锚点，不宣称仓库里的可写文件具备防篡改能力。

两份文档副本用于 `git diff --no-index` 比较 Phase 4.2 的增量，不能用相对 HEAD 的累计 diff
替代。副本摘要等于原 170 项清单对应摘要；副本本身不允许改动。
新增补充保护还涵盖评测闸门、生成器、CI 配置、requirements、.gitignore 和历史修订记录；
原清单仍为 170 项，不因补充检查而重写它。4.3.2 同时检查已跟踪修改与新增文件范围。
暂存不会被误判为原文件丢失；本任务仍禁止擅自 commit/push，HEAD 改变须重新审核基线。

## 这份证据能证明什么、不能证明什么

**能**：证明「本目录生成时刻**之后**」这些对象是否发生变化。这是 Phase 4.2 的**改动前基线**。

**不能**：**不能**补造 Phase 4.1 的历史前置证据。
本清单生成时，Phase 4.1 的产出（`src/quality_analysis.py`、`tests/test_quality_analysis.py`、
`docs/stage-35-*.md` 等）**已经存在且未提交**。因此本清单记录的是「Phase 4.2 开始前的工作区状态」，
**不是**「Phase 4.1 实施前的工作区状态」。任何把它当成后者使用的结论都是倒填。

**Phase 4.1 的准确状态**：功能测试通过（`pytest` 299 passed、评测闸门与入库期望一致），
但**历史资产保护验收仍有证据缺口**——`photo/` 只有 mtime 弱证据，`data/reports/`
被 `.gitignore` 排除、tracked 数为 0、无任何前置证据。这不是「全部验收完成」。

本目录**只填补「从现在起」的缺口**，对 Phase 4.1 之前的历史仍然无证据。

## 三份产物的提交状态

`protected-sha256.txt`、`qr-stable-fields-oracle.json`、`extract_qr_stable_fields.py` 与
本规格文件目前都是 **已保存但未提交**（`??`，不在任何 commit 里，也不在 HEAD 里）。
「已入库」的说法不准确，不得使用。

## 重新计算 oracle 并比较（**绝不覆盖冻结版本**）

**禁止**把提取脚本的输出重定向到 `qr-stable-fields-oracle.json`。
正确做法是**在内存里比较**：比较脚本自己以子进程运行提取脚本、按**字节**捕获其输出，
因此**不产生任何候选文件**，也**不可能**写到冻结路径。可直接执行：

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\Projects\Python\camera-quality-diagnostics'

@'
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(r"D:\Projects\Python\camera-quality-diagnostics")
FROZEN = ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/qr-stable-fields-oracle.json"
SCRIPT = ROOT / "docs/tasks/evidence/phase-4.2-quality-qr-association/extract_qr_stable_fields.py"

# Integrity of the FROZEN oracle itself, by full SHA-256.
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

> **编码说明**：上面的脚本刻意只用 ASCII。Windows PowerShell 5.1 对**无 BOM** 的 `.ps1`
> 按 ANSI 解码，中文会破坏字符串终止符（本机已实测）。若存成 `.ps1` 并加入非 ASCII 字符，
> **必须**保存为 **UTF-8 with BOM**；直接粘贴进控制台则无此问题。

脚本确定性：除 `generated_at_utc` 外，两次运行输出完全一致（已实测）。
脚本**只读**：不传 `--output`，不写项目文件。

## oracle 的比较规则

**文档级**唯一允许变化的字段是 `generated_at_utc`（生成时间）。

**报告级** volatile 路径已在**生成时**剥离，保存在 oracle 的 `volatile_paths` 里，**不比较**：

| volatile 路径 | 为什么允许变化 |
| --- | --- |
| `analysis_id` | 每次调用的随机 uuid4 |
| `analyzed_at` | 墙上时间戳 |
| `analysis_duration_seconds` | 耗时 |
| `provenance.git` | commit / working_tree_dirty / status 随提交变化（Phase 4.1 若先提交，commit 必变） |
| `attempts[].decode.duration_seconds` | 单次解码耗时 |

**任何不在上述白名单内的路径出现差异，均不得通过本基线比较。**
不接受「差异不大」「属于时间类」这类笼统豁免。

**环境适用范围**：同一项目路径与冻结 `.venv`，Python 3.12.10 / OpenCV 5.0.0 /
NumPy 2.5.3 / Pillow 12.3.0 / zxing-cpp 3.1.1。oracle 的运行库、解码器版本及绝对路径
仍参与比较，不加入 volatile 白名单。环境变更时报告范围不匹配，停止并另行审核；
不得直接判为业务回归，也不得通过重生成/放宽字段使其通过。

## 固定夹具覆盖的状态

| fixture | 状态 | 真值 |
| --- | --- | --- |
| `stage2_full_no_downscale` | decoded | correct |
| `stage2_roi_with_downscale` | full_image=decoded / roi=not_decoded | correct / not_decoded |
| `dev01_clean_decoded` | decoded | correct |
| `dev07_blur5_decode_error` | decode_error | decode_error |
| `dev08_blur8_not_decoded` | not_decoded | not_decoded |
| `test07_blur5_ambiguous` | ambiguous | ambiguous |
| `dev01_clean_no_truth` | decoded | **not_provided**（无独立答案，不得称正确） |

未覆盖 `conflict` 与 `execution_error`：合成数据集里没有自然产生这两种状态的固定样本。
验收测试必须在解码层注入**结构完整**的夹具覆盖，不得因为 oracle 里没有就省略。
借鉴旧测试的注入位置，不复制其中用于旧汇总测试的最小字典。必需字段为
`status/symbols/error/decoder/config/duration_seconds`；symbol、错误和 profile 配置遵守真实格式。
耗时为有限非负 Python 数值，首选 `0.0`；禁止缺键默认补零，细则见规格 6.7.1。

`conflict` 只在 `qr_report.decode_summaries[].decode.status` 断言：注入两个 decoded 的不同
payload，由真实汇总函数产生 conflict，关联表仍为 decoded。execution_error 是解码状态，
不转为质量错误。当前样本没有覆盖这两种状态，**不代表**真实场景不可能出现。

`decoded/not_decoded/decode_error/ambiguous` 的覆盖必须保留真实解码证据。
另允许 B06 恢复场景在解码层注入前次 decode_error、后次 decoded，核对失败记录与警告保留；
该注入不替代前述真实解码覆盖。decoded + incorrect 由真实固定 PNG 与另一份既有独立答案
验证，不生成新样本或改写答案。正向偏移 ROI 必须成功，测量调用次数、实际输入来源及
跨层可变引用隔离按 B03/B05/B08/B16 核验。
