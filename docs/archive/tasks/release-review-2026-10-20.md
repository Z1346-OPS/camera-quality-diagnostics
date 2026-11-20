# 提交前代码与测试审查（2026-10-20）

## 目标与范围

判断现有测试成果是否可信、当前代码还有哪些可复现缺陷，以及本轮结项前需要处理什么。

被审查基线：`main`，HEAD `81b86e6d6b2b264890d2229e12856b7ef15b19ea`，加当前未提交工作区。取帧失败传播修正、Linux V4L2 后端适配均在工作区，不能说已进入 HEAD。

重点阅读图片标准化、QR 解码/汇总、清单评测、质量测量及关联层、定时采集、CSV/PNG 保存与离线复核，以及对应测试、CI 和交付记录。本轮属于有重点的人工审查，不是逐分支形式化验证或完整覆盖率测量。

本轮只新增本文；不修改业务源码、测试、依赖、CI、历史记录或精确期望，不提交、不推送。验证仅新建临时合成材料。撤销本轮文档只需移除本文；不要回退其他既有工作区改动。

## 结论

现有功能与回归资产已经具备练习项目的结项基础，建议完成下面的小范围修正和交付说明后冻结范围，不再为结项扩展服务化、数据库、故障诊断或新报告系统。

本轮没有观察到正式测试套件的断言失败，但额外探针复现了透明 PNG 处理错误、首次导出说明缺失，以及报告发布的并发覆盖窗口。默认 pytest 收集范围也会混入本机历史夹具。测试通过不能据此理解为没有缺陷。

## 本轮验证结果

| 检查 | 实际结果 | 解释 |
| --- | --- | --- |
| 正式 `tests/` 全套 | **497 passed、4 skipped，49.72s，exit 0** | 共 501 项，27 个测试文件；四项跳过均为 Windows 创建符号链接失败（WinError 1314），涉及 PNG、任务 JSON、质量 CSV、颜色 CSV |
| 精确评测闸门 | exit 0 | development/test 各 23 样本，与入库期望完全一致；未使用 `--refresh` |
| `pip check` | exit 0，`No broken requirements found.` | 仅证明当前环境没有声明依赖冲突 |
| 文档内合成复核演示 | 三种情况全部符合预期 | 正常 exit 0/consistent；缺图 exit 1/frame_unverifiable；指标差异 exit 1/metric_mismatch；输入摘要前后不变 |
| 默认根目录 pytest | 失败定位至历史夹具 | `CQD_PROBE_PATH must point at live_probe_v2/v3.py`；见问题 R2 |
| 透明 PNG 探针 | 两种模式均复现错误 | RGB/L 的透明黑像素预期白底亮度 255，实际 0.0 |
| 新导出目录探针 | exit 2/output_write_failed | 父目录不存在时不会自动创建；见问题 R3 |
| 报告发布并发探针 | 竞争写入的文件被替换 | 见问题 R4；仅操作本轮新建的合成文件 |
| Git 差异检查 | `git -c core.whitespace=cr-at-eol diff --check` exit 0 | 默认 `diff --check` 对能力矩阵 CRLF 行报告 trailing whitespace，识别 CR 行尾后无该告警；不应误当作业务错误 |
| 常见凭据模式检查 | 当前已跟踪文本未命中 | 检查常见 GitHub/API token、私钥头、AWS key 模式及常见凭据文件名；不覆盖 Git 历史，不是完整安全认证 |

正式测试使用项目 `.venv`，以新的项目内临时目录避开本机旧临时目录权限限制，并关闭 pytest 缓存插件；未改变任何测试或跳过条件：

```powershell
$reviewTemp = Join-Path (Get-Location) ('data/reports/release-review-pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests -q -rs -p no:cacheprovider --basetemp $reviewTemp
.\.venv\Scripts\python.exe -X utf8 tools/check_evaluation_expectations.py
.\.venv\Scripts\python.exe -m pip check
```

运行过程中的失败也保留说明：默认全套探索运行出现大量 setup errors 后主动中断；`-x` 明确定位历史夹具环境变量缺失。随后一次指定 `tests/` 的探索运行因给 basetemp 使用了未创建的嵌套父目录而报错并中断，`-x` 定位为 WinError 3；这是本轮命令准备错误，改用已有 `data/reports/` 下的直接新子目录后完成上述正式全套。不能把这些探索运行报告成全套通过，也不能把它们误算为产品断言失败。

## R1：透明色 PNG 未按白底合成（P2，建议结项前修复）

