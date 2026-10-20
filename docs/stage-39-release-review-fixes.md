# 文档 39：提交前审查问题修正

日期：2026-10-20。承接 `docs/tasks/release-review-2026-10-20.md`；本文记录修正，不改写该次审查或旧交付快照。

## 1. 目标、范围与回滚

在保留既有未提交取帧防护和 Linux 适配的基础上，修正透明 PNG、默认测试发现、首次导出步骤、报告并发覆盖四项问题。未扩展工业诊断、重连、数据库或服务化。

修改 `src/analyze_image.py`、`src/capture_task.py` 及对应测试，新增 `pytest.ini`，同步 README、AGENTS、能力矩阵及当前候选说明。旧报告、原图、合成样例、评测期望和历史 oracle 不改写。报告 schema、原有字段含义、指标公式和实现版本字符串不变；精确源码身份由新的 SHA-256 表达。

README 行尾恢复为 HEAD 的 CRLF，既有用户内容保留，避免整文件行尾变更掩盖正文差异。保护文件摘要比对的 75 个原图/样例/清单文件全部保持原字节；源码与测试的最终摘要保存在本机运行目录的 `final-sha256.json`。

修改前的目标文件已备份在仅本机的 `data/reports/release-fixes-20261020-8d816be9/2026-10-20_pre-fix/`，其中关联层测试另存为该目录顶层的 `test_quality_qr_analysis.py`。回滚应先核对后续编辑，再只恢复本轮目标的备份或逐块撤销本次增量；不要对整个工作区执行 restore/reset，以免丢失之前未提交的修正。新建的 pytest 配置和两份修正文档可单独撤销，验证产物不自动删除。

## 2. 四项修正

### RGB/L PNG 的透明色

标准化加载器现在把 `transparency` 元数据也视为透明输入，覆盖 RGB、L 和 P 模式的 PNG tRNS；RGBA/LA 继续按已有 alpha 白底合成流程处理。读取后才进行通道转换，原图字节不变。

新增 6 项回归：RGB/L 全透明黑图在白底下亮度 255、曝光比例正确；混合透明/不透明像素准确保留；EXIF 0 与 6 的方向处理仍正确。普通不透明模式继续由既有测试覆盖。修改共享加载器也会影响 `analyze_label` 和质量/QR 关联层的新分析结果，历史报告不重算。

### 默认 pytest 收集范围

`pytest.ini` 仅增加 `testpaths = tests`。默认全套指完整产品 `tests/`，不会再收集 `data/reports/` 的历史诊断夹具或备用副本。历史夹具没有删除，需要使用时仍可显式指定路径与其依赖环境。

根目录与显式 `tests/` 分别收集到 512 项；个别既有参数在模块导入时生成 UUID，两次进程的节点参数字符串会变化，仅验证收集等价性时归一化 32 位 UUID 后逐节点比较，未改测试本身。

### 首次导出说明

README 顶部新增不依赖摄像头的完整合成 QR 入口，先创建 `.venv`、安装固定依赖、创建被 Git 忽略的报告目录，再导出到新 JSON。各 JSON CLI 仍要求父目录存在，输出仍独占新建。重复运行须换文件名。

### 不覆盖的完整报告发布

先独占新建同目录 `capture_task.json.tmp`，写完整并关闭，再执行 `os.link(temp, target)`。硬链接创建在目标已存在时失败，目标在早期检查后才出现也不会被替换；成功后只移除临时名字。

新增 5 项回归：发布窗口出现竞争报告时原字节保留；成功发布后临时名移除；硬链接不支持时明确报错并保留完整临时文件；临时名移除失败时原错误传播并注明正式报告已发布；有先前采集错误时报告发布错误仍只作附加信息，设备释放与首错优先不变。

本机 NTFS 的真实硬链接路径经正式套件和合成采集验证。其他文件系统必须支持硬链接；不支持时不降级成覆盖写。Linux 代码仍请求 V4L2，但本次没有 Linux 环境测试或实机采集，因此不能把 Windows 验证外推为 Linux 支持完成。

