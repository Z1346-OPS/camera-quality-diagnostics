# 摄像头报告与排查助手的联合复验

两个仓库通过 JSON 报告对接。此用例在摄像头项目的 Python 3.12 虚拟环境内运行，使用模拟设备、临时目录及固定合成 QR 样例。在 PowerShell 中将 `INVESTIGATOR_ROOT` 指向要核验的本地排查助手检出目录，再从摄像头项目根目录运行：

```powershell
$env:INVESTIGATOR_ROOT = 'D:\AIProjects\projects\test_failure_investigator'
$caseDir = Join-Path ([IO.Path]::GetTempPath()) ('camera-contract-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q tools/test_investigator_contract.py --basetemp $caseDir
Get-ChildItem -LiteralPath $caseDir -Recurse -Filter '*.md'
```

使用新的临时目录，因为 pytest 会清理已有的 `--basetemp` 目录。测试过程中，采集执行器生成任务报告，复核 CLI 和 QR CLI 生成 JSON，助手通过文件读取器导入，生成可查看的 `pending.md` 和 `restored.md`。默认的单仓测试独立运行。

| 输入顺序 | 预期结论 |
| --- | --- |
| 两帧正常 → 第 2 帧缺图 → 仅第 1 帧正常 → 最初正常报告重新排版 | 第 2 帧仍未解决；重排记录属于已有材料。 |
| 上述调查 → 同批次重新完整复核第 1、2 帧 | 范围内通过，交接说明与预览一致。 |
| 第 1、2 帧的 CSV 键不匹配 → 只核实第 3、4 帧 → 核实原来的第 1、2 帧 | 第二份材料证据不足，第三份材料允许关闭原问题。 |
| 同一 QR 对两份不同答案分别得到不匹配、匹配 → 后一报告缺少答案摘要 | 使用不同答案时不可比较；答案身份缺失时证据不足。 |

## 复核报告字段

`capture_task_review` v1 保持原字段含义。每次实际调用复核入口都会生成独立的 `review_id`（UUID 十六进制）并记录开始时间 `reviewed_at_utc`。判断恢复要求新复核的开始时间严格晚于问题记录，且证据覆盖同批次原对象。时间相同、时间倒退或执行身份缺失时保留证据缺口。执行编号和本机时间用于本地报告关联，不提供来源认证。

对于已完成的采集任务，`declared_frame_counts` 保存任务声明的全部帧号。CSV 键不匹配而提前停止时，`frames` 仍表示实际检查过的帧；`csv_key_differences` 分别列出质量和颜色 CSV 相对任务声明缺少、多出的 `[run_id, frame_count]` 键。未完成的任务不声明已核实的帧。

旧 v1 报告仍可导入查看。缺少复核身份或无法还原原始帧范围时，助手保留未解决状态。二维码内容复验还要求可比的区域及有效、一致的独立答案 SHA-256。
