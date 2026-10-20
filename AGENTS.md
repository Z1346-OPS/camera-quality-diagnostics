# camera-quality-diagnostics — 项目规则

> 项目专属规则。跨项目通用约束见 `C:\Users\zex\.codex\AGENTS.md`。
> 下面的路径与命令均已在本机实测；测试数量随用例变化，2026-10-20 的本地记录为 508 passed、4 skipped
> （见 `docs/tasks/delivery-candidate-2026-10-20.md`；跳过原因是 Windows 符号链接权限不足）。

## 项目定位

基于 Python + OpenCV 的**摄像头采集、图像质量指标记录与证据核对**项目。
目前是练习与流程验证项目，**不是**已标定的工业相机诊断产品。

**已实现**：摄像头采集；亮度/曝光比例/清晰度/对比度等指标；颜色通道均值；
读帧失败事件记录；按批次保存 CSV/JSON；可选原始帧 PNG 留证与数值复核；
本地 JPEG/PNG 图片分析；QR 解码（整图 / 人工 ROI / `--try-downscale` 降采样搜索）；
按清单批量评测（固定答案逐字节校验、失败样本留证、分组泄漏检查）。

**尚未实现**：脏污/条纹/噪点/偏色等故障的自动识别；场景阈值标定；
手机上传、数据库、服务化；标签可读性的合格判定；离线 HTML 报告导出；
批量图片质量分析入口；结构化设备/拍摄条件字段。

## 能力状态判断（防误判）

判断某项能力是否已实现时，**以最新的核对/设计记录为准**：能力边界看
`docs/stage-32-docs-vs-code-consistency.md`，数据集与 CI 回归看
`docs/stage-33-synthetic-regression-dataset.md`；**项目数字（提交数、用例数、仓库体积等）
看 `docs/stage-34-project-capability-matrix.md`，不要凭记忆说数字。**
不要依据 `docs/label-reading-project-design.md`（2026-10-01 的历史记录）或旧提交信息。

交付候选身份、支持范围与当前验证依据看 `docs/tasks/delivery-candidate-2026-10-20.md`；
**未提交改动不属于 HEAD**，不能把当前 HEAD 单独称为包含最新修正的版本。

已实现能力的准确位置：

- QR 解码与降采样搜索：`src/analyze_label.py`、`src/label_analysis.py`
- 批量评测与清单契约：`src/evaluate_labels.py`、`src/label_evaluation.py`
- 图像质量分析：`src/analyze_image.py`

改动上述模块时，必须同时更新 `docs/` 与 `README.md`（见「修改流程」第 4 条）。

回归基线：`data/manifests/evaluation-synthetic-expectations.json` —— 合成数据集
（`data/samples/synthetic-qr-v1/`）的**精确期望值**，由 CI 闸门每次提交校验。行为变化必须
`--refresh` 并人工确认后提交；**不要用阈值或容差放宽它**。

## 环境与命令（实测）

- Python **3.12.10**，虚拟环境在项目根的 `.venv`。一律使用 `.venv`，不要用系统 Python。
- 项目根：`D:\Projects\Python\camera-quality-diagnostics`
  **会话 cwd 必须 = 项目根**（见全局规则中的沙箱说明）。

```powershell
# 测试（默认由 pytest.ini 收集完整 tests/；2026-10-20 本地记录 508 passed、4 skipped）
.\.venv\Scripts\python.exe -m pytest -q

# 重新生成合成回归数据集（重写样例目录与两份清单；稳定后不要反复重生成）
.\.venv\Scripts\python.exe -X utf8 tools\generate_synthetic_samples.py

# 校验评测结果与入库期望一致（行为确实变了才用 --refresh，并需人工确认后提交）
.\.venv\Scripts\python.exe -X utf8 tools\check_evaluation_expectations.py

# 摄像头采集
.\.venv\Scripts\python.exe src\main.py
.\.venv\Scripts\python.exe src\camera_test.py

# 本地图片质量分析
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_image.py <图片> --output <新JSON>

# QR 解码 / 人工 ROI
.\.venv\Scripts\python.exe -X utf8 .\src\analyze_label.py <图片> [--roi x y w h] --output <新JSON>
```