## 3. 冻结 oracle 的源码身份核验

第一次全套得到 **3 failed、505 passed、4 skipped**。差异全部是透明 PNG 修正使 `provenance.source_sha256.analyze_image.py` 与历史 oracle 中的旧源码摘要不同，评测业务结果闸门仍通过。

没有覆盖历史 `qr-stable-fields-oracle.json`，没有 refresh 评测期望。关联层测试从当前五个源文件的实际字节独立计算期望摘要，与报告逐项比较，来源不取自被测报告；新增五个逐项篡改摘要反例和缺失摘要反例，均必须失败。图片路径、运行库版本及解码器版本仍按已有独立身份核验，其他业务稳定字段继续精确对照冻结值，五条 volatile 路径不变。

`docs/stage-36-quality-qr-association.md` 中“源码摘要对照冻结值”是当时的历史约定；当前源码身份核验以本文为准。实现及旧 oracle 均需随版本保留，源码更新不再要求篡改历史报告。

## 4. 验证结果与失败记录

| 检查 | 实际结果 |
| --- | --- |
| 新增目标回归，修正前 | 10 failed、1 passed；完整输出见本机 `regression-before.txt` |
| 新增目标回归，修正后 | 11 passed、155 deselected，0.93s |
| 第一次完整测试 | 3 failed、505 passed、4 skipped，50.03s；源码摘要旧值差异，见上节 |
| 关联层测试修正后 | 27 passed，8.44s |
| 最终根目录完整测试 | **508 passed、4 skipped，47.34s，exit 0** |
| 精确评测闸门 | development/test 各 23 样本，与原期望完全一致，exit 0，未 refresh |
| `pip check` | exit 0，无依赖冲突 |
| 根目录/显式发现 | 两者同为 512 项；随机 UUID 参数归一化后节点相同 |
| 新源码副本 QR 导出 | exit 0，completed，独立合成答案 correct；重复同名导出 exit 2，旧 JSON 字节不变 |
| 新源码副本图片分析 | exit 0，新建 JSON |
| 新源码副本合成采集与复核 | capture exit 0；临时名已移除；review exit 0/consistent |

四项跳过都是 Windows WinError 1314，分别覆盖 PNG、任务 JSON、质量 CSV、颜色 CSV 的真实符号链接。没有新增跳过条件，没有删减或弱化产品测试。

收集等价性脚本第一次把导入时随机 UUID 当成稳定节点 ID 而断言失败；归一化该随机身份后比较通过。这是验证脚本的比较口径修正，不是产品失败，也不是 pytest 忽略参数化用例。

正式命令（项目根目录、项目 `.venv`；此处临时目录须尚不存在）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -rs -p no:cacheprovider --basetemp data/reports/release-fixes-20261020-8d816be9/full-final-temp
.\.venv\Scripts\python.exe -X utf8 tools/check_evaluation_expectations.py
.\.venv\Scripts\python.exe -m pip check
```

源码副本只复制应交付文件及新 pytest 配置，不复制旧报告、实拍或虚拟环境；CLI 复用当前项目 `.venv`，没有在新环境重新安装依赖。合成采集使用注入的摄像头对象，不访问硬件，不构成实机验收。

所有本轮日志和新合成产物仅本机：`data/reports/release-fixes-20261020-8d816be9/`。审查发现的失败输出保留，不将失败改写为成功。

## 5. 当前边界

当前候选及文件清单见 `docs/tasks/delivery-candidate-2026-10-20.md`，最新数字见 `docs/stage-34-project-capability-matrix.md`。本轮未暂存、未提交、未推送、未发布；当前修正没有对应远程 CI。项目没有独立 build/lint/type-check 配置，本轮未安装额外工具。历史近黑画面的根因仍未确认。
