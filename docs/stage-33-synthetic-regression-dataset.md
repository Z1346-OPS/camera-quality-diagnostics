# 文档 33：合成回归数据集——从单案例验证到可持续回归验证

> 编号 `33` 是**文档序号**，不代表业务阶段（见 `AGENTS.md` 的文档编号规范）。

- 日期：2026-10-12
- 相关提交：`3e30a19`（数据集）、`eaca762`（期望闸门）
- 本文记录**设计过程、实验证据与边界**；使用说明见 `README.md`，不在此重复

## 0. 背景：为什么需要合成数据

在此之前，唯一能证明「基线失败 → 内部降采样搜索救回」的证据是**一次实拍**：

| 事实 | 值 |
| --- | --- |
| 源图 | `photo/A7.jpg`（4096×3072 手机实拍打印件） |
| 二维码在照片中的尺寸 | `position_region` 约 2300×2300 像素（每模块 ≈ 92 px） |
| 基线结果 | `decode_error` |
| 降采样搜索 | `decoded`，`truth_check.status = correct`（`exact_payload_bytes`） |
| 结果文件 | `data/reports/qr-A7-downscale-001.json` |

问题很明确：这张照片**进不了 Git**（`/photo/` 被 `.gitignore` 忽略，且可能含私人画面），所以这条旗舰能力**无法被 CI 回归**。改代码时没有任何东西能告诉你「降采样能力还在不在」。

## 1. 初始假设（错的）

第一版假设：**扩大背景比例**（大画面 + 小二维码）就能让基线失败、让降采样搜索获益。

| 样本 | 二维码占比 | 实测结果 |
| --- | --- | --- |
| 200 px 二维码 / 1600×1200 画布 | 2.1 % | baseline **decoded**（未触发） |
| 320 px 二维码 / 1600×1200 画布 | 5.3 % | baseline **decoded**（未触发） |
| 上述两者 + 轻微高斯模糊 | — | baseline **decoded**（未触发） |

第一版数据集（20 样本/split）因此**完全没有覆盖降采样路径**：`paired_change.improved = 0`，两条 profile 的结论逐样本相同。**数据集存在不等于覆盖到位**——这是本轮最重要的教训。

## 2. 修正模型

回到 A7 的数据才发现模型反了：A7 的二维码**占了约 2300×2300 像素**（每模块 ≈ 92 px），是「**二维码极大 + 真实拍摄噪声**」，与「小」正好相反。

修正后的触发条件是：**每模块像素尺寸大 + 传感器噪声**（通常还需要 JPEG 压缩参与）。

| 实验配方 | baseline | 降采样搜索 | 汇总（选中 attempt） |
| --- | --- | --- | --- |
| module 24 + 噪声 σ25 + JPEG q50 | `not_decoded` | `decoded` | decoded（1） |
| module 48 + 噪声 σ20 + JPEG q60 | `not_decoded` | `decoded` | decoded（1） |
| module 48 + 噪声 σ35 | `not_decoded` | `decoded` | decoded（1） |
| module 48 + 透视 0.04 + 噪声 σ25 + q50 | `not_decoded` | `decoded` | decoded（1） |
| module 48 + 模糊 σ2 + 噪声 σ15 + JPEG q40 | `not_decoded` | `decoded` | decoded（1） |

另外实测：**画布大小不影响结论**——2048×2560（3.54 MB）与 896×1120（0.68 MB）给出完全相同的 profile 结论，因此采用最小画布控制仓库体积。

## 3. 数据集设计

生成脚本：`tools/generate_synthetic_samples.py`（确定性；不含随机参数，噪声用固定种子）。

### 受控退化矩阵（每个 split 23 个样本）

| 条件 | 数量 | 强度 |
| --- | --- | --- |
| `clean` | 2 | 每模块 8 px / 6 px |
| `downscale` | 3 | 缩到 160 / 96 / 64 px |
| `blur` | 3 | 高斯 σ 3 / 5 / 8 |
| `brightness` | 3 | α0.55β25 / α0.75β40 / α1.35β−30 |
| `rotation` | 3 | 8° / 15° / 25° |
| `jpeg` | 3 | q30 / q15 / q8 |
| `occlusion` | 3 | 居中白块 12 / 20 / 28 px |
| `noise-large` | 3 | module 24 + 噪声 σ25/σ22 + JPEG q50/60 + 透视 0.04 |

### 与评测器契约的对齐（`src/label_evaluation.py`）

| 契约 | 处置 |
| --- | --- |
| 样本 8 个必填字段 + 4 个可选字段，**未知字段直接报错** | 退化条件**不新增字段**，写进 `source` 文本 |
| 真值必须 `expected_file` + `expected_sha256` + `truth_source` 三件套齐全 | 每个 split 每个载荷一份答案文件（内容 = 载荷字节，无换行） |
| 同一 `label_id` / `batch_id` / `expected_sha256` 不得跨 split | 载荷按 split 完全不相交：`SYNTH-DEV-A..D` 与 `SYNTH-TEST-A..D` |
| 图片 sha256 会被实际复算比对 | 图片入库；哈希由脚本按**实际写出的字节**计算，重跑得到自洽的图片+清单对 |
| 同一原图（哈希）只能列一次 | 每个样本退化参数互不相同，哈希天然唯一（脚本内自检） |

### 体积

| 项 | 值 |
| --- | --- |
| 图片 | 46 张，合计 4.23 MB |
| 其中 `noise-large` | 6 张 ≈ 4.1 MB（每张 ≈ 0.7 MB，高噪声 PNG 难以压缩） |
| 答案文件 / 清单 | 8 个 txt + 2 份清单 |