## 目录约定

- `src/` — 入口与实现（`analyze_image.py`、`analyze_label.py`、`camera_test.py`、`main.py` …）
- `tests/` — pytest 用例，与 `src/` 模块同名对应
- `tools/` — 辅助**生成、校验、维护**数据与开发流程的脚本（如合成数据集生成、评测期望闸门）；
  **不是产品入口**，不要当作业务代码，也不要让 `src/` 依赖它
- `docs/` — 记录文件 `stage-NN-*.md`；NN 是**文档序号**，不是业务阶段号（见下节）
- `data/reports/` — 生成的 JSON / CSV；`data/samples/` — 合成样例；`data/manifests/` — 入库的评测清单与期望值
- `photo/` — 实拍原图

## 文档编号规范

- `stage-NN-*.md` 里的 NN 只表示「这是第几份记录」，**不表示业务阶段**。
- **适用范围**：本规范只管 `docs/` 顶层的阶段性设计、验证、总结文档；
  `docs/tasks/` 保持任务管理格式，**不受 stage 编号约束**。
- NN 用两位数，从 `01` 起，只增不改；作废的编号不复用（在文档正文里注明作废即可）。
- 业务阶段号只能写在标题或正文，且必须同时给出文档序号，例如：
  `业务阶段 1（文档 31）：通用图片分析入口`。
- 新增文档：NN = `docs/` 下已有 `stage-NN-*` 的最大 NN + 1（截至 2026-10-20 为 `stage-39-`）。
- 引用历史文档时**只写文件名**，不要用「阶段 N」指代。
- 已知历史偏差（**不改文件名、不重写历史**）：
  - `stage-0-design-and-learning.md`、`stage-1-local-input-verification.md`、
    `stage-2-roi-qr-baseline.md` 用一位数编号；
  - `stage-31-local-image-analysis.md` 文件序号是 31、正文却自称「阶段 1」；
  - `pixel-limit-assessment.md` 没有序号前缀，属遗留文件。

## 不可违反的约束

1. **原图只读**：不覆盖、不修改 `photo/` 与 `data/samples/` 下的任何图片。
2. **输出仅新建**：`--output` 指定的 JSON 路径必须是**新文件**；重新分析换新文件名，
   不覆盖历史报告。
3. **旧报告不改写**：可以新增字段，但不要改变历史 JSON 的既有格式与字段含义。
4. **不夸大结论**：文档必须区分「已实现」与「规划」。未读出的 QR 只能说
   "读出/未读出"，**不能称为"正确"**；无真值时 `truth_check.status` 为 `not_provided`；
   仅单一有效码与独立已知答案逐字节相同才为 `correct`。
5. **区分业务结果与程序异常**：未读出、歧义、答案不匹配**不是**执行异常；
   只有候选解码失败/执行错误才返回退出码 2。不要把业务结果包装成异常。
6. **不自动打开 QR 内的链接。**
7. 不为了让测试通过而删除、跳过或弱化测试。

## 修改流程

1. 先读相关 `src/` 与 `tests/`，确认现有行为；
2. 说明要改哪些文件、为什么、预期效果、风险、回滚方式；
3. 改完运行 `.\.venv\Scripts\python.exe -m pytest -q`；
4. 行为变更同步更新 `docs/` 与 `README.md`；
5. 报告如实写测试结果：失败就贴输出，跳过的步骤就说明跳过。
6. **提交信息统一用英文 conventional commit**：格式 `type(scope): description`，
   类型用 `feat` / `fix` / `docs` / `test` / `chore`；例如
   `docs(stage): add documentation consistency report`。历史提交不重写。
