# Phase 4.5 本地复验记录（2026-10-15）

本文件整理自当日已经执行的检查及原始日志；创建本文时没有重新运行测试。

结论：已执行范围内的核心功能复验通过，可进入验收收尾；真实符号链接测试受环境限制，仍未验证。Phase 4.5 未提交、未推送，未运行对应版本的远程 CI。

## 实际结果

| 检查 | 结果 | 退出码 |
| --- | --- | --- |
| 项目专项 | 23 passed, 1 skipped in 2.42s | 0 |
| DeepSeek 独立套件 | 49 passed, 5 skipped in 2.03s | 0 |
| Codex 独立反例 | 8 passed, 4 skipped in 0.34s | 0 |
| 完整 pytest | 477 passed, 1 skipped in 25.65s | 0 |
| 精确评测闸门 | development / test 均与入库期望完全一致；未 refresh | 0 |
| smoke-trial-003 | consistent；6 帧；逐帧值与旧接口对照一致 | 0 |
| smoke-trial-004 | consistent；2 帧；逐帧值与旧接口对照一致 | 0 |
| module-smoke | consistent；2 帧；逐帧值与旧接口对照一致 | 0 |
| 真实 junction 逃逸探针 | JSON / 两份 CSV / PNG 共 4 PASS，0 FAIL，0 SKIP | 0 |

## 限制与核对说明

- 所有跳过项均与真实符号链接无法创建有关（WinError 1314）。junction 是不同链接类型，不能把符号链接测试记为通过。
- 独立套件与项目测试分别报告，不相加作为项目测试数量。
- 复核的是已有 trial-003 / trial-004 产物；本轮未重新打开摄像头。
- 复验前后 292 个项目文件的 SHA-256 与文件集合一致，Git 状态一致。此比较发生在本文创建之前，不包含后来新增的本文。
- 项目未配置独立 build、lint 或类型检查；未安装额外工具。
- 默认 git diff --check 将 CRLF 行尾报为空白告警；git -c core.whitespace=cr-at-eol diff --check 通过。
- junction 探针复跑时，仅将副本的自动清理改为保留临时证据，并把临时目录设在仓库外；原探针文件未修改。
- csv_pairs 表示两份 CSV 彼此配对的键数；集合不一致时，不代表与任务声明匹配的帧数。
- 逐帧 csv.Error 应描述为当前静态输入流程未复现、并发改写属于声明范围外，不宜概括为实践不可达。

## 实际执行命令

工作目录：`D:\Projects\Python\camera-quality-diagnostics`。各检查使用项目 .venv；禁用字节码与 pytest 缓存，basetemp 在仓库外。

### project-targeted

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider -rs --basetemp C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0\targeted tests/test_review_capture.py
```

实际退出码：0。

### deepseek-independent

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider -rs --rootdir D:\harness\camera_review\phase45-review --confcutdir D:\harness\camera_review\phase45-review --basetemp C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0\deepseek-independent D:\harness\camera_review\phase45-review\test_phase45_independent.py
```

实际退出码：0。

### codex-independent

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider -rs --rootdir C:\Users\zex\.codex\visualizations\2026\10\12\01a12ed0-11d7-7d13-be87-0c4bd858475b\phase45-review --confcutdir C:\Users\zex\.codex\visualizations\2026\10\12\01a12ed0-11d7-7d13-be87-0c4bd858475b\phase45-review --basetemp C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0\codex-independent C:\Users\zex\.codex\visualizations\2026\10\12\01a12ed0-11d7-7d13-be87-0c4bd858475b\phase45-review\test_independent_contract.py
```

实际退出码：0。

### full-regression

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 -m pytest -q -p no:cacheprovider -rs --basetemp C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0\full
```

实际退出码：0。

### expectations

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 tools/check_evaluation_expectations.py
```

实际退出码：0。

### smoke-trial-003

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 src/review_capture.py D:\Projects\Python\camera-quality-diagnostics\data\reports\timed-capture\trial-003
```

实际退出码：0。

### smoke-trial-004

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 src/review_capture.py D:\Projects\Python\camera-quality-diagnostics\data\reports\timed-capture\trial-004
```

实际退出码：0。

### module-smoke

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 -m src.review_capture D:\Projects\Python\camera-quality-diagnostics\data\reports\timed-capture\trial-004
```

实际退出码：0。

### junction-probe

```powershell
D:\Projects\Python\camera-quality-diagnostics\.venv\Scripts\python.exe -B -X utf8 C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0\probe_junction_no_cleanup.py
```

实际退出码：0。

## 原始证据位置

```text
C:\Users\zex\.codex\visualizations\2026\10\15\01a13df0-98e2-72f3-b260-ccd645216690\phase45-acceptance-9232zdr0
```

该目录包含 summary.json、before.json、after.json 与各检查同名 .log。本文便于直接从项目目录阅读，原始证据保留。

## 交付前复验（2026-10-15，后续追加）

原始复验记录保留；用户授权继续未完成事项后，本轮仅收尾文档，没有修改源码、测试、依赖、CI、原图或冻结期望。

- 完整 pytest：477 passed、1 skipped，29.51 秒，exit 0。
- 精确评测闸门：两组均与入库期望完全一致，exit 0，未 refresh。
- trial-003 / trial-004 CLI：分别 6 / 2 帧，consistent，exit 0。
- 重新尝试沙箱内及沙箱外普通用户符号链接创建，均 WinError 1314；未使用管理员权限或改系统设置。
- 293 个项目文件中，完整复验前后只出现三份预定文档改动（README、能力矩阵、任务文档）；源码、测试和数据资产保持原字节。随后向本文追加这份结果，另计为有意文档改动。
- 新日志与命令清单在仓库外 `phase45-delivery-2dy4v6as` 证据目录；远程 CI 尚待推送后实际核验。

### 一次已有采集案例的使用流程

本轮复用了已有实机批次，没有重新打开摄像头。trial-003 的原任务配置为设备 0、30 秒、间隔 5 秒，实际记录 6 个完整样本；trial-004 为 10 秒、间隔 5 秒，实际记录 2 个完整样本。

复查 trial-003：

```powershell
.\.venv\Scripts\python.exe -X utf8 src\review_capture.py data\reports\timed-capture\trial-003
```

实际输出摘要：`verification_status=consistent`；`reported_samples=6`、`csv_pairs=6`、`verified_frames=6`；`issues=[]`、`warnings=[]`，exit 0。对应的 6 张 PNG 文件摘要匹配，五项当前算法重算值与 CSV 一致。

结果仅表示本次检查范围内的记录与文件一致；不能据此认定画面真实或相机工业合格。重新采集时必须为 run_capture.py 指定新的 output-dir，不能覆盖这两个历史目录。

## 远程交付结果（2026-10-15，后续追加）

以上“未提交／未推送／远程 CI 待执行”为当时状态，保留历史。后续已完成：

- 六个文件以功能提交 `66b05d655e7045aab71c5594723baf3684e8f379` 正常推送 origin/main。
- [GitHub Actions 38686222004](https://github.com/Z1346-OPS/camera-quality-diagnostics/actions/runs/38686222004) 精确对应该提交，ubuntu-latest，结论 success。
- 日志：`478 passed in 8.93s`，无跳过；development / test 两组精确评测闸门通过。
- 项目中的图片符号链接逃逸测试已在 Linux 通过；Windows WinError 1314 仍是本机限制。仓库外独立套件的 JSON/CSV 等符号链接参数化检查未在 CI 执行，不能声称全部链接测试已完成。
- 后续只追加此文档证据，不改源码、测试或工作流；后续文档提交的 CI 另以实际运行核验。
