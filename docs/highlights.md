# 亮点说明

本项目的重点不在识别算法，而在让每个结论都能被独立核对。下面四节各讲一件事，每节给出：结论、触发条件、能抓住问题的测试或闸门，以及证据链接。凡是数字，都注明来源记录、提交与环境。

模块与数据流见[架构](architecture.md)；按时间保留的原始记录在[开发日志归档](archive/README.md)，阅读本页不需要进入归档。

## 1. Oracle 设计

**结论：读出内容不等于验证正确。只有当解码结果是单一有效码、且载荷与独立提供的答案逐字节相同时，才记为 `correct`。整个数据集的行为由逐样本冻结期望锁定。**

- **判定规则在代码里只有一处**：`src/label_analysis.py` 的 `check_expected()`。
  - 没有答案时返回 `not_provided`。
  - 有答案时，只有解码汇总为 `decoded`（多次尝试的有效结果一致）才比较 `payload_base64`，结果为 `correct` 或 `incorrect`。
  - `ambiguous`、`conflict`、`decode_error` 原样保留，不会被答案“救回”。
  - 答案文件由调用方独立提供，函数注释写明 “never decoder-derived”。
- **首页可以亲手验证**：同一张合成图，带答案是 `correct`，不带答案是 `not_provided`，两次退出码都是 0。见 [README 可运行示例](../README.md#可运行示例无需摄像头)和[首页证据 §2](verification/stage1-readme-evidence-2026-11-19.md#2-两次示例运行)。
- **冻结期望逐样本比对，而不是比总数**：
  - 闸门 `tools/check_evaluation_expectations.py` 按样本 ID 固定图片与答案的 SHA-256，再逐区域核对 `baseline` 和 `with_downscale_search` 的结果。
  - 只有 `--refresh` 会改写期望文件，脚本提示数值变化必须人工确认后随提交更新。
  - 精确比对，不设阈值，所以“变好了”也会被拦下，要求显式确认。
- **能抓住“总数不变、成败互换”的测试**：`tests/test_synthetic_dataset_expectations.py` 的 `test_synthetic_dataset_matches_expectations`。
  - 它先验证打乱行顺序不影响结果。
  - 再交换同组 01（清晰）与 07（模糊）样本的比较结果，并重算汇总计数，这时总数不变。
  - 最后断言闸门恰好报出这两个样本、两种方法的四处差异。
- **结果**：固定合成 QR 开发组、测试组各 23 张，每组 baseline 18/23，启用内部降采样搜索后 21/23，改进 3、退化 0。
  - 这些都是程序生成的固定样本；测试组参加过历史回归，不是盲测。
  - 数字绑定 CI 提交 `6dba7c7`（Ubuntu 24.04.5，Python 3.12.15），本地复核绑定代码版本 `0904038`（Windows 11，Python 3.12.10）。
  - 逐样本证据见[首页证据 §4、§6](verification/stage1-readme-evidence-2026-11-19.md#4-固定合成-qr-回归数字出处)。
- **出发点**：项目任务格式中写明，“新测试通过”不能当验收依据，因为测试由实现者写，等于实现者自己定 oracle（[`archive/tasks/README.md`](archive/tasks/README.md) 第 45 行）。

延伸阅读（开发日志）：[数据集与闸门的原始设计](archive/stage-33-synthetic-regression-dataset.md)。

## 2. 故障注入与可控环境

**结论：采集链路不依赖真实摄像头也能测。测试用假设备、可控时钟和故障注入，构造真实硬件上难以稳定复现的失败。缺陷 F01 就是这样被抓住、修复，并留下回归测试的。**

- **测试替身**：`tests/test_capture_task.py` 定义了 `FakeClock`（第 28 行）和 `FakeVideoCapture`（第 1235 行）。
  - `FakeVideoCapture` 的 `grab()` / `retrieve()` 返回真实标志，`read()` 则故意模仿 OpenCV 5.0.0 只看数组是否为空的旧行为。
  - 入口 `src/run_capture.py` 的 `main()` 接受注入的 `camera_factory` 与 `clock`。
- **F01：失败的取帧被计为成功**：
  - 触发条件：`grab()` 成功，`retrieve()` 返回 False，但输出数组非空（DirectShow 会预分配数组）。修复前，这次失败被当作有效帧，任务报告 `completed`。
  - 修复：`src/capture_task.py` 的 `_GrabRetrieveCamera.read` 分别检查两个返回值，任一失败就转入 `read_failed`。
  - 能抓住它的测试：`test_default_factory_retrieve_failure_is_read_failed`，辅助用例 `test_grab_retrieve_adapter_rejects_nonempty_array_on_retrieve_failure`。
  - 修复前后的记录见 [README 缺陷案例](../README.md#缺陷案例-f01失败的取帧被计为成功)和[首页证据 §5](verification/stage1-readme-evidence-2026-11-19.md#5-缺陷案例-f01-的修复前后记录)。
  - 结论边界：只修复了状态传播，不等于确认历史近黑画面的根因。
- **退出码契约区分业务结果与程序异常**：
  - 未读出、歧义、答案不匹配都是业务结果，不是异常。
  - 评测 CLI `src/evaluate_labels.py` 的退出码 2 有两种含义：一是批量结果中有 `decode_error` 或 `execution_error`，状态为 `completed_with_errors`，这时报告已写出；二是程序级失败，这时没有报告。
  - 闸门 `run_evaluation()` 接受退出码 0 和 2，再看“是否生成了报告 JSON”，没有报告就判失败。
  - 完整的退出码表见[架构 · 退出码](architecture.md#退出码)。
- **缺陷回放**：撤销 F01、F03、F07 的修复后，每个缺陷都至少有一条指定测试因该缺陷失败；恢复修复后通过。补丁、复现命令和失败输出见[测试策略与缺陷回放](testing-strategy.md#2-缺陷回放)。

延伸阅读：[F01 原始记录](archive/stage-37-read-failure-guard.md)。

## 3. 证据完整性

**结论：从原始像素到报告的每一环都能核对。原图前后有 SHA-256，复核时的摘要与指标重算用的是同一次读到的字节，报告用独占方式发布，不会覆盖已有文件。**

- **原图与样本只读**：
  - 受保护目录的 SHA-256 在每个阶段前后对比。
  - 冻结证据的测试 `tests/test_blur_experiment.py::test_original_assets_and_frozen_evidence_unchanged` 在实验前后对原资产逐一计算 SHA-256，并断言不变。
- **摘要与重算用同一份字节**：
  - 复核器 `src/review_capture.py` 的 `_review_frame` 只读一次留证 PNG，用这份字节同时计算 SHA-256，并通过 `png_bytes=` 传给 `compare_frame_metrics()` 重算指标。
  - 测试 `tests/test_review_capture.py::test_png_replacement_after_read_cannot_mix_hash_and_pixels` 在第一次读取后立刻替换文件，断言复核只读了一次，并且摘要与指标来自同一份字节。
- **报告独占发布**：`src/capture_task.py` 的 `_publish_report` 先独占新建临时文件并写完整，再用 `os.link` 硬链接到目标名。
  - 目标已经存在时，硬链接会失败，所以不会替换已有报告。
  - 文件系统不支持硬链接时，明确报错，不会退化成覆盖写。
  - 回归测试包括 `test_publish_refuses_target_created_after_initial_check`，它在初次检查后、发布前制造竞争报告；以及 `test_publish_link_error_preserves_temp_without_fallback`。
- **可复现演示**：[离线采集复核演示](capture-review-walkthrough.md)在临时目录里构造三种合成输入，展示复核器的不同结论：
  - 正常图片与记录：退出码 0，`consistent`；
  - 声明已保存的图片缺失：退出码 1，`inconsistent`，问题码 `frame_unverifiable`；
  - CSV 亮度被改为 101.0，而图片实际为 100.0：退出码 1，`inconsistent`，问题码 `metric_mismatch`。
- **历史实采**：2026-10-16，基线 `81b86e6`，Windows/DirectShow，3 轮 × 6 张留证图片，摘要与指标核对一致。这是历史设备验证，不是最终修正后的新实机验收，见[公开验收汇总](verification/acceptance-summary-2026-10-27.md#历史-windows-实采验收)。

延伸阅读：[发布修正的原始记录](archive/stage-39-release-review-fixes.md)、[采集复核验收记录](archive/tasks/phase-4.5-capture-review.md)。

## 4. 流程判断与如实报告

**结论：流程的作用包括否决不该做的任务、保留失败记录、照实呈现与预期不符的结果。**

### 哪项前提不成立：案例 001

- 2026-10-12 提出“给 `src/analyze_label.py` 加 `--json-only`，只输出 JSON”。
- 前提核验发现，这项能力已经存在，并且已有测试覆盖：
  - CLI 只有一处 stdout 写入，就是 JSON；
  - 失败信息走 stderr；
  - 被导入的模块不打印；
  - `tests/test_label_analysis.py` 有三处用 `json.loads` 解析 stdout。
- “需要关闭多余输出”这个前提不成立，任务作废。“前提核验”因此成为任务模板的必填项。
- 来源：[`archive/tasks/README.md` 案例 001](archive/tasks/README.md#案例-001--json-only-输出模式任务作废)。

### 首次 `3 failed` 如何记录

- 2026-10-20 的提交前修正中，第一次全套结果是 **3 failed、505 passed、4 skipped**。
- 原因：修复透明 PNG 改变了 `analyze_image.py` 的源码摘要，与历史 oracle 中的旧摘要不同。评测业务闸门仍然通过。
- 处理方式：
  - 没有覆盖历史 oracle，也没有 `--refresh` 期望；
  - 改为从当前源文件独立计算期望摘要，并新增篡改摘要的反例；
  - 最终结果为 508 passed、4 skipped。
- 记录表同时列出“第一次完整测试 3 failed”和最终结果，两者都保留。
- 环境：Windows 本地，修正尚未提交。
- 来源：[发布修正 §3、§4](archive/stage-39-release-review-fixes.md#3-冻结-oracle-的源码身份核验)。

### 降采样搜索新增恢复为 0 如何呈现

- 固定模糊实验：4 张基图 × σ∈{0,1,3,5,8}，共 20 个条件。
- baseline 与内部降采样搜索在全部 20 个条件中**逐一相同**，新增恢复为 0。
- 实验记录把这一点放在“不符合预想的结果（如实记录）”第一条，并写明：
  - 不能据此说降采样搜索对模糊普遍无效；
  - 只能说在本矩阵中没有出现恢复。
- 结果没有被删除，也没有用调参换取恢复，协议规定固定矩阵、不可调参。
- 来源：[模糊实验 §4.1](archive/tasks/phase-4.3-blur-experiment.md#41-不符合预想的结果如实记录)。