> 注意：每次重新生成都会在 Git 历史里再存一份 ≈4 MB 的二进制。数据集**稳定后不要反复重生成**；要改条件就改脚本 + 一次性重生成。

## 4. 评测结果

| split | 样本 | 基线 | 降采样搜索 | paired_change | status |
| --- | --- | --- | --- | --- | --- |
| `development` | 23 | 18/23 | 21/23 | improved=3 degraded=0 | `completed_with_errors` |
| `test` | 23 | 18/23 | 21/23 | improved=3 degraded=0 | `completed` |

仍然无法读出的（每 split 仅 2 个，全部是最重的模糊）：

| 样本 | 条件 | 基线 / 降采样 |
| --- | --- | --- |
| `dev-07` / `test-07` | blur σ5 | `decode_error` / `ambiguous`（两次尝试结论一致） |
| `dev-08` / `test-08` | blur σ8 | `not_decoded`（两次尝试结论一致） |

**这不是"识读率"，是受控样本上的行为记录**：23 个样本里有 3 个在基线与降采样之间存在精确可复现的差异，这正是回归闸门要盯住的东西。

## 5. CI 接入与期望闸门

```
evaluate_labels.py  →  报告 JSON  →  check_evaluation_expectations.py  →  CI pass/fail
```

### 为什么不能用退出码

`src/evaluate_labels.py` 对**两种情况都返回 2**：

| 情况 | 含义 | 退出码 |
| --- | --- | --- |
| `EvaluationError` / `OSError` / `MemoryError` | 程序故障 | 2 |
| `status == "completed_with_errors"` | **业务结果**（有样本按预期读不出） | 2 |

直接把这个命令写进 CI，会把「2 个最难模糊样本没读出来」这个**正常业务结果**判成构建失败——恰好违反 `AGENTS.md` 的「区分业务结果与程序异常」。所以闸门**不看退出码，只看报告 JSON**。

### 闸门规则

- 比对项：`status`、样本数、每个 method 的 9 个 outcome 计数、正确率分母、`paired_change` 四项
- **精确值比对，不是阈值**：不写成「失败数 ≤ N 就通过」
- `--refresh` 才会改写期望文件，且必须**人工确认后随提交更新**
- 因此闸门**在改善方向也会拦住你**：如果将来 σ5/σ8 也能读出，`improved` 变化会失败并要求显式确认——这是刻意的，项目对数据集行为的声明必须是有意识更新的

### 闸门自身的验证（双向）

| 方向 | 操作 | 结果 |
| --- | --- | --- |
| 正向 | 与入库期望比对 | 一致，exit 0 |
| 反向 | 人为把 `test.paired_change.improved` 从 3 改成 0 | `❌ paired_change.improved: 期望 0，实际 3`，exit 1 |
| 恢复 | 还原并校验 SHA-256 | 一致，无污染 |

### 落地位置

| 位置 | 作用 |
| --- | --- |
| `tools/check_evaluation_expectations.py` | 闸门本体（可 `--split`、可 `--refresh`） |
| `tests/test_synthetic_dataset_expectations.py` | pytest 包装（2 个用例）→ 本地跑 `pytest` 即可发现漂移 |
| `.github/workflows/tests.yml` | 显式闸门步骤 → CI 日志里可见 |
| `data/manifests/evaluation-synthetic-expectations.json` | 入库的精确期望值 |

测试规模随之从 283 项变为 **285 项**。

## 6. 环境差异经验（两个方向的真实案例）

两个案例方向相反，合起来说明「为什么必须同时有本地验证和 CI 验证」。

| 案例 | 谁发现 | 原因 | 处置 |
| --- | --- | --- | --- |
| venv 假设（Phase 2） | **只有 CI** | 测试断言「必须运行在虚拟环境内」，而 `actions/setup-python` 给的是全局 toolcache Python | 不改测试（`AGENTS.md` 禁止弱化测试），改为在 workflow 里创建真实 venv |
| GBK 解码（Phase 3.2） | **只有本地** | 闸门用 `subprocess.run(..., text=True)` 未指定编码，在中文 Windows 上按 GBK 解码子进程的 UTF-8 输出（含中文 `source` 字段）而崩溃 | 显式 `encoding="utf-8", errors="replace"`；Linux CI 的 locale 是 UTF-8，永远不会暴露它 |

前者说明**本地为真的假设不等于普遍为真**；后者说明**CI 为绿不等于本地没问题**。

## 7. 边界（本数据集不能用来声称的事）

- 不能声称任何**识读率 / 准确率**：`test` split 只有 23 个受控合成样本，且它们来自 4 个载荷
- 不能声称**泛化能力**或**工业场景有效性**：合成样本只覆盖程序**主动施加**的退化，其中 `noise-large` 是模仿真实拍摄形态，而不是真实采集
- 不能把 `development` 的 `completed_with_errors` 说成「失败」：它是有意的难样本，且其期望值已入库
- 真实采集方向的证据仍然只有 `photo/` 下的少量实拍（A7 等），**该部分不进 Git、不进 CI**

## 8. 下一步（不在本文范围）

- 扩大**真实**采集样本（受控光照/距离/角度的实拍），仍走 `source_kind=phone_photo` 通道
- 若将来需要「按退化条件分组统计」，需要给清单加结构化条件字段——那是**代码契约变更**，必须同时改 `label_evaluation.py`、测试与文档，并重新走一遍本流程