- 位置：`src/analyze_image.py:114` 附近 `has_alpha` 分支；`tests/test_analyze_image.py` 的透明度测试。
- 触发：8 位 RGB 或 L PNG 使用 `tRNS` 透明色，而不是 RGBA/LA 显式 alpha 通道。
- 实际：只把 RGBA、LA、带 transparency 的 P 模式视为透明图；RGB/L 的 transparency 被忽略。4×4 完全透明黑图在 Pillow 转成 RGBA 后 alpha=0，产品计算亮度却为 0.0。
- 预期：按现有文档的白底合成策略，应为亮度 255.0，且预处理记录应为 `alpha_over_white_then_RGB_to_BGR`。
- 影响：合法 PNG 的亮度、曝光比例、颜色均值和 QR 输入可能偏离既定预处理；`analyze_label`、质量与 QR 关联层共享此加载器。
- 测试缺口：现有用例覆盖 RGBA、LA、P，但没有 RGB/L 的透明色形式。
- 建议：透明性判断同时识别支持模式中的 `transparency` 元数据，再统一转 RGBA 白底合成；补 RGB、L 两类透明色回归，包含透明与不透明像素，确认普通 RGB/L 行为保持。
- 验收：上述透明样本输出白色；原图摘要不变；正式全套和精确期望闸门均通过。同步 README 与新的设计/验证记录；不要放宽精确回归期望。

独立复现方式（只新建合成文件）：

```python
from pathlib import Path
from tempfile import mkdtemp
from PIL import Image
from src.analyze_image import analyze_image

root = Path(mkdtemp(prefix="transparent-png-review-"))
for mode, color, key in [("RGB", (0, 0, 0), (0, 0, 0)), ("L", 0, 0)]:
    path = root / f"{mode}.png"
    Image.new(mode, (4, 4), color).save(path, transparency=key)
    with Image.open(path) as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0
    print(mode, analyze_image(path)["metrics"]["brightness"])
    # 当前输出两次 0.0；白底合成策略预期两次 255.0。
```

## R2：默认测试发现会收集运行产物（P2，建议结项前修复）

- 位置：项目根没有 pytest 收集范围配置；CI `.github/workflows/tests.yml:32` 和规则文档均执行根目录 `pytest -q`。
- 触发：本地被忽略的 `data/reports/` 中存在历史诊断脚本、`test_*.py` 或副本。Git 忽略不会阻止 pytest 递归收集。
- 实际证据：`data/reports/diagnostic-fixture-closeout-20261018-134204-c86ffa3b/fixtures/test_fixture_closeout.py` 被收集，因缺少 `CQD_PROBE_PATH` 在 fixture setup 报错。
- 影响：本地默认命令与干净 CI 克隆收集到的不是同一套测试；历史备用副本还可能造成模块同名冲突。
- 建议：在根 pytest 配置中设置 `testpaths = tests`，将产品回归的默认发现范围固定到 `tests/`。历史诊断夹具保留，确需验证时显式给路径及对应环境变量；不要删除、跳过或弱化产品测试。
- 验收：根目录默认命令和显式 `pytest tests` 收集相同的 501 项（后续新增回归后以新数字为准），本地报告目录内容不再影响默认发现；CI 仍运行产品全套与精确闸门。

## R3：首次导出缺少父目录准备步骤（P2，建议结项前修正）

- 位置：`README.md:32` 的合成 QR 示例；`src/analyze_label.py:120`、`src/analyze_image.py:218` 的独占新建输出。
- 触发：普通克隆没有被忽略的 `data/reports/`，用户直接按 README 运行首条带 `--output data/reports/...` 的示例。
- 实际：解码能够运行，但写 JSON 时返回 `output_write_failed`、exit 2。本轮以一个新的、父目录不存在的输出位置执行真实 QR CLI，复现该结果。
- 建议：最低成本是在快速开始中明确创建报告目录，然后使用新文件名。也可设计输出父目录自动创建行为，但须同步三个 JSON CLI 的契约并补测试，结项前不必扩大实现范围。
- 验收：在全新副本中，从安装依赖到合成 QR 导出可按说明连续完成；重复使用同一 JSON 文件名依然拒绝覆盖。不要为解决父目录问题改成覆盖写。

## R4：报告发布的存在性检查与替换之间有覆盖窗口（P2，条件性缺陷）

- 位置：`src/capture_task.py:407–420`，`_publish_report()`。
- 触发：目标最初不存在，在 `target.exists()` 检查后、`os.replace()` 前，其他进程或同步工具创建同名报告。
- 实际：`os.replace()` 会替换新出现的目标，与函数承诺的“目标已存在即拒绝”不一致。已有测试只覆盖调用前目标已存在。
- 本轮复现：用 `unittest.mock.patch` 包装 `os.replace`，在执行真实 replace 之前创建一份合成的竞争报告；发布返回成功，竞争报告被 JSON 替换。未触碰历史报告。
- 风险范围：一般单进程、独占新任务目录场景触发概率较低；不把它描述成正常采集必然丢数据。
- 建议：选择跨受支持平台的、不覆盖已存在目标的发布机制；保留完整写临时文件与首错优先语义。不要只多加一次 `exists()`，那仍有相同窗口。
- 验收：增加目标在最后发布瞬间出现的故障注入；拒绝覆盖并保留原目标字节，发布错误仍通过既有主错/附加错误规则暴露。

