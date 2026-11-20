# 开发日志归档

本目录是项目开发过程的原始记录，按时间保留。它**不是使用文档，也不代表当前能力**。当前的能力、结果与证据请看：

- [仓库首页](../../README.md)
- [亮点说明](../highlights.md)、[架构](../architecture.md)
- [公开验收汇总](../verification/acceptance-summary-2026-10-27.md)、[首页证据](../verification/stage1-readme-evidence-2026-11-19.md)

## 内容

| 位置 | 内容 |
| --- | --- |
| `stage-NN-*.md` | 按顺序编号的开发记录。NN 是文档序号，不是业务阶段号；`stage-0/1/2` 是早期的一位数编号 |
| `tasks/phase-4.*.md` | 各阶段的任务规格、验收条件和复核记录 |
| `tasks/evidence/` | 冻结证据与实验原始材料 |
| `tasks/delivery-candidate-*.md`、`tasks/release-review-*.md`、`tasks/real-use-acceptance-*.md` | 历史交付候选与验收记录 |
| `tasks/README.md` | 任务文件格式与案例 001 |
| 其他 | 早期设计、方向调整与使用指南；`project-guide.md` 是旧版 README 的详细内容 |

这些文件于 2026-11-20 从 `docs/` 和 `docs/tasks/` 移到这里，子路径保持不变，例如 `docs/tasks/phase-4.5-capture-review.md` 现在是 `docs/archive/tasks/phase-4.5-capture-review.md`。

## 阅读时请注意

- **数字只对当时成立。** 记录里的测试数、提交号和通过率，只对当时的提交和环境成立；当前数字以首页和公开验收汇总为准。
- **只做过两类机械修改。** 记录保持原文，结论没有改动：
  1. 移动后修正跨目录的相对链接。
  2. 把开发者本机的绝对路径替换为占位符：
     - `<仓库根>`：本仓库在开发者本机的根目录；
     - `<用户目录>`：开发者的 Windows 用户目录；
     - `<排查助手仓库>`：另一仓库 `test_failure_investigator` 的本机检出位置；
     - `<仓库外临时目录>`：仓库外的本机临时测试目录。
- **反引号里的路径是原位置。** 正文中反引号写出的 `docs/...` 路径，是记录写成时的原位置，不是链接，没有随移动改写。按上面的子路径规则，就能找到它现在的位置。
- **部分链接在克隆中打不开。** 有些记录链接到 `data/reports/` 下的本机证据，如 `tasks/real-use-acceptance-2026-10-16.md`。该目录不入库，所以克隆的仓库里这些链接打不开。
- **“助手”等称呼指当时的 AI 工具。** 记录中的“助手”“Codex”“DeepSeek”“Claude Code”，是指当时参与实现或复核的 AI 工具；分工见各记录正文。

## 冻结证据与摘要核对

- **`tasks/evidence/phase-4.2-quality-qr-association/protected-sha256.txt` 是 `afdca8f` 时的快照。** 它记录的是当时的工作区：HEAD 为 `afdca8f`，另有 7 项未提交改动，文件头部有说明。其中列出的 170 个路径和摘要指当时的文件，核对时请按原提交与原路径进行，例如 `git show afdca8f:<原路径> | sha256sum`，不要拿当前工作区的文件去比。文件头列出的那几项已修改或未跟踪的文件，当时的字节不在 git 中，无法这样还原。
- **该目录有 3 个文件仍被测试读取。** 它们是 `protected-sha256.txt`、`qr-stable-fields-oracle.json` 和 `extract_qr_stable_fields.py`，被 `tests/test_blur_experiment.py` 当作冻结资产：测试在实验前后计算它们的 SHA-256 并断言不变。移动这些文件时，必须同步修改测试中的路径。
- **有 3 份记录的 SHA-256 不再与当前字节一致。** 同一目录下的 `README.md`、`README.phase-4.2-baseline.md`、`specification-review-snapshot.md` 做过占位符替换。其他记录钉住的是它们的原始字节，应以 `120d8a3` 及原路径 `docs/tasks/evidence/phase-4.2-quality-qr-association/` 为准，例如：

  ```bash
  git show 120d8a3:docs/tasks/evidence/phase-4.2-quality-qr-association/README.phase-4.2-baseline.md | sha256sum
  # 3c0b83fb047b3737a80ac111a444a668c2c09383f14cbb59cde2c62a373e54b7
  ```

- **`README.phase-4.2-baseline.md` 中有 9 条链接在这里打不开。** 它们以 `docs/` 开头，是当时根目录 README 的快照原文，在归档位置无法直接打开，按“保持快照原文”保留，未修改。
