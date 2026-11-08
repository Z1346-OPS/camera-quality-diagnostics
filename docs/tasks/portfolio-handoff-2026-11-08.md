# 摄像头质量异常复验与证据问答助手｜项目交接

交接日期：2026-11-08。两仓交付版本已在各自本地分支固定，提交号见第 2 节。采集问题详情查询 v1 已实现，原三份走查报告已通过现有桌面窗口、Python 查询和 Markdown 导出的联合核对。下一步是请目标用户独立完成一次交接，记录实际误读和求助点。

## 1. 总目标与目标用户

**目标用户**是负责摄像头或扫码终端回归验证的软件测试工程师。他接到一份异常报告和几份后续结果，需要决定原问题能否关闭，并向下一位接手人说明理由。

**项目目标**是核对后续证据是否覆盖同一批次、同一对象和可比的检查条件，给出问题状态、所依据的材料、仍缺的证据和下一步操作。首要成功标准是阻止漏验造成的误关闭，同时允许充分的复验关闭对应问题。

要区分两种验证任务。找回与原任务摘要匹配的图片，可以复核原批次的那一帧。修改采集程序后在新批次拍摄成功，只能作为新版本运行表现的证据。后者若要证明软件缺陷已修复，还需要版本、复现条件和单独的回归方案。

## 2. 两个仓库如何协作

| 仓库 | 职责与当前入口 | 本机分支与交付提交 |
| --- | --- | --- |
| `D:\Projects\Python\camera-quality-diagnostics` | 采集图像、测量质量、核验二维码、复核原图并输出报告。主要入口为 `src/run_capture.py`、`src/review_capture.py`、`src/analyze_label.py`。 | `main`，`c20feeafe28616d2a3269ccbd82085bbb22e5122` |
| `D:\AIProjects\projects\test_failure_investigator` | 只读导入报告、比较后续材料、查询单个采集问题并导出交接说明。桌面入口为 `src/run_investigator.py`，Python 入口为 `Session.get_issue_details`。 | `experiment/multi-agent-fault-benchmark`，`9a7eb914355c327d999948d8c193a916f6780dce` |

两仓通过三种报告对接：`camera_timed_capture` v1、`capture_task_review` v1、`label_baseline` v2。采集复核支持逐问题的发现、关闭和重新出现；QR 已支持图片、区域与独立答案的前后比较。第一版问题详情查询优先覆盖采集复核。

## 3. 主案例与判定表

| 接手时看到的材料 | 应得出的结论 | 下一步 |
| --- | --- | --- |
| 批次 A 的第 2 帧原图无法核实；后续正常报告只核实了第 1 帧 | 后续报告在自己的检查范围内正常，第 2 帧仍未解决 | 索取同批次、覆盖第 2 帧的新复核 |
| 故障前的正常报告只改了 JSON 排版 | 同一次执行，没有新增复验证据 | 保留已有问题和历史 |
| 晚于异常的独立复核覆盖原第 2 帧，图片摘要和五项指标均一致，比较条件完整 | 第 2 帧的问题在本次核实范围内可关闭 | 交接说明中保留原失败和支持关闭的新报告 |
| 第 1、2 帧有批次级 CSV 配对异常，新报告只核实第 3、4 帧 | 数量相同仍不足以覆盖原范围 | 按原声明帧号补查 |
| 同一二维码更换了独立答案，或报告遗漏答案摘要 | 不同答案不可比较；答案身份缺失时证据不足 | 核对独立答案来源、摘要和区域 |

## 4. 实施进度与验证依据

| 工作项 | 状态 | 交付情况 |
| --- | --- | --- |
| 摄像头测量、留证和单图 QR 分析 | 已实现 | 可从原图重算指标，保留区域、解码配置及独立答案核验结果 |
| 调查、局部复验和交接导出 | 已实现 | 桌面界面可导入报告、追加结果、查看未解决问题、预览并保存说明 |
| 联合演示和审查修复 | 双仓提交已固定，干净检出复验通过 | 已验证执行编号与时间、原帧号覆盖、QR 答案摘要、同一份 PNG 字节核对、报告父目录联接及文件替换检查 |
| Python 问题详情 | v1 已验证 | 返回问题状态、逐次判断、来源摘要、完整核实帧集合、执行身份及缺失项。新导出列出各次复核的编号与开始时间。 |
| 真人走查 | 待执行 | 主持人材料已备齐。已有两个独立 AI 会话的阅读记录，尚无真人操作记录。 |
| AI 依据问答与本地 HTTP | 备选阶段 | 已完成方案调研，尚无模型对照结果、推理耗时或独立 HTTP 调用示例 |

在 Windows 本机使用两个项目原有的 Python 3.12.10 虚拟环境复验。摄像头完整测试 **509 通过、4 跳过**，助手完整单测 **163 通过、1 跳过**，跨仓回归 **2 通过**，Tk 冒烟 **161/161 个检查点通过**，另有 8 项 Tk 专项回归通过。5 项跳过均涉及 Windows 符号链接权限。QR 的 development 和 test 各 23 个样本，结果均与入库期望完全一致。联合验证使用模拟设备和合成材料。

摄像头首次从 `aa77a72` 干净检出时，全量测试为 1 失败、508 通过、4 跳过。`test_qr_stable_fields_oracle` 检出参考脚本的 SHA-256 不符，原因是 Windows 将 168 个 LF 换成了 CRLF。交付提交 `c20feea` 为该脚本固定 LF；再次干净检出后，原冻结摘要与单项、全量测试均通过。

## 5. 接手第一步：重跑联合演示

