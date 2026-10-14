# Phase 4.3 固定矩阵模糊实验报告（development 组）

- 协议版本：`phase-4.3-blur-v1`
- 实验 ID：`development-20261013T081607Z`
- 组别：`development`（开发组与验证组分别执行、分别报告；验证组已在历史回归中出现，**不称盲测**）
- 状态：**完成**
- 本组条件数：10（2 张基图 × 5 个 sigma）
- 全实验规模：20 个条件 / 4 张基图；本报告只覆盖本组

本实验不输出准确率、通用阈值、故障原因或跨场景有效性结论。
σ=0 直接引用原图；σ>0 每次从原图独立生成，不串联叠加。
每个条件恰一条质量测量、两条解码尝试；**尝试数不是独立样本数**。

## 基图 `synthetic-qr-v1-development-01`

- 组别：`development`；尺寸 264×264；模块宽度 8 px
- 原图：`data/samples/synthetic-qr-v1/development/dev-01-clean-module8-A.png`（SHA-256 `9b1ff8d038e8beab…`）
- 独立答案：`data/samples/synthetic-qr-v1/development/answers/A.txt`

| σ | 清晰度 | 亮度 | 对比度 | 块间均值极差 | baseline 状态 | baseline 真值 | downscale 状态 | downscale 真值 | decode_summaries 汇总 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 7314.5661 | 198.8017 | 105.6992 | 127.3829 | decoded | correct | decoded | correct | decoded |
| 1 | 427.8173 | 198.8020 | 97.0086 | 127.3726 | decoded | correct | decoded | correct | decoded |
| 3 | 24.6820 | 198.8038 | 79.4538 | 126.1118 | decoded | correct | decoded | correct | decoded |
| 5 | 4.1663 | 198.8004 | 69.0409 | 124.3978 | ambiguous | ambiguous | ambiguous | ambiguous | ambiguous |
| 8 | 2.5135 | 198.7988 | 62.2924 | 123.0530 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |

> 「downscale 状态」是第二条 attempt 自身的结果，**不是**组合的最终结论；
> 最终汇总以 `decode_summaries` 列为准。完整四项质量输出见 `results.json`。

## 基图 `synthetic-qr-v1-development-02`

- 组别：`development`；尺寸 198×198；模块宽度 6 px
- 原图：`data/samples/synthetic-qr-v1/development/dev-02-clean-module6-B.png`（SHA-256 `6747837297057c7d…`）
- 独立答案：`data/samples/synthetic-qr-v1/development/answers/B.txt`

| σ | 清晰度 | 亮度 | 对比度 | 块间均值极差 | baseline 状态 | baseline 真值 | downscale 状态 | downscale 真值 | decode_summaries 汇总 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 10310.0551 | 199.2700 | 105.3818 | 144.4526 | decoded | correct | decoded | correct | decoded |
| 1 | 592.3368 | 199.2709 | 93.4846 | 144.2451 | decoded | correct | decoded | correct | decoded |
| 3 | 27.4337 | 199.2715 | 72.3500 | 140.0378 | decoded | correct | decoded | correct | decoded |
| 5 | 2.9069 | 199.2648 | 64.1928 | 134.8177 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |
| 8 | 2.3445 | 199.2667 | 58.9761 | 131.3969 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |

> 「downscale 状态」是第二条 attempt 自身的结果，**不是**组合的最终结论；
> 最终汇总以 `decode_summaries` 列为准。完整四项质量输出见 `results.json`。

## 本组状态计数

仅代表本组 10 个条件与 2 张基图；
全实验为 20 个条件与 4 张基图，本表不能外推。

| 层 | 状态 | 数量 |
| --- | --- | --- |
| baseline | ambiguous | 1 |
| baseline | decoded | 6 |
| baseline | not_decoded | 3 |
| internal_downscale_search | ambiguous | 1 |
| internal_downscale_search | decoded | 6 |
| internal_downscale_search | not_decoded | 3 |
| summary | ambiguous | 1 |
| summary | decoded | 6 |
| summary | not_decoded | 3 |

## 限制

- 只做固定矩阵的模糊实验，不含其他退化类型、多因素组合或 ROI 实验。
- 不要求清晰度或识读结果随 sigma 单调变化；每张基图只在本基图内部比较。
- 耗时沿用 Phase 4.2 的定义，本实验不新增性能统计体系。
- 全部结论限于本机、项目 `.venv` 与本次运行。
