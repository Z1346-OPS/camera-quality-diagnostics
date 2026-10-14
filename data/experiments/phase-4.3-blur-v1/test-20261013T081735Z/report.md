# Phase 4.3 固定矩阵模糊实验报告（test 组）

- 协议版本：`phase-4.3-blur-v1`
- 实验 ID：`test-20261013T081735Z`
- 组别：`test`（开发组与验证组分别执行、分别报告；验证组已在历史回归中出现，**不称盲测**）
- 状态：**完成**
- 本组条件数：10（2 张基图 × 5 个 sigma）
- 全实验规模：20 个条件 / 4 张基图；本报告只覆盖本组

本实验不输出准确率、通用阈值、故障原因或跨场景有效性结论。
σ=0 直接引用原图；σ>0 每次从原图独立生成，不串联叠加。
每个条件恰一条质量测量、两条解码尝试；**尝试数不是独立样本数**。

## 基图 `synthetic-qr-v1-test-01`

- 组别：`test`；尺寸 264×264；模块宽度 8 px
- 原图：`data/samples/synthetic-qr-v1/test/test-01-clean-module8-A.png`（SHA-256 `acb207f247997f52…`）
- 独立答案：`data/samples/synthetic-qr-v1/test/answers/A.txt`

| σ | 清晰度 | 亮度 | 对比度 | 块间均值极差 | baseline 状态 | baseline 真值 | downscale 状态 | downscale 真值 | decode_summaries 汇总 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 7553.4091 | 201.1433 | 104.0813 | 122.6997 | decoded | correct | decoded | correct | decoded |
| 1 | 438.1376 | 201.1440 | 95.0993 | 122.6915 | decoded | correct | decoded | correct | decoded |
| 3 | 24.3910 | 201.1464 | 77.2482 | 121.6552 | decoded | correct | decoded | correct | decoded |
| 5 | 4.0892 | 201.1405 | 66.7599 | 119.8783 | decode_error | decode_error | decode_error | decode_error | decode_error |
| 8 | 2.4330 | 201.1418 | 59.9402 | 117.9910 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |

> 「downscale 状态」是第二条 attempt 自身的结果，**不是**组合的最终结论；
> 最终汇总以 `decode_summaries` 列为准。完整四项质量输出见 `results.json`。

## 基图 `synthetic-qr-v1-test-02`

- 组别：`test`；尺寸 198×198；模块宽度 6 px
- 原图：`data/samples/synthetic-qr-v1/test/test-02-clean-module6-B.png`（SHA-256 `df50a3881a7c51ea…`）
- 独立答案：`data/samples/synthetic-qr-v1/test/answers/B.txt`

| σ | 清晰度 | 亮度 | 对比度 | 块间均值极差 | baseline 状态 | baseline 真值 | downscale 状态 | downscale 真值 | decode_summaries 汇总 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 10336.5932 | 200.6749 | 104.4111 | 126.6851 | decoded | correct | decoded | correct | decoded |
| 1 | 590.7771 | 200.6760 | 92.4997 | 126.6944 | decoded | correct | decoded | correct | decoded |
| 3 | 26.3924 | 200.6760 | 71.4992 | 124.5963 | decode_error | decode_error | decode_error | decode_error | decode_error |
| 5 | 3.0210 | 200.6711 | 62.8919 | 122.3881 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |
| 8 | 2.3207 | 200.6703 | 57.0269 | 119.8564 | not_decoded | not_decoded | not_decoded | not_decoded | not_decoded |

> 「downscale 状态」是第二条 attempt 自身的结果，**不是**组合的最终结论；
> 最终汇总以 `decode_summaries` 列为准。完整四项质量输出见 `results.json`。

## 本组状态计数

仅代表本组 10 个条件与 2 张基图；
全实验为 20 个条件与 4 张基图，本表不能外推。

| 层 | 状态 | 数量 |
| --- | --- | --- |
| baseline | decode_error | 2 |
| baseline | decoded | 5 |
| baseline | not_decoded | 3 |
| internal_downscale_search | decode_error | 2 |
| internal_downscale_search | decoded | 5 |
| internal_downscale_search | not_decoded | 3 |
| summary | decode_error | 2 |
| summary | decoded | 5 |
| summary | not_decoded | 3 |

## 限制

- 只做固定矩阵的模糊实验，不含其他退化类型、多因素组合或 ROI 实验。
- 不要求清晰度或识读结果随 sigma 单调变化；每张基图只在本基图内部比较。
- 耗时沿用 Phase 4.2 的定义，本实验不新增性能统计体系。
- 全部结论限于本机、项目 `.venv` 与本次运行。