在拥有两个本地仓库的 Windows 账号下运行以下 PowerShell 命令。命令新建两个临时检出，使用摄像头项目现有的虚拟环境运行联合用例。第 2 节给出的提交号也可用于核对其他复现环境。

```powershell
$cameraRepo = 'D:\Projects\Python\camera-quality-diagnostics'
$assistantRepo = 'D:\AIProjects\projects\test_failure_investigator'
$pair = Join-Path ([IO.Path]::GetTempPath()) ('camera-handoff-' + [guid]::NewGuid().ToString('N'))
$camera = Join-Path $pair 'camera'
$assistant = Join-Path $pair 'assistant'
$caseDir = Join-Path $pair 'results'
$null = New-Item -ItemType Directory -Path $pair -ErrorAction Stop
git clone --quiet --no-hardlinks --no-checkout $cameraRepo $camera
if ($LASTEXITCODE) { throw '摄像头仓库复制失败' }
git -C $camera checkout --quiet --detach c20feeafe28616d2a3269ccbd82085bbb22e5122
if ($LASTEXITCODE) { throw '摄像头交付提交检出失败' }
git clone --quiet --no-hardlinks --no-checkout $assistantRepo $assistant
if ($LASTEXITCODE) { throw '助手仓库复制失败' }
git -C $assistant checkout --quiet --detach 9a7eb914355c327d999948d8c193a916f6780dce
if ($LASTEXITCODE) { throw '助手交付提交检出失败' }
$env:INVESTIGATOR_ROOT = $assistant
Push-Location -LiteralPath $camera -ErrorAction Stop
try {
    & (Join-Path $cameraRepo '.venv\Scripts\python.exe') -B -X utf8 -m pytest -q tools/test_investigator_contract.py -p no:cacheprovider --basetemp $caseDir
    if ($LASTEXITCODE) { throw '跨仓复验失败' }
    Get-ChildItem -LiteralPath $caseDir -Recurse -Filter '*.md'
} finally { Pop-Location }
```

预期有两项跨仓测试通过。打开 `pending.md` 和 `restored.md`：前者应保留第 2 帧的问题，后者应说明新证据已覆盖第 2 帧，并保留旧失败。测试也会核对导出文件与预览一致。更详细的输入顺序和字段定义见[联合复现指南](investigator-contract.md)。

## 6. 走查与 Python 查询

**2026-11-08 接手续记。** 两轮[主持人走查单](capture-trial-2026-11-08/host/走查.md)、[参与者任务卡](capture-trial-2026-11-08/round-1/任务.md)及三份脱敏合成报告已就绪。按发放顺序在同一调查中实际导入，第一轮仍有第 2 帧未解决，第二轮才得到“范围内通过”。两份示例均由助手实际导出。真人走查待执行，项目维护者可从主持人走查单开始。

1. **试用材料已备齐。** 两轮材料随摄像头交付提交入库。主持人先单独给出 `round-1`，待参与者保存第一轮说明再给 `round-2`。每轮只问“这项异常能关闭吗？请写一句话交给下一位同事”。主持人留存答案和匿名记录单。
2. **邀请 1～2 位未参与开发的人独立操作。** 优先邀请实际做回归验证的测试人员；如由同学代试，记录其背景。观察是否误关闭、能否找到证据、能否说出下一步，以及接手人只读交接说明能否继续。分别记录用时和求助点。已有材料可复用助手仓库中的 `docs/first-guide-and-trial-plan.md`。
3. **采集问题详情查询已实现。** `session.get_issue_details(investigation_id, issue_id)` 返回当前调查中的问题快照。助手仓库 `docs/capture-issue-query.md` 有可直接运行的两轮示例和错误约定。报告自身结论、相对主报告的比较结果、问题当前状态分别表达。
4. **已完成技术验收。** 第一轮返回 `open`，补充记录的说明写出 `verified_frame_counts=[1]`。第二轮返回 `closed_in_scope`，说明写出 `verified_frame_counts=[1, 2]`，并用 `frames[1] → 帧 2` 定位原报告记录。两轮均在现有 Tk 窗口核对查询、预览与保存的说明。定向回归另覆盖仅核实第 2 帧、重复导入、旧版缺身份、相同时间、不同批次、缺失或未知编号、矛盾记录及关闭后重新出现。[第一轮脱敏导出](capture-trial-2026-11-08/host/verified-frame-counts-round-1.md) · [第二轮脱敏导出](capture-trial-2026-11-08/host/verified-frame-counts-round-2.md)

这一步的交付件是匿名走查记录、Python 查询契约、回归用例和一份脱敏交接样例。未经真人操作，走查项保持待完成。

## 7. 后续扩展的启动条件

- **AI 依据问答**：从走查中选取参与者实际提出的问题，用同一批事实比较规则说明和模型回答。程序生成状态和证据编号；模型只生成说明、引用和建议。验收时检查引用是否真实支持回答、是否遗漏未解决项、是否擅自推断硬件根因，以及用户是否更容易判断下一步。超时或依据不足时继续提供规则说明。
- **本地 HTTP API**：出现网页或独立脚本调用需求后，再提供建立调查、追加报告、列出问题、查询详情、提问和导出交接等操作。客户端提交报告内容，沿用导入校验，查询结果复用 Python 契约。业务上的“证据不足”是有效响应；报告损坏或调查不存在属于接口错误。
- **单独排期的候选项**：固定 QR 数据集按样本身份锁定期望、扩大独立实拍样本、测量额外搜索耗时。它们有独立的验收价值，不是完成本轮交接或开始用户走查的前置条件。