## 测试成果如何评价

现有测试并非只有导入和正常路径：已覆盖输入边界、逐字节真值、不匹配与歧义、执行失败、统计分母、分组泄漏、原图只读、输出不覆盖、首错优先、释放失败、任务与 CSV/PNG 关联、摘要及五项指标重算。合成回归不是浮动阈值，而是精确期望，本轮再次复现一致。

新增的默认工厂测试直接替换底层 VideoCapture，经真实工厂验证 grab/retrieve 的返回标记，而非只向 Runner 注入一个已返回失败的假对象；还检查成功黑图保留、原始像素不变、设备释放和离线复核。这些是有实际价值的回归资产。

仍需区分：

1. `test_r02_frame_metrics_match_existing_interface` 等测试把复核层与既有指标接口比对，能验证组合正确，但不能独立证明底层指标公式正确。现有手算常量/边界测试与历史独立测量记录应继续作为另一层证据。
2. 符号链接四项在本机跳过，不能计作本机通过；旧 Linux CI 的成功也不能替代当前未提交源码的 Linux 验证。
3. 2026-10-16 的实机结果是旧源码证据；2026-10-17 的实机记录先于 Linux 适配。当前 497+4 是自动化结果，不是新的实机验收。
4. 实拍 QR 14/18 是单一读出数量，无独立真值时不能写成正确率。合成 test split 的 21/23 也不能外推真实工业泛化能力。
5. 本轮没有安装覆盖率、lint 或类型检查工具，没有测行/分支覆盖率；不声称“覆盖完整”。

## 交付资料与 GitHub 收尾顺序

1. 先修 R1、R2，补齐 R3 的首次运行步骤；根据单写入者约定决定 R4 是否本次修正或作为明确已知限制保留。不要把本轮发现包装成已修复。
2. 更新当前交付入口。10 月 18 日文档可保留为历史快照，新增当前候选说明并让 README 顶部指向它：现有说明仍写默认仅 CAP_DSHOW、T13 新增 12 项，未包含 10 月 19 日的 8 个后端参数化用例，也未列 `docs/stage-38-linux-capture-backend.md`。
3. 将最新测试结果及其源码范围同步到 `docs/stage-34-project-capability-matrix.md`，保留旧日期的历史数字，分开写本机与远程结果；修正后的结果需重新测，不能直接沿用本文数字。
4. 在干净副本按 README 做离线冒烟；只取仓库应交付的源代码、合成材料与文档，不复制本机报告/实拍/虚拟环境。依赖安装与真实克隆复现本轮未重做。
5. 审阅最终 diff，确认新文档均被纳入、源码修正和测试成对提交。README 当前有大面积行尾差异，忽略行尾后实质改动仅 33 行量级；建议单独整理行尾，避免淹没审查内容。
6. 使用英文 conventional commit，按修正内容拆分提交；推送后核对**该具体提交**的 GitHub Actions。本文未查询最新远程状态，没有新的远程 CI 结论。
7. 当前提交的 CI 通过后再记录最终版本号/标签与支持范围。可以将本项目定义为“摄像头采集、图像质量测量、QR 评测及证据复核”的学习项目结项；真实故障自动识别、阈值标定、服务化仍属未实现范围。

若只交付已验证的 Windows 本机采集范围，不必为结项强行扩展 Linux 实机承诺；如要声明 Linux 摄像头支持，则必须另做 Linux 实机采集及复核。历史近黑画面的根因仍未确认。

## 证据身份

本轮正式测试对应以下源码字节，未来修正后应重新验证：

| 文件 | SHA-256 |
| --- | --- |
| `src/capture_task.py` | `1ee6a57292e15a56e944fad4818b9d654a9230b57b48f693d4ff53a489532a34` |
| `tests/test_capture_task.py` | `6b10e7c3c0676bddb54cf2a116032b09078c4b3371b5f94713c7d85ccb54a3c0` |
| `src/analyze_image.py` | `dd246c36102f5c02331e26ba3862e4bdc86d0114c683030f460d3d2560cda9cb` |
| `data/manifests/evaluation-synthetic-expectations.json` | `5ad8ef2b06ee3e43077eaf50faca8f4fd6d4461d5421a158b8985271bfb41a5d` |

合成探针产物与 pytest 临时文件仅本机：`data/reports/release-review-*`。文档三类复核演示本轮输出在 `C:\Users\zex\AppData\Local\Temp\capture-review-demo-1g7okez4`；上述路径不是普通克隆交付内容。

本轮未访问摄像头、未重新验证 Linux 设备、未修改历史图片/报告、未刷新期望、未暂存、未提交、未推送或发布。
